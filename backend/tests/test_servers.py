from django.test import TestCase
from apps.accounts.models import SSHCredential, Tenant, User
from apps.servers.models import ServerGroup, Server, get_or_create_default_group, DEFAULT_GROUP_NAME


class TestServerGroup(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="测试租户")
        self.admin = User.objects.create_user(
            username="admin", password="testpass123", tenant=self.tenant, role="admin",
        )
        self.server_group = ServerGroup.objects.create(
            tenant=self.tenant, name="生产服务器", created_by=self.admin,
        )

    def test_create_group(self):
        group = ServerGroup.objects.create(tenant=self.tenant, name="web-servers", created_by=self.admin)
        self.assertEqual(group.name, "web-servers")
        self.assertEqual(group.tenant, self.tenant)

    def test_unique_name_per_tenant(self):
        with self.assertRaises(Exception):
            ServerGroup.objects.create(tenant=self.tenant, name=self.server_group.name, created_by=self.admin)

    def test_delete_group_moves_servers_to_default(self):
        from apps.servers.models import get_or_create_default_group
        from rest_framework.test import APIClient
        from rest_framework_simplejwt.tokens import RefreshToken

        group = ServerGroup.objects.create(tenant=self.tenant, name="待删分组", created_by=self.admin)
        server = Server.objects.create(hostname="srv-01", ip="10.1.1.1")
        server.groups.add(group)
        default_group = get_or_create_default_group(self.tenant)

        client = APIClient()
        token = RefreshToken.for_user(self.admin)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
        resp = client.delete(f"/api/groups/{group.id}/")
        self.assertEqual(resp.status_code, 204)
        server.refresh_from_db()
        self.assertIn(default_group, server.groups.all())
        self.assertNotIn(group, server.groups.all())

    def test_delete_default_group_rejected(self):
        from apps.servers.models import get_or_create_default_group
        from rest_framework.test import APIClient
        from rest_framework_simplejwt.tokens import RefreshToken

        default_group = get_or_create_default_group(self.tenant)
        client = APIClient()
        token = RefreshToken.for_user(self.admin)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
        resp = client.delete(f"/api/groups/{default_group.id}/")
        self.assertEqual(resp.status_code, 400)
        self.assertTrue(ServerGroup.objects.filter(id=default_group.id).exists())


class TestDefaultGroup(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="测试租户")
        self.admin = User.objects.create_user(
            username="admin", password="testpass123", tenant=self.tenant, role="admin",
        )

    def test_get_or_create_default_group(self):
        group = get_or_create_default_group(self.tenant)
        self.assertEqual(group.name, DEFAULT_GROUP_NAME)
        self.assertEqual(group.tenant, self.tenant)

    def test_default_group_idempotent(self):
        g1 = get_or_create_default_group(self.tenant)
        g2 = get_or_create_default_group(self.tenant)
        self.assertEqual(g1.id, g2.id)
        self.assertEqual(ServerGroup.objects.filter(tenant=self.tenant, name=DEFAULT_GROUP_NAME).count(), 1)

    def test_server_default_group_assignment(self):
        """Server created without group should go to default group."""
        default_group = get_or_create_default_group(self.tenant)
        server = Server.objects.create(hostname="test-01", ip="10.0.0.1")
        server.groups.add(default_group)
        self.assertIn(default_group, server.groups.all())


