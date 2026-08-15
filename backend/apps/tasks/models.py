import uuid
from django.db import models
from apps.accounts.models import Tenant, User
from apps.servers.models import ServerGroup, Server
from apps.scripts.models import Script


class InitTemplate(models.Model):
    """Initialization template with ordered steps."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="init_templates")
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    health_check_script = models.ForeignKey(
        Script, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", limit_choices_to={"script_type": "health_check"},
    )
    completion_check_script = models.ForeignKey(
        Script, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", limit_choices_to={"script_type": "completion_check"},
    )
    # Optional webhook called when the job finishes (M4)
    webhook_url = models.URLField(max_length=500, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.name


class TemplateStep(models.Model):
    """A step within an initialization template."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    template = models.ForeignKey(InitTemplate, on_delete=models.CASCADE, related_name="steps")
    step_order = models.PositiveIntegerField()
    script = models.ForeignKey(Script, on_delete=models.CASCADE, related_name="+")
    parameters = models.JSONField(default=dict, blank=True)
    timeout_seconds = models.PositiveIntegerField(default=600)
    on_failure = models.CharField(
        max_length=10,
        choices=[("abort", "中断"), ("continue", "继续"), ("retry", "重试")],
        default="abort",
    )
    max_retries = models.PositiveIntegerField(default=3)

    class Meta:
        ordering = ["step_order"]
        unique_together = [("template", "step_order")]

    def __str__(self):
        return f"Step {self.step_order}: {self.script.name}"


class InitJob(models.Model):
    """An initialization job (batch task across a server group)."""
    STATUS_CHOICES = [
        ("pending", "等待中"),
        ("running", "运行中"),
        ("success", "成功"),
        ("failed", "失败"),
        ("cancelled", "已取消"),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="init_jobs")
    template = models.ForeignKey(InitTemplate, on_delete=models.SET_NULL, null=True, related_name="jobs")
    group = models.ForeignKey(ServerGroup, on_delete=models.CASCADE, related_name="jobs")
    triggered_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="+")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True)
    current_phase = models.CharField(
        max_length=20,
        choices=[
            ("connectivity", "连通性检查"),
            ("health", "健康检查"),
            ("init", "初始化"),
            ("completion", "完成度检查"),
        ],
        default="connectivity",
    )
    summary = models.JSONField(default=dict, blank=True)
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "-created_at"]),
            models.Index(fields=["tenant", "status"]),
        ]

    def __str__(self):
        return f"Job {self.id} ({self.status})"


class JobServerTask(models.Model):
    """Per-server task within a job."""
    STATUS_CHOICES = [
        ("pending", "等待中"),
        ("running", "运行中"),
        ("success", "成功"),
        ("failed", "失败"),
        ("timeout", "超时"),
        ("cancelled", "已取消"),
        ("skipped", "跳过"),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(InitJob, on_delete=models.CASCADE, related_name="server_tasks")
    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name="tasks")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True)
    current_step = models.PositiveIntegerField(default=0)
    connectivity_result = models.JSONField(default=dict, blank=True)
    health_result = models.JSONField(default=dict, blank=True)
    completion_result = models.JSONField(default=dict, blank=True)
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    attempt = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["server__hostname"]
        indexes = [
            models.Index(fields=["job", "status"]),
        ]

    def __str__(self):
        return f"{self.job.id} - {self.server.hostname} ({self.status})"


class TaskStepLog(models.Model):
    """Log entry for a step execution within a server task."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    server_task = models.ForeignKey(JobServerTask, on_delete=models.CASCADE, related_name="step_logs")
    phase = models.CharField(max_length=20)
    step_order = models.PositiveIntegerField(null=True, blank=True)
    script_name = models.CharField(max_length=200, blank=True)
    output = models.TextField(blank=True)
    error = models.TextField(blank=True)
    exit_code = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, default="running")
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["started_at"]
        indexes = [
            models.Index(fields=["server_task", "phase"]),
        ]

    def __str__(self):
        return f"Log {self.phase} step={self.step_order} ({self.status})"
