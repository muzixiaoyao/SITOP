import uuid
from django.db import models
from apps.accounts.models import Tenant, User


class Script(models.Model):
    """Shell/Python script template with version management."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="scripts")
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    script_type = models.CharField(
        max_length=20,
        choices=[
            ("health_check", "健康检查"),
            ("init_step", "初始化步骤"),
            ("completion_check", "完成度检查"),
        ],
    )
    language = models.CharField(
        max_length=10,
        choices=[("shell", "Shell"), ("python", "Python")],
        default="shell",
    )
    content = models.TextField()
    version = models.PositiveIntegerField(default=1)
    parameter_schema = models.JSONField(default=dict, blank=True)
    # HMAC-SHA256 signature of content (M4): verified before execution
    signature = models.CharField(max_length=64, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        unique_together = [("tenant", "name", "version")]

    def __str__(self):
        return f"{self.name} v{self.version} ({self.get_script_type_display()})"

    def save(self, *args, **kwargs):
        # Keep the signature in sync with content on every save
        from .signing import compute_signature
        self.signature = compute_signature(self.content)
        super().save(*args, **kwargs)

    def verify_signature(self) -> bool:
        from .signing import compute_signature
        return self.signature == compute_signature(self.content)

    def save_version_snapshot(self):
        """Snapshot current content as a historical version."""
        ScriptVersion.objects.create(
            script=self, version=self.version, content=self.content,
            created_by=self.created_by,
        )


class ScriptVersion(models.Model):
    """Immutable snapshot of a script's content at a given version."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    script = models.ForeignKey(Script, on_delete=models.CASCADE, related_name="versions")
    version = models.PositiveIntegerField()
    content = models.TextField()
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-version"]
        unique_together = [("script", "version")]

    def __str__(self):
        return f"{self.script.name} v{self.version}"