class TestServerM2M(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="测试租户")
        self.admin = User.objects.create_user(
            username="admin", password="testpass123", tenant=self.tenant, role="admin",
        )
        self.group_a = ServerGroup.objects.create(
            tenant=self.tenant, name="分组A", created_by=self.admin,
        )
        self.group_b = ServerGroup.objects.create(
            tenant=self.tenant, name="分组B", created_by=self.admin,
        )
        self.group_c = ServerGroup.objects.create(
            tenant=self.tenant, name="分组C", created_by=self.admin,
        )

    def test_server_single_group(self):
        server = Server.objects.create(hostname="web-01", ip="192.168.1.10")
        server.groups.add(self.group_a)
        self.assertEqual(server.groups.count(), 1)
        self.assertIn(server, self.group_a.servers.all())

    def test_server_multiple_groups(self):
        """Server can belong to multiple groups."""
        server = Server.objects.create(hostname="web-01", ip="192.168.1.10")
        server.groups.add(self.group_a, self.group_b, self.group_c)
        self.assertEqual(server.groups.count(), 3)
        self.assertIn(server, self.group_a.servers.all())
        self.assertIn(server, self.group_b.servers.all())
        self.assertIn(server, self.group_c.servers.all())

    def test_server_remove_from_group(self):
        server = Server.objects.create(hostname="web-01", ip="192.168.1.10")
        server.groups.add(self.group_a, self.group_b)
        server.groups.remove(self.group_a)
        self.assertEqual(server.groups.count(), 1)
        self.assertNotIn(server, self.group_a.servers.all())
        self.assertIn(server, self.group_b.servers.all())

    def test_server_set_groups(self):
        """Setting groups replaces all existing groups."""
        server = Server.objects.create(hostname="web-01", ip="192.168.1.10")
        server.groups.add(self.group_a, self.group_b)
        server.groups.set([self.group_c])
        self.assertEqual(server.groups.count(), 1)
        self.assertIn(server, self.group_c.servers.all())
        self.assertNotIn(server, self.group_a.servers.all())

    def test_resolve_credential_server_level(self):
        cred1 = SSHCredential.objects.create(
            tenant=self.tenant, name="group-cred", auth_type="password",
            username="root", created_by=self.admin,
        )
        cred2 = SSHCredential.objects.create(
            tenant=self.tenant, name="server-cred", auth_type="password",
            username="deploy", created_by=self.admin,
        )
        self.group_a.default_credential = cred1
        self.group_a.save()
        server = Server.objects.create(
            hostname="web-01", ip="192.168.1.10", ssh_credential=cred2,
        )
        server.groups.add(self.group_a)
        self.assertEqual(server.resolve_credential(), cred2)

    def test_resolve_credential_fallback_to_group(self):
        cred = SSHCredential.objects.create(
            tenant=self.tenant, name="group-cred", auth_type="password",
            username="root", created_by=self.admin,
        )
        self.group_a.default_credential = cred
        self.group_a.save()
        server = Server.objects.create(hostname="web-02", ip="192.168.1.11")
        server.groups.add(self.group_a)
        self.assertEqual(server.resolve_credential(), cred)

    def test_resolve_credential_multiple_groups(self):
        """Returns the first group's credential that has one."""
        cred_b = SSHCredential.objects.create(
            tenant=self.tenant, name="cred-b", auth_type="password",
            username="root", created_by=self.admin,
        )
        self.group_b.default_credential = cred_b
        self.group_b.save()
        server = Server.objects.create(hostname="web-03", ip="192.168.1.12")
        server.groups.add(self.group_a, self.group_b)
        # group_a has no credential, group_b has cred_b
        self.assertEqual(server.resolve_credential(), cred_b)

    def test_resolve_credential_none(self):
        server = Server.objects.create(hostname="web-03", ip="192.168.1.12")
        server.groups.add(self.group_a)
        self.assertIsNone(server.resolve_credential())

    def test_primary_group(self):
        server = Server.objects.create(hostname="web-01", ip="192.168.1.10")
        server.groups.add(self.group_a, self.group_b)
        self.assertIsNotNone(server.primary_group)
        self.assertIn(server.primary_group, [self.group_a, self.group_b])

    def test_bulk_create_servers(self):
        servers = []
        for i in range(1, 6):
            s = Server.objects.create(hostname=f"web-{i:02d}", ip=f"10.0.0.{i}")
            s.groups.add(self.group_a)
            servers.append(s)
        self.assertEqual(self.group_a.servers.count(), 5)

    def test_batch_group_move(self):
        """Move servers from group A to group B."""
        s1 = Server.objects.create(hostname="s1", ip="10.0.0.1")
        s2 = Server.objects.create(hostname="s2", ip="10.0.0.2")
        s1.groups.add(self.group_a)
        s2.groups.add(self.group_a)

        # Move to group B (replace)
        for s in [s1, s2]:
            s.groups.set([self.group_b])

        self.assertEqual(self.group_a.servers.count(), 0)
        self.assertEqual(self.group_b.servers.count(), 2)

    def test_batch_group_add(self):
        """Add servers to additional group."""
        s1 = Server.objects.create(hostname="s1", ip="10.0.0.1")
        s2 = Server.objects.create(hostname="s2", ip="10.0.0.2")
        s1.groups.add(self.group_a)
        s2.groups.add(self.group_a)

        # Add to group B (keep A)
        for s in [s1, s2]:
            s.groups.add(self.group_b)

        self.assertEqual(self.group_a.servers.count(), 2)
        self.assertEqual(self.group_b.servers.count(), 2)
        self.assertEqual(s1.groups.count(), 2)


