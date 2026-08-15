from rest_framework import serializers
from django.db import IntegrityError
from .models import ServerGroup, Server, get_or_create_default_group
from apps.accounts.crypto import encrypt_value


def encrypt_inline_auth(validated_data):
    """将内联认证明文字段（auth_password/auth_private_key）转为加密存储字段。"""
    pw = validated_data.pop("auth_password", None)
    pk = validated_data.pop("auth_private_key", None)
    if pw:
        validated_data["auth_password_encrypted"] = encrypt_value(pw)
    if pk:
        validated_data["auth_private_key_encrypted"] = encrypt_value(pk)
    return validated_data


class ServerGroupBriefSerializer(serializers.ModelSerializer):
    """Lightweight group serializer for embedding in server responses."""

    class Meta:
        model = ServerGroup
        fields = ["id", "name", "description"]
        read_only_fields = fields


class ServerSerializer(serializers.ModelSerializer):
    groups = ServerGroupBriefSerializer(many=True, read_only=True)
    ip = serializers.IPAddressField(protocol='both')
    group_ids = serializers.ListField(
        child=serializers.UUIDField(),
        write_only=True,
        required=False,
    )
    # 内联认证（写接口可传明文密码/私钥，不回传）
    auth_password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    auth_private_key = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = Server
        fields = [
            "id", "hostname", "ip", "ssh_port", "protocol", "platform",
            "os_info", "connect_timeout", "exec_timeout", "ssh_options",
            "labels", "tags", "custom_fields", "comment",
            "ssh_credential", "connectivity_status", "last_check_time",
            "groups", "group_ids",
            "auth_type", "auth_username", "auth_password", "auth_private_key",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "connectivity_status", "last_check_time",
            "created_at", "updated_at", "groups",
        ]

    def validate_ip(self, value):
        qs = Server.objects.filter(ip=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            existing = qs.first()
            raise serializers.ValidationError(
                f"IP 地址已存在（hostname: {existing.hostname}），不允许重复添加"
            )
        return value

    def validate(self, attrs):
        auth_type = attrs.get("auth_type", self.instance.auth_type if self.instance else "credential")
        existing_username = self.instance.auth_username if self.instance else ""
        if auth_type == "password":
            pw = attrs.get("auth_password", "")
            if not pw and (not self.instance or not self.instance.auth_password_encrypted):
                raise serializers.ValidationError({"auth_password": "密码认证类型必须填写密码"})
            if not (attrs.get("auth_username") or existing_username or "").strip():
                raise serializers.ValidationError({"auth_username": "密码认证类型必须填写用户名"})
        elif auth_type == "key":
            pk = attrs.get("auth_private_key", "")
            if not pk and (not self.instance or not self.instance.auth_private_key_encrypted):
                raise serializers.ValidationError({"auth_private_key": "私钥认证类型必须填写私钥"})
            if not (attrs.get("auth_username") or existing_username or "").strip():
                raise serializers.ValidationError({"auth_username": "私钥认证类型必须填写用户名"})
        return attrs

    def _encrypt_and_create(self, validated_data):
        return encrypt_inline_auth(validated_data)

    def create(self, validated_data):
        validated_data = self._encrypt_and_create(validated_data)
        group_ids = validated_data.pop("group_ids", [])
        request = self.context.get("request")
        tenant = None
        if request:
            tenant = getattr(request, "tenant", None) or getattr(request.user, "tenant", None)

        server = Server.objects.create(**validated_data)

        if group_ids:
            if tenant:
                groups = ServerGroup.objects.filter(id__in=group_ids, tenant=tenant)
            else:
                groups = ServerGroup.objects.filter(id__in=group_ids)
            server.groups.set(groups)
        elif tenant:
            # Default to "未分组" if no groups specified
            default_group = get_or_create_default_group(tenant)
            server.groups.add(default_group)

        return server

    def update(self, instance, validated_data):
        validated_data = self._encrypt_and_create(validated_data)
        group_ids = validated_data.pop("group_ids", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if group_ids is not None:
            request = self.context.get("request")
            tenant = None
            if request:
                tenant = getattr(request, "tenant", None) or getattr(request.user, "tenant", None)
            if tenant:
                groups = ServerGroup.objects.filter(id__in=group_ids, tenant=tenant)
            else:
                groups = ServerGroup.objects.filter(id__in=group_ids)
            instance.groups.set(groups)

        return instance


class ServerBatchCreateSerializer(serializers.Serializer):
    servers = ServerSerializer(many=True)

    def create(self, validated_data):
        group = self.context.get("group")
        tenant = self.context.get("tenant")
        request = self.context.get("request")
        if not tenant and request:
            tenant = getattr(request, "tenant", None) or getattr(request.user, "tenant", None)

        from apps.accounts.models import SSHCredential

        created_servers = []
        # 并发窗口兜底：数据库唯一约束触发时记录错误并继续（视图层已预检剔除大部分重复）
        self._errors = []
        for server_data in validated_data["servers"]:
            group_ids = server_data.pop("group_ids", [])
            encrypt_inline_auth(server_data)  # 内联认证明文 → 加密字段
            credential_id = server_data.pop("ssh_credential", None)
            if credential_id and tenant:
                try:
                    server_data["ssh_credential"] = SSHCredential.objects.get(id=credential_id, tenant=tenant)
                except SSHCredential.DoesNotExist:
                    pass
            try:
                server = Server.objects.create(**server_data)
            except IntegrityError as e:
                ip = server_data.get("ip")
                self._errors.append({"ip": ip or "", "error": f"IP 地址已存在，不允许重复添加 ({e})"})
                continue

            if group_ids:
                if tenant:
                    groups = ServerGroup.objects.filter(id__in=group_ids, tenant=tenant)
                else:
                    groups = ServerGroup.objects.filter(id__in=group_ids)
                server.groups.set(groups)
            elif group:
                server.groups.add(group)
            elif tenant:
                default_group = get_or_create_default_group(tenant)
                server.groups.add(default_group)

            created_servers.append(server)
        return created_servers


class ServerBatchOperationSerializer(serializers.Serializer):
    """Serializer for batch operations on servers."""
    server_ids = serializers.ListField(
        child=serializers.UUIDField(),
        help_text="服务器ID列表",
    )


class ServerBatchCredentialUpdateSerializer(ServerBatchOperationSerializer):
    """Serializer for batch credential update."""
    credential_id = serializers.UUIDField(help_text="要应用的凭据ID")


class ServerBatchDeleteSerializer(ServerBatchOperationSerializer):
    """Serializer for batch delete."""
    pass


class ServerBatchGroupSerializer(ServerBatchOperationSerializer):
    """Serializer for batch group operations (move/add)."""
    group_ids = serializers.ListField(
        child=serializers.UUIDField(),
        help_text="目标分组 ID 列表",
    )


class ServerGroupSerializer(serializers.ModelSerializer):
    server_count = serializers.IntegerField(source="servers.count", read_only=True)
    servers = ServerSerializer(many=True, read_only=True)

    class Meta:
        model = ServerGroup
        fields = [
            "id", "name", "description", "default_credential",
            "auto_patrol", "server_count", "servers",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class ServerGroupListSerializer(serializers.ModelSerializer):
    server_count = serializers.IntegerField(source="servers.count", read_only=True)

    class Meta:
        model = ServerGroup
        fields = [
            "id", "name", "description", "server_count",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
