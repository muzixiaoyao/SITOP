import uuid
from django.db import models
from apps.accounts.models import Tenant, User
from apps.tasks.models import InitJob


class SLAPolicy(models.Model):
    """SLA 策略：定义各优先级的响应/处理时限"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    priority = models.CharField(
        max_length=20,
        choices=[("critical", "紧急"), ("high", "高"), ("medium", "中"), ("low", "低")],
    )
    response_minutes = models.PositiveIntegerField(help_text="响应时限（分钟）")
    resolve_minutes = models.PositiveIntegerField(help_text="处理时限（分钟）")
    escalation_rules = models.JSONField(default=dict, blank=True, help_text="超时升级规则")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["priority"]
        verbose_name = "SLA策略"

    def __str__(self):
        return f"{self.name} ({self.get_priority_display()})"


class TicketFlow(models.Model):
    """工单流转模板"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True, related_name="ticket_flows")
    name = models.CharField(max_length=100)
    ticket_type = models.CharField(
        max_length=20,
        choices=[("fault", "故障"), ("request", "需求"), ("internal", "内部请求"), ("change", "变更")],
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "流转模板"

    def __str__(self):
        return f"{self.name} ({self.get_ticket_type_display()})"


class TicketNode(models.Model):
    """流程节点"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    flow = models.ForeignKey(TicketFlow, on_delete=models.CASCADE, related_name="nodes")
    name = models.CharField(max_length=100)
    order = models.PositiveIntegerField()
    role_required = models.CharField(
        max_length=20,
        choices=[
            ("admin", "平台管理员"),
            ("operator", "运维员"),
            ("enterprise_admin", "企业管理员"),
        ],
        default="operator",
    )
    is_terminal = models.BooleanField(default=False)
    sla_hours = models.PositiveIntegerField(default=8, help_text="节点处理时限（小时）")
    auto_assign_rule = models.CharField(
        max_length=20,
        choices=[("manual", "手动"), ("round_robin", "轮询"), ("least_load", "最少负载")],
        default="manual",
    )

    class Meta:
        ordering = ["flow", "order"]
        unique_together = [("flow", "order")]
        verbose_name = "流程节点"

    def __str__(self):
        return f"{self.flow.name} - {self.name}"


class Ticket(models.Model):
    """工单主表"""
    STATUS_CHOICES = [
        ("pending", "待受理"),
        ("assigned", "已分派"),
        ("processing", "处理中"),
        ("resolved", "已解决"),
        ("closed", "已关闭"),
        ("cancelled", "已取消"),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="tickets")
    ticket_no = models.CharField(max_length=30, unique=True, db_index=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    type = models.CharField(
        max_length=20,
        choices=[("fault", "故障"), ("request", "需求"), ("internal", "内部请求"), ("change", "变更")],
    )
    priority = models.CharField(
        max_length=20,
        choices=[("critical", "紧急"), ("high", "高"), ("medium", "中"), ("low", "低")],
        default="medium",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True)
    current_node = models.ForeignKey(TicketNode, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    submitter = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="submitted_tickets")
    assignee = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_tickets")
    related_job = models.ForeignKey(InitJob, on_delete=models.SET_NULL, null=True, blank=True, related_name="tickets")
    sla_policy = models.ForeignKey(SLAPolicy, on_delete=models.SET_NULL, null=True, blank=True, related_name="tickets")
    first_response_at = models.DateTimeField(null=True, blank=True, help_text="首次响应时间")
    assigned_at = models.DateTimeField(null=True, blank=True, help_text="首次分派时间")
    resolved_at = models.DateTimeField(null=True, blank=True, help_text="解决时间")
    closed_at = models.DateTimeField(null=True, blank=True, help_text="关闭时间")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "工单"
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["tenant", "-created_at"]),
            models.Index(fields=["assignee", "status"]),
        ]

    def __str__(self):
        return f"{self.ticket_no} {self.title}"


class TicketTransition(models.Model):
    """工单流转记录（不可变）"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="transitions")
    from_node = models.ForeignKey(TicketNode, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    to_node = models.ForeignKey(TicketNode, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    operator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="+")
    comment = models.TextField(blank=True)
    duration_seconds = models.PositiveIntegerField(default=0, help_text="在源节点停留时长（秒）")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "流转记录"

    def __str__(self):
        return f"{self.ticket.ticket_no}: {self.from_node} → {self.to_node}"


class TicketComment(models.Model):
    """工单评论"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="+")
    content = models.TextField()
    is_system = models.BooleanField(default=False, help_text="系统自动评论")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "工单评论"

    def __str__(self):
        return f"Comment by {self.author} on {self.ticket.ticket_no}"


class TicketAttachment(models.Model):
    """工单附件"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to="ticket_attachments/%Y/%m/")
    filename = models.CharField(max_length=255)
    size = models.PositiveIntegerField(help_text="文件大小（字节）")
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "附件"

    def __str__(self):
        return self.filename


class Notification(models.Model):
    """站内通知"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    type = models.CharField(
        max_length=30,
        choices=[
            ("ticket_created", "工单创建"),
            ("ticket_assigned", "工单分派"),
            ("ticket_transition", "工单流转"),
            ("ticket_resolved", "工单解决"),
            ("ticket_closed", "工单关闭"),
            ("sla_warning", "SLA预警"),
            ("sla_violated", "SLA违规"),
            ("ticket_comment", "工单评论"),
        ],
    )
    title = models.CharField(max_length=200)
    content = models.TextField(blank=True)
    ticket = models.ForeignKey(Ticket, on_delete=models.SET_NULL, null=True, blank=True, related_name="notifications")
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "通知"
        indexes = [
            models.Index(fields=["user", "is_read", "-created_at"]),
        ]

    def __str__(self):
        return f"[{self.type}] {self.title}"


class TicketTemplate(models.Model):
    """工单模板（预填表单）"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    ticket_type = models.CharField(
        max_length=20,
        choices=[("fault", "故障"), ("request", "需求"), ("internal", "内部请求"), ("change", "变更")],
    )
    fields = models.JSONField(default=dict, blank=True, help_text="自定义字段定义")
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "-created_at"]
        verbose_name = "工单模板"

    def __str__(self):
        return self.name