class TestServerIpUnique(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="唯一性租户")
        self.user = User.objects.create_user(
            username="uniq", password="testpass123", tenant=self.tenant, role="admin",
        )

    def test_duplicate_ip_rejected_by_model(self):
        Server.objects.create(hostname="web-01", ip="192.168.1.10")
        with self.assertRaises(Exception):
            Server.objects.create(hostname="web-02", ip="192.168.1.10")

    def test_serializer_validate_ip_duplicate(self):
        from apps.servers.serializers import ServerSerializer

        Server.objects.create(hostname="web-01", ip="10.0.0.6")
        ser = ServerSerializer(data={"hostname": "web-02", "ip": "10.0.0.6"})
        self.assertFalse(ser.is_valid())
        self.assertIn("ip", ser.errors)
        self.assertIn("web-01", str(ser.errors["ip"]))

    def test_serializer_validate_ip_self_on_update(self):
        from apps.servers.serializers import ServerSerializer

        server = Server.objects.create(hostname="web-01", ip="10.0.0.7")
        ser = ServerSerializer(
            server, data={"hostname": "web-01", "ip": "10.0.0.7", "group_ids": []},
            partial=True,
        )
        self.assertTrue(ser.is_valid(), ser.errors)

    def test_serializer_accepts_ipv6(self):
        """API 应支持 IPv6 地址（与模型 GenericIPAddressField 一致）。"""
        from apps.servers.serializers import ServerSerializer

        ser = ServerSerializer(data={"hostname": "v6-01", "ip": "2001:db8::1"})
        self.assertTrue(ser.is_valid(), ser.errors)

    def test_batch_create_partial_success_on_duplicate_ip(self):
        from rest_framework.test import APIClient
        from rest_framework_simplejwt.tokens import RefreshToken
        from apps.servers.models import get_or_create_default_group

        Server.objects.create(hostname="existing", ip="10.0.0.8")
        default_group = get_or_create_default_group(self.tenant)
        client = APIClient()
        token = RefreshToken.for_user(self.user)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")

        resp = client.post(
            f"/api/groups/{default_group.id}/servers/batch/",
            {"servers": [
                {"hostname": "new-01", "ip": "10.0.0.9"},
                {"hostname": "dup", "ip": "10.0.0.8"},
                {"hostname": "new-02", "ip": "10.0.0.9"},  # 批内重复
            ]},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(len(resp.data["created"]), 1)
        self.assertEqual(len(resp.data["errors"]), 2)
        self.assertEqual(Server.objects.filter(hostname="new-01").count(), 1)
        self.assertEqual(Server.objects.filter(hostname="dup").count(), 0)

    def test_csv_import_skips_duplicate_ip(self):
        from apps.servers.batch import import_servers_csv
        from apps.servers.models import get_or_create_default_group

        Server.objects.create(hostname="existing", ip="10.0.0.10")
        group = get_or_create_default_group(self.tenant)
        csv_content = (
            "hostname,ip\n"
            "good-01,10.0.0.11\n"
            "dup,10.0.0.10\n"
            "good-02,10.0.0.12\n"
        ).encode("utf-8")
        created, errors = import_servers_csv(csv_content, group, self.tenant, self.user)
        self.assertEqual(created, 2)
        self.assertEqual(len(errors), 1)
        self.assertIn("10.0.0.10", errors[0]["error"])


class TestInlineAuth(TestCase):
    """服务器内联认证：直接填写用户名密码/私钥，无需预先创建凭据。"""

    def setUp(self):
        self.tenant = Tenant.objects.create(name="内联认证租户")
        self.user = User.objects.create_user(
            username="authuser", password="testpass123", tenant=self.tenant, role="admin",
        )

    def _credential(self, name="server-cred"):
        return SSHCredential.objects.create(
            tenant=self.tenant, name=name, auth_type="password",
            username="root", created_by=self.user,
        )

    def test_serializer_create_password_inline(self):
        from apps.servers.serializers import ServerSerializer
        from apps.accounts.crypto import decrypt_value

        ser = ServerSerializer(data={
            "hostname": "srv-pw", "ip": "10.20.0.1",
            "auth_type": "password", "auth_username": "deploy",
            "auth_password": "secret123",
        })
        self.assertTrue(ser.is_valid(), ser.errors)
        server = ser.save()
        server.refresh_from_db()
        self.assertEqual(server.auth_type, "password")
        self.assertEqual(server.auth_username, "deploy")
        self.assertIsNotNone(server.auth_password_encrypted)
        self.assertEqual(decrypt_value(bytes(server.auth_password_encrypted)), "secret123")
        # 响应不应包含明文密码
        data = ServerSerializer(server).data
        self.assertNotIn("auth_password", data)
        self.assertEqual(data["auth_type"], "password")
        self.assertEqual(data["auth_username"], "deploy")

    def test_serializer_create_key_inline(self):
        from apps.servers.serializers import ServerSerializer
        from apps.accounts.crypto import decrypt_value

        key_content = "-----BEGIN OPENSSH PRIVATE KEY-----\nsecret-key\n-----END OPENSSH PRIVATE KEY-----"
        ser = ServerSerializer(data={
            "hostname": "srv-key", "ip": "10.20.0.2",
            "auth_type": "key", "auth_username": "deploy",
            "auth_private_key": key_content,
        })
        self.assertTrue(ser.is_valid(), ser.errors)
        server = ser.save()
        server.refresh_from_db()
        self.assertEqual(server.auth_type, "key")
        self.assertEqual(decrypt_value(bytes(server.auth_private_key_encrypted)), key_content)

    def test_serializer_password_requires_password(self):
        from apps.servers.serializers import ServerSerializer

        ser = ServerSerializer(data={
            "hostname": "srv-bad", "ip": "10.20.0.3",
            "auth_type": "password", "auth_username": "deploy",
        })
        self.assertFalse(ser.is_valid())
        self.assertIn("auth_password", ser.errors)

    def test_serializer_update_keeps_existing_password(self):
        from apps.servers.serializers import ServerSerializer
        from apps.accounts.crypto import decrypt_value, encrypt_value

        server = Server.objects.create(
            hostname="srv-upd", ip="10.20.0.4",
            auth_type="password", auth_username="deploy",
            auth_password_encrypted=encrypt_value("oldpass"),
        )
        # 更新不传密码：保持原密码
        ser = ServerSerializer(server, data={"hostname": "srv-upd", "ip": "10.20.0.4"}, partial=True)
        self.assertTrue(ser.is_valid(), ser.errors)
        updated = ser.save()
        updated.refresh_from_db()
        self.assertEqual(decrypt_value(bytes(updated.auth_password_encrypted)), "oldpass")

    def test_resolve_credential_priority(self):
        """内联认证 > 服务器凭据 > 分组默认凭据。"""
        from apps.servers.models import InlineCredential
        from apps.accounts.crypto import encrypt_value

        group = ServerGroup.objects.create(tenant=self.tenant, name="g", created_by=self.user)
        group.default_credential = self._credential("group-cred")
        group.save()
        server_cred = self._credential("server-cred")
        server = Server.objects.create(
            hostname="srv-pri", ip="10.20.0.5",
            ssh_credential=server_cred,
            auth_type="password", auth_username="inline-user",
            auth_password_encrypted=encrypt_value("inline-pass"),
        )
        server.groups.add(group)
        resolved = server.resolve_credential()
        self.assertIsInstance(resolved, InlineCredential)
        self.assertEqual(resolved.username, "inline-user")
        self.assertEqual(resolved.get_password(), "inline-pass")

    def test_csv_import_password_supported(self):
        from apps.servers.batch import import_servers_csv
        from apps.accounts.crypto import decrypt_value

        group = get_or_create_default_group(self.tenant)
        csv_content = (
            "hostname,ip,auth_type,auth_username,auth_password\n"
            "imp-pw,10.20.1.1,password,deploy,importpass\n"
            "imp-none,10.20.1.2,\n"  # auth_type 留空：不设置内联认证
        ).encode("utf-8")
        created, errors = import_servers_csv(csv_content, group, self.tenant, self.user)
        self.assertEqual(created, 2, errors)
        self.assertEqual(len(errors), 0)
        s1 = Server.objects.get(hostname="imp-pw")
        self.assertEqual(s1.auth_type, "password")
        self.assertEqual(s1.auth_username, "deploy")
        self.assertEqual(decrypt_value(bytes(s1.auth_password_encrypted)), "importpass")
        s2 = Server.objects.get(hostname="imp-none")
        self.assertEqual(s2.auth_type, "credential")

    def test_csv_import_key_rejected(self):
        from apps.servers.batch import import_servers_csv

        group = get_or_create_default_group(self.tenant)
        csv_content = (
            "hostname,ip,auth_type,auth_username\n"
            "imp-key,10.20.1.3,key,deploy\n"
        ).encode("utf-8")
        created, errors = import_servers_csv(csv_content, group, self.tenant, self.user)
        self.assertEqual(created, 0)
        self.assertEqual(len(errors), 1)
        self.assertIn("不支持私钥", errors[0]["error"])

    def test_csv_import_password_missing_fields(self):
        from apps.servers.batch import import_servers_csv

        group = get_or_create_default_group(self.tenant)
        csv_content = (
            "hostname,ip,auth_type,auth_username\n"
            "imp-bad,10.20.1.4,password,deploy\n"  # 缺密码
        ).encode("utf-8")
        created, errors = import_servers_csv(csv_content, group, self.tenant, self.user)
        self.assertEqual(created, 0)
        self.assertEqual(len(errors), 1)
        self.assertIn("auth_password", errors[0]["error"])

    def test_csv_import_infers_password_without_auth_type(self):
        """auth_type 留空但提供用户名+密码时自动按密码认证处理。"""
        from apps.servers.batch import import_servers_csv
        from apps.accounts.crypto import decrypt_value

        group = get_or_create_default_group(self.tenant)
        csv_content = (
            "hostname,ip,auth_username,auth_password\n"
            "imp-inf,10.20.1.7,deploy,infpass\n"
        ).encode("utf-8")
        created, errors = import_servers_csv(csv_content, group, self.tenant, self.user)
        self.assertEqual(created, 1, errors)
        s = Server.objects.get(hostname="imp-inf")
        self.assertEqual(s.auth_type, "password")
        self.assertEqual(s.auth_username, "deploy")
        self.assertEqual(decrypt_value(bytes(s.auth_password_encrypted)), "infpass")

    def test_csv_import_chinese_content_utf8(self):
        """UTF-8 CSV 中文分组/主机名/标签导入成功。"""
        from apps.servers.batch import import_servers_csv

        group = get_or_create_default_group(self.tenant)
        csv_content = (
            "hostname,ip,labels,tags,groups\n"
            "中文字符机,10.20.1.8,生产环境,重要,中文分组\n"
        ).encode("utf-8-sig")
        created, errors = import_servers_csv(csv_content, group, self.tenant, self.user)
        self.assertEqual(created, 1, errors)
        s = Server.objects.get(hostname="中文字符机")
        self.assertEqual(s.labels, ["生产环境"])
        self.assertEqual(s.tags, ["重要"])
        self.assertTrue(s.groups.filter(name="中文分组").exists())

    def test_csv_import_chinese_content_gbk(self):
        """GBK 编码 CSV（Excel 中文环境）导入成功。"""
        from apps.servers.batch import import_servers_csv

        group = get_or_create_default_group(self.tenant)
        csv_content = (
            "hostname,ip,groups\n"
            "测试服务器,10.20.1.9,中文分组二\n"
        ).encode("gbk")
        created, errors = import_servers_csv(csv_content, group, self.tenant, self.user)
        self.assertEqual(created, 1, errors)
        self.assertTrue(Server.objects.filter(hostname="测试服务器").exists())
        self.assertTrue(ServerGroup.objects.filter(name="中文分组二", tenant=self.tenant).exists())

    def test_csv_import_undecodable_returns_clear_error(self):
        """无法识别的编码返回明确错误（不抛 500）。"""
        from apps.servers.batch import import_servers_csv, CSVDecodeError

        group = get_or_create_default_group(self.tenant)
        with self.assertRaises(CSVDecodeError):
            import_servers_csv(b"\xff\xfe\x00\x81", group, self.tenant, self.user)

    def test_batch_api_inline_password(self):
        from rest_framework.test import APIClient
        from rest_framework_simplejwt.tokens import RefreshToken
        from apps.accounts.crypto import decrypt_value

        group = get_or_create_default_group(self.tenant)
        client = APIClient()
        token = RefreshToken.for_user(self.user)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
        resp = client.post(
            f"/api/groups/{group.id}/servers/batch/",
            {"servers": [{
                "hostname": "api-pw", "ip": "10.20.1.5",
                "auth_type": "password", "auth_username": "deploy", "auth_password": "apipass",
            }]},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        server = Server.objects.get(hostname="api-pw")
        self.assertEqual(server.auth_type, "password")
        self.assertEqual(decrypt_value(bytes(server.auth_password_encrypted)), "apipass")
        # 响应不返回明文密码
        created_data = resp.data["created"][0]
        self.assertNotIn("auth_password", created_data)

    def test_batch_api_inline_key(self):
        """批量 API 也支持私钥（前端批量添加仅限密码，API 层保留能力）。"""
        from rest_framework.test import APIClient
        from rest_framework_simplejwt.tokens import RefreshToken

        group = get_or_create_default_group(self.tenant)
        client = APIClient()
        token = RefreshToken.for_user(self.user)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
        resp = client.post(
            f"/api/groups/{group.id}/servers/batch/",
            {"servers": [{
                "hostname": "api-key", "ip": "10.20.1.6",
                "auth_type": "key", "auth_username": "deploy", "auth_private_key": "PRIVATE-KEY",
            }]},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        server = Server.objects.get(hostname="api-key")
        self.assertEqual(server.auth_type, "key")
