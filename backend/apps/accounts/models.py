import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models


class Tenant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    status = models.CharField(
        max_length=20,
        choices=[("active", "活跃"), ("suspended", "暂停"), ("archived", "归档")],
        default="active",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="users")
    role = models.CharField(
        max_length=20,
        choices=[
            ("admin", "平台管理员"),  # 保留 admin 值，向后兼容
            ("operator", "运维员"),
            ("viewer", "只读"),
            ("enterprise_admin", "企业管理员"),
            ("enterprise_user", "企业员工"),
        ],
        default="operator",
    )

    class Meta:
        ordering = ["-date_joined"]

    def __str__(self):
        return f"{self.username} ({self.tenant.name})"


class SSHCredential(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="credentials")
    name = models.CharField(max_length=100)
    
    # Authentication type (JumpServer-inspired)
    auth_type = models.CharField(
        max_length=20,
        choices=[
            ("password", "密码"),
            ("key", "SSH密钥"),
            ("key_with_passphrase", "SSH密钥+密码"),
            ("token", "临时Token"),
        ],
        default="password",
    )
    username = models.CharField(max_length=100)
    
    # Credential data (encrypted)
    encrypted_password = models.BinaryField(null=True, blank=True)
    private_key = models.BinaryField(null=True, blank=True)
    passphrase = models.BinaryField(null=True, blank=True)
    token = models.BinaryField(null=True, blank=True, help_text="临时Token（加密存储）")
    
    # SSH Agent support (JumpServer-inspired)
    use_ssh_agent = models.BooleanField(default=False, help_text="使用SSH Agent转发")
    
    # Optional SSH jump host (M4): connections tunnel through this host
    jump_host = models.CharField(max_length=255, blank=True)
    jump_port = models.PositiveIntegerField(default=22)
    jump_username = models.CharField(max_length=100, blank=True)
    
    # Connection settings
    connect_timeout = models.PositiveIntegerField(default=15, help_text="连接超时（秒）")
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.username}@{self.auth_type})"

    def set_password(self, password: str):
        from .crypto import encrypt_value
        self.encrypted_password = encrypt_value(password)

    def get_password(self) -> str | None:
        if not self.encrypted_password:
            return None
        from .crypto import decrypt_value
        return decrypt_value(bytes(self.encrypted_password))

    def set_private_key(self, key: str):
        from .crypto import encrypt_value
        self.private_key = encrypt_value(key)

    def get_private_key(self) -> str | None:
        if not self.private_key:
            return None
        from .crypto import decrypt_value
        return decrypt_value(bytes(self.private_key))

    def set_token(self, token: str):
        from .crypto import encrypt_value
        self.token = encrypt_value(token)

    def get_token(self) -> str | None:
        if not self.token:
            return None
        from .crypto import decrypt_value
        return decrypt_value(bytes(self.token))


class AuditLog(models.Model):
    """Append-only audit trail. Never updated or deleted through the API."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="audit_logs")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="+")
    action = models.CharField(max_length=100)  # e.g. job.create, server.delete
    resource_type = models.CharField(max_length=50)
    resource_id = models.CharField(max_length=50, blank=True)
    details = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["tenant", "-created_at"])]

    def __str__(self):
        return f"{self.action} {self.resource_type} {self.resource_id}"
