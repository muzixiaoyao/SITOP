import uuid
from dataclasses import dataclass

from django.db import models
from apps.accounts.models import Tenant, User, SSHCredential

DEFAULT_GROUP_NAME = "未分组"


def get_or_create_default_group(tenant):
    """Get or create the default '未分组' group for a tenant."""
    group, _ = ServerGroup.objects.get_or_create(
        tenant=tenant,
        name=DEFAULT_GROUP_NAME,
        defaults={"description": "默认分组，用于存放未指定分组的服务器"},
    )
    return group


class ServerGroup(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="server_groups")
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    default_credential = models.ForeignKey(
        SSHCredential, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    # Scheduled connectivity patrol (M4)
    auto_patrol = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("tenant", "name")]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.tenant.name})"


class Server(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    groups = models.ManyToManyField(ServerGroup, related_name="servers", blank=True)
    hostname = models.CharField(max_length=255)
    ip = models.GenericIPAddressField(unique=True)
    ssh_port = models.PositiveIntegerField(default=22)
    
    # Protocol and platform (JumpServer-inspired)
    protocol = models.CharField(
        max_length=20,
        choices=[("ssh", "SSH"), ("rdp", "RDP"), ("telnet", "Telnet"), ("vnc", "VNC")],
        default="ssh",
    )
    platform = models.CharField(
        max_length=50,
        choices=[
            ("linux", "Linux"), ("windows", "Windows"), ("unix", "Unix"),
            ("network", "网络设备"), ("other", "其他"),
        ],
        default="linux",
    )
    os_info = models.CharField(max_length=200, blank=True)
    
    # SSH connection options (JumpServer-inspired)
    connect_timeout = models.PositiveIntegerField(default=15, help_text="连接超时（秒）")
    exec_timeout = models.PositiveIntegerField(default=600, help_text="执行超时（秒）")
    ssh_options = models.JSONField(default=dict, blank=True, help_text="SSH选项: StrictHostKeyChecking, etc.")
    
    # Labels and tags for grouping
    labels = models.JSONField(default=list, blank=True)
    tags = models.JSONField(default=list, blank=True, help_text="自定义标签")
    
    # Credential and connectivity
    ssh_credential = models.ForeignKey(
        SSHCredential, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    
    # 内联认证（可直接在添加界面填写用户名密码/私钥，无需预先创建凭据）
    auth_type = models.CharField(
        max_length=20,
        choices=[("credential", "使用凭据"), ("password", "密码"), ("key", "私钥")],
        default="credential",
        help_text="认证方式：credential=使用已有凭据；password=直接用户名密码；key=直接用户名+私钥",
    )
    auth_username = models.CharField(max_length=100, blank=True, default="")
    auth_password_encrypted = models.BinaryField(null=True, blank=True, help_text="内联密码（加密存储）")
    auth_private_key_encrypted = models.BinaryField(null=True, blank=True, help_text="内联私钥（加密存储）")
    
    connectivity_status = models.CharField(
        max_length=20,
        choices=[("unknown", "未知"), ("success", "连通"), ("failed", "失败")],
        default="unknown",
    )
    last_check_time = models.DateTimeField(null=True, blank=True)
    
    # Custom fields (JumpServer-inspired)
    custom_fields = models.JSONField(default=dict, blank=True, help_text="自定义字段")
    comment = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["hostname"]

    def __str__(self):
        return f"{self.hostname} ({self.ip})"

    def resolve_credential(self):
        """Resolve credential: inline auth first, then server credential, then group default."""
        if self.auth_type == "password" and self.auth_username and self.auth_password_encrypted:
            return InlineCredential(self)
        if self.auth_type == "key" and self.auth_username and self.auth_private_key_encrypted:
            return InlineCredential(self)
        if self.ssh_credential:
            return self.ssh_credential
        for group in self.groups.all():
            if group.default_credential:
                return group.default_credential
        return None

    @property
    def primary_group(self):
        """Return the first group (for backward compatibility / display)."""
        return self.groups.first()


@dataclass
class InlineCredential:
    """Wraps a Server with inline auth as a credential-like object for SSHExecutor."""
    server: Server

    @property
    def username(self) -> str:
        return self.server.auth_username

    @property
    def auth_type(self) -> str:
        return self.server.auth_type

    def get_password(self) -> str | None:
        from apps.accounts.crypto import decrypt_value
        if self.server.auth_password_encrypted:
            return decrypt_value(bytes(self.server.auth_password_encrypted))
        return None

    def get_private_key(self) -> str | None:
        from apps.accounts.crypto import decrypt_value
        if self.server.auth_private_key_encrypted:
            return decrypt_value(bytes(self.server.auth_private_key_encrypted))
        return None

    @property
    def passphrase(self) -> None:
        return None

    @property
    def jump_host(self) -> str:
        return ""

    @property
    def jump_port(self):
        return 22

    @property
    def jump_username(self) -> str:
        return ""
