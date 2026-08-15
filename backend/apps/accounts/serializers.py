from rest_framework import serializers
from .models import Tenant, User, SSHCredential, AuditLog


class TenantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = ["id", "name", "status", "created_at"]
        read_only_fields = ["id", "created_at"]


class UserSerializer(serializers.ModelSerializer):
    tenant_name = serializers.CharField(source="tenant.name", read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "email", "role", "tenant", "tenant_name", "is_active", "date_joined"]
        read_only_fields = ["id", "date_joined"]

    def validate(self, attrs):
        """保护：最后一个管理员不能降级自己，防止平台锁死。"""
        request = self.context.get("request")
        new_role = attrs.get("role")
        if (
            self.instance
            and request
            and new_role
            and new_role != "admin"
            and self.instance.id == request.user.id
            and self.instance.role == "admin"
        ):
            other_admins = User.objects.filter(
                tenant=self.instance.tenant, role="admin", is_active=True,
            ).exclude(id=self.instance.id).count()
            if other_admins == 0:
                raise serializers.ValidationError(
                    {"role": "不能降级最后一个管理员，请先提升其他用户为管理员"}
                )
        return attrs


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)

    class Meta:
        model = User
        fields = ["id", "username", "email", "password", "role", "tenant"]
        read_only_fields = ["id"]

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class SSHCredentialSerializer(serializers.ModelSerializer):
    # Write-only fields for credential input
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    private_key_content = serializers.CharField(write_only=True, required=False, allow_blank=True)
    passphrase_content = serializers.CharField(write_only=True, required=False, allow_blank=True)
    token_content = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = SSHCredential
        fields = [
            "id", "name", "auth_type", "username",
            "password", "private_key_content", "passphrase_content", "token_content",
            "use_ssh_agent", "jump_host", "jump_port", "jump_username",
            "connect_timeout", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        private_key_content = validated_data.pop("private_key_content", None)
        passphrase_content = validated_data.pop("passphrase_content", None)
        token_content = validated_data.pop("token_content", None)
        request = self.context["request"]
        # request.tenant is set by TenantMiddleware (pre-DRF-auth, may be None with JWT);
        # always fall back to the authenticated user's tenant.
        tenant = getattr(request, "tenant", None) or getattr(request.user, "tenant", None)
        cred = SSHCredential.objects.create(
            tenant=tenant,
            created_by=request.user,
            **validated_data,
        )
        if password:
            cred.set_password(password)
        if private_key_content:
            cred.set_private_key(private_key_content)
        if passphrase_content:
            from .crypto import encrypt_value
            cred.passphrase = encrypt_value(passphrase_content)
        if token_content:
            cred.set_token(token_content)
        cred.save()
        return cred

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        private_key_content = validated_data.pop("private_key_content", None)
        passphrase_content = validated_data.pop("passphrase_content", None)
        token_content = validated_data.pop("token_content", None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        if password:
            instance.set_password(password)
        if private_key_content:
            instance.set_private_key(private_key_content)
        if passphrase_content:
            from .crypto import encrypt_value
            instance.passphrase = encrypt_value(passphrase_content)
        if token_content:
            instance.set_token(token_content)
        
        instance.save()
        return instance


class MeSerializer(serializers.ModelSerializer):
    tenant = TenantSerializer(read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "email", "role", "tenant"]


class AuditLogSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True, default=None)

    class Meta:
        model = AuditLog
        fields = ["id", "username", "action", "resource_type", "resource_id", "details", "ip_address", "created_at"]
