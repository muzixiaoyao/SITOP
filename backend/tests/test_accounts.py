from django.test import TestCase
from rest_framework.test import APIClient
from apps.accounts.models import Tenant, User, SSHCredential
from apps.accounts.crypto import encrypt_value, decrypt_value


class TestTenant(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="测试租户")

    def test_create_tenant(self):
        t = Tenant.objects.create(name="TestOrg")
        self.assertEqual(t.name, "TestOrg")
        self.assertEqual(t.status, "active")
        self.assertIsNotNone(t.id)

    def test_tenant_name_unique(self):
        with self.assertRaises(Exception):
            Tenant.objects.create(name=self.tenant.name)


class TestUser(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="测试租户")
        self.admin = User.objects.create_user(
            username="admin", password="testpass123", tenant=self.tenant, role="admin",
        )

    def test_user_belongs_to_tenant(self):
        user = User.objects.create_user(username="testuser", password="pass123", tenant=self.tenant)
        self.assertEqual(user.tenant, self.tenant)
        self.assertEqual(user.role, "operator")

    def test_user_str(self):
        self.assertIn("admin", str(self.admin))

    def test_last_admin_cannot_demote_self(self):
        """唯一管理员不能降级自己，防止平台锁死。"""
        from rest_framework.test import APIClient
        from rest_framework_simplejwt.tokens import RefreshToken

        client = APIClient()
        token = RefreshToken.for_user(self.admin)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
        resp = client.patch(f"/api/auth/users/{self.admin.id}/", {"role": "operator"}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("role", resp.data)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role, "admin")

    def test_admin_can_demote_self_when_other_admin_exists(self):
        """存在其他管理员时允许降级自己。"""
        from rest_framework.test import APIClient
        from rest_framework_simplejwt.tokens import RefreshToken

        User.objects.create_user(
            username="admin2", password="testpass123", tenant=self.tenant, role="admin",
        )
        client = APIClient()
        token = RefreshToken.for_user(self.admin)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
        resp = client.patch(f"/api/auth/users/{self.admin.id}/", {"role": "operator"}, format="json")
        self.assertEqual(resp.status_code, 200, resp.data)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role, "operator")

    def test_operator_cannot_promote_self(self):
        """操作员不能通过 API 提升自己为管理员（权限隔离）。"""
        from rest_framework.test import APIClient
        from rest_framework_simplejwt.tokens import RefreshToken

        operator = User.objects.create_user(
            username="op", password="testpass123", tenant=self.tenant, role="operator",
        )
        client = APIClient()
        token = RefreshToken.for_user(operator)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
        resp = client.patch(f"/api/auth/users/{operator.id}/", {"role": "admin"}, format="json")
        self.assertEqual(resp.status_code, 403)


class TestSSHCredential(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="测试租户")
        self.admin = User.objects.create_user(
            username="admin", password="testpass123", tenant=self.tenant, role="admin",
        )

    def _client(self):
        c = APIClient()
        # force_authenticate sets request.user at the DRF view layer, mirroring JWT auth
        # where TenantMiddleware sees an anonymous user and request.tenant is None.
        c.force_authenticate(user=self.admin)
        return c

    def test_api_create_password_credential(self):
        resp = self._client().post("/api/auth/credentials/", {
            "name": "api-cred", "auth_type": "password", "username": "root", "password": "secret123",
        }, format="json")
        self.assertEqual(resp.status_code, 201, resp.data)
        cred = SSHCredential.objects.get(id=resp.data["id"])
        self.assertEqual(cred.tenant, self.tenant)
        self.assertEqual(cred.get_password(), "secret123")

    def test_api_create_key_credential(self):
        key_content = "-----BEGIN OPENSSH PRIVATE KEY-----\nfake-key\n-----END OPENSSH PRIVATE KEY-----"
        resp = self._client().post("/api/auth/credentials/", {
            "name": "api-key", "auth_type": "key", "username": "deploy",
            "private_key_content": key_content,
        }, format="json")
        self.assertEqual(resp.status_code, 201, resp.data)
        cred = SSHCredential.objects.get(id=resp.data["id"])
        self.assertEqual(cred.tenant, self.tenant)
        self.assertEqual(cred.get_private_key(), key_content)

    def test_api_create_credential_cross_tenant_isolated(self):
        other = Tenant.objects.create(name="其他租户")
        other_user = User.objects.create_user(
            username="other", password="pass123", tenant=other, role="admin",
        )
        c = APIClient()
        c.force_authenticate(user=other_user)
        resp = c.post("/api/auth/credentials/", {
            "name": "other-cred", "auth_type": "password", "username": "root", "password": "x",
        }, format="json")
        self.assertEqual(resp.status_code, 201, resp.data)
        # original tenant must not see it
        lst = self._client().get("/api/auth/credentials/")
        self.assertEqual(lst.data["count"], 0)

    def test_password_credential(self):
        cred = SSHCredential.objects.create(
            tenant=self.tenant, name="test-cred", auth_type="password",
            username="root", created_by=self.admin,
        )
        cred.set_password("secret123")
        cred.save()
        cred.refresh_from_db()
        self.assertEqual(cred.get_password(), "secret123")

    def test_key_credential(self):
        cred = SSHCredential.objects.create(
            tenant=self.tenant, name="key-cred", auth_type="key",
            username="deploy", created_by=self.admin,
        )
        key_content = "-----BEGIN OPENSSH PRIVATE KEY-----\nfake-key\n-----END OPENSSH PRIVATE KEY-----"
        cred.set_private_key(key_content)
        cred.save()
        cred.refresh_from_db()
        self.assertEqual(cred.get_private_key(), key_content)


class TestCrypto(TestCase):
    def test_encrypt_decrypt_roundtrip(self):
        plaintext = "my-secret-password"
        encrypted = encrypt_value(plaintext)
        self.assertIsInstance(encrypted, bytes)
        self.assertEqual(decrypt_value(encrypted), plaintext)

    def test_different_encryptions_differ(self):
        e1 = encrypt_value("test")
        e2 = encrypt_value("test")
        self.assertNotEqual(e1, e2)
