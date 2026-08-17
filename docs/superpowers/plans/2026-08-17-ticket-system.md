# 工单系统实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 SITOP 中新增 `apps/tickets` 模块，实现综合工单系统，支持四种工单类型、可配置流程引擎、SLA 管理和通知系统。

**Architecture:** 方案 A — SITOP 内嵌模块。复用现有多租户、JWT 认证、Celery 基础设施。后端新增 `apps/tickets` Django app，前端新增 `/tickets` 路由和 `TicketsView.vue` 页面。

**Tech Stack:** Django 5.1 + DRF 3.15 + Celery 5 + Redis 7 / Vue 3.5 + Element Plus 2.9 + Pinia 2.3

**Spec:** `docs/superpowers/specs/2026-08-17-ticket-system-design.md`

---

## 文件结构总览

### 后端新增文件

| 文件 | 职责 |
|------|------|
| `backend/apps/tickets/__init__.py` | App 初始化 |
| `backend/apps/tickets/apps.py` | App 配置 |
| `backend/apps/tickets/models.py` | Ticket, TicketFlow, TicketNode, SLAPolicy, TicketTransition, TicketComment, TicketAttachment, Notification |
| `backend/apps/tickets/engine.py` | TicketEngine 流程引擎核心逻辑 |
| `backend/apps/tickets/sla.py` | SLA 检查与升级逻辑 |
| `backend/apps/tickets/serializers.py` | DRF 序列化器 |
| `backend/apps/tickets/views.py` | DRF 视图 |
| `backend/apps/tickets/urls.py` | URL 路由 |
| `backend/apps/tickets/notifications.py` | 通知发送逻辑 |
| `backend/apps/tickets/celery_tasks.py` | Celery 定时任务（SLA 扫描、邮件发送） |
| `backend/apps/tickets/ticket_no.py` | 工单编号生成器 |
| `backend/apps/tickets/import_export.py` | 工单导入导出（CSV） |
| `backend/tests/test_tickets.py` | 工单模块测试 |

### 知识库模块新增文件

| 文件 | 职责 |
|------|------|
| `backend/apps/kb/__init__.py` | App 初始化 |
| `backend/apps/kb/apps.py` | App 配置 |
| `backend/apps/kb/models.py` | Article, ArticleCategory |
| `backend/apps/kb/serializers.py` | DRF 序列化器 |
| `backend/apps/kb/views.py` | DRF 视图 |
| `backend/apps/kb/urls.py` | URL 路由 |
| `backend/tests/test_kb.py` | 知识库测试 |

### 后端修改文件

| 文件 | 修改内容 |
|------|----------|
| `backend/apps/accounts/models.py` | User.role 新增 choices |
| `backend/apps/accounts/permissions.py` | 新增企业角色权限类 |
| `backend/config/settings/base.py` | INSTALLED_APPS 新增 `apps.tickets` 和 `apps.kb` |
| `backend/config/urls.py` | 新增 tickets、notifications 和 kb URL |
| `backend/config/celery.py` | 注册 SLA 扫描定时任务 |
| `backend/tests/conftest.py` | 新增工单相关 fixture |

### 前端新增文件

| 文件 | 职责 |
|------|------|
| `frontend/src/api/tickets.ts` | 工单 API 封装 |
| `frontend/src/api/kb.ts` | 知识库 API 封装 |
| `frontend/src/views/TicketsView.vue` | 工单列表页 |
| `frontend/src/views/TicketDetailView.vue` | 工单详情页 |
| `frontend/src/views/KnowledgeBaseView.vue` | 知识库首页 |
| `frontend/src/views/ArticleDetailView.vue` | 文章详情页 |

### 前端修改文件

| 文件 | 修改内容 |
|------|----------|
| `frontend/src/router/index.ts` | 新增 tickets 和 kb 路由 |
| `frontend/src/components/AppLayout.vue` | 新增工单菜单、通知铃铛、角色菜单控制 |
| `frontend/src/stores/auth.ts` | 新增角色判断辅助方法 |

---

## Task 1: 扩展用户角色体系

**Files:**
- Modify: `backend/apps/accounts/models.py:27-31`
- Modify: `backend/apps/accounts/permissions.py`
- Test: `backend/tests/test_tickets.py`

- [ ] **Step 1: 编写角色扩展测试**

```python
# backend/tests/test_tickets.py
import pytest
from apps.accounts.models import Tenant, User


@pytest.mark.django_db
class TestRoleExtension:
    def test_platform_admin_role_exists(self):
        tenant = Tenant.objects.create(name="ICT公司")
        # admin 角色即平台管理员（向后兼容，保留 admin 值）
        user = User.objects.create_user(
            username="plat_admin", password="pass", tenant=tenant, role="admin"
        )
        assert user.role == "admin"
        assert user.get_role_display() == "平台管理员"

    def test_enterprise_admin_role_exists(self):
        tenant = Tenant.objects.create(name="客户企业A")
        user = User.objects.create_user(
            username="ent_admin", password="pass", tenant=tenant, role="enterprise_admin"
        )
        assert user.role == "enterprise_admin"

    def test_enterprise_user_role_exists(self):
        tenant = Tenant.objects.create(name="客户企业B")
        user = User.objects.create_user(
            username="ent_user", password="pass", tenant=tenant, role="enterprise_user"
        )
        assert user.role == "enterprise_user"

    def test_operator_role_still_works(self):
        """向后兼容：operator 角色仍然可用"""
        tenant = Tenant.objects.create(name="测试租户")
        user = User.objects.create_user(
            username="op", password="pass", tenant=tenant, role="operator"
        )
        assert user.role == "operator"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && python -m pytest tests/test_tickets.py::TestRoleExtension -v
```

Expected: FAIL — `platform_admin` 等角色不在 choices 中

- [ ] **Step 3: 修改 User.role choices**

> **向后兼容策略：** 保留 `admin` 作为内部值（现有代码中大量使用 `role == "admin"`），仅新增 `enterprise_admin` 和 `enterprise_user`。`admin` 的显示名称改为"平台管理员"。

```python
# backend/apps/accounts/models.py — 修改 User 类的 role 字段
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
```

- [ ] **Step 4: 更新权限类**

```python
# backend/apps/accounts/permissions.py — 在文件末尾追加
class IsEnterpriseAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "enterprise_admin"


class IsICTStaff(BasePermission):
    """ICT 内部员工（admin / operator / viewer）"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in (
            "admin", "operator", "viewer"
        )


class IsEnterpriseUser(BasePermission):
    """企业用户（enterprise_admin / enterprise_user）"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in (
            "enterprise_admin", "enterprise_user"
        )


class WriteRequiresOperatorOrAbove(BasePermission):
    """GET/HEAD/OPTIONS allowed for all authenticated; writes require ICT staff or enterprise_admin."""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.role in ("admin", "operator", "enterprise_admin")
```

- [ ] **Step 5: 生成并应用 migration**

```bash
cd backend && python manage.py makemigrations accounts --name extend_user_roles
cd backend && python manage.py migrate
```

- [ ] **Step 6: 运行测试确认通过**

```bash
cd backend && python -m pytest tests/test_tickets.py::TestRoleExtension -v
```

Expected: PASS

- [ ] **Step 7: 提交**

```bash
git add backend/apps/accounts/models.py backend/apps/accounts/permissions.py backend/tests/test_tickets.py backend/apps/accounts/migrations/
git commit -m "feat(accounts): extend user roles for ticket system (platform_admin, enterprise_admin, enterprise_user)"
```

---

## Task 2: 创建工单数据模型

**Files:**
- Create: `backend/apps/tickets/__init__.py`
- Create: `backend/apps/tickets/apps.py`
- Create: `backend/apps/tickets/models.py`
- Modify: `backend/config/settings/base.py:28-34`
- Test: `backend/tests/test_tickets.py`

- [ ] **Step 1: 创建 tickets app 骨架**

```python
# backend/apps/tickets/__init__.py
# (空文件)
```

```python
# backend/apps/tickets/apps.py
from django.apps import AppConfig


class TicketsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.tickets"
    verbose_name = "工单管理"
```

- [ ] **Step 2: 编写模型测试**

```python
# backend/tests/test_tickets.py — 在 TestRoleExtension 后追加
from apps.tickets.models import (
    Ticket, TicketFlow, TicketNode, SLAPolicy,
    TicketTransition, TicketComment, TicketAttachment, Notification,
)


@pytest.mark.django_db
class TestTicketModels:
    def test_create_sla_policy(self):
        policy = SLAPolicy.objects.create(
            name="紧急工单SLA",
            priority="critical",
            response_minutes=30,
            resolve_minutes=240,
            escalation_rules={"response_timeout": [{"minutes": 30, "action": "notify_assignee"}]},
        )
        assert policy.name == "紧急工单SLA"
        assert policy.response_minutes == 30

    def test_create_ticket_flow_with_nodes(self):
        flow = TicketFlow.objects.create(name="标准故障流程", ticket_type="fault")
        node1 = TicketNode.objects.create(flow=flow, name="一线受理", order=1, role_required="operator", sla_hours=2)
        node2 = TicketNode.objects.create(flow=flow, name="二线处理", order=2, role_required="platform_admin", sla_hours=4)
        assert flow.nodes.count() == 2
        assert node1.order < node2.order

    def test_create_ticket(self):
        tenant = Tenant.objects.create(name="测试企业")
        submitter = User.objects.create_user(username="submitter", password="pass", tenant=tenant, role="enterprise_user")
        flow = TicketFlow.objects.create(name="故障流程", ticket_type="fault")
        node = TicketNode.objects.create(flow=flow, name="受理", order=1, role_required="operator")
        policy = SLAPolicy.objects.create(name="默认SLA", priority="medium", response_minutes=60, resolve_minutes=480)

        ticket = Ticket.objects.create(
            tenant=tenant,
            ticket_no="TK-20260817-0001",
            title="数据库连接超时",
            description="生产环境数据库连接池耗尽",
            type="fault",
            priority="high",
            status="pending",
            current_node=node,
            submitter=submitter,
            sla_policy=policy,
        )
        assert ticket.status == "pending"
        assert ticket.submitter == submitter

    def test_ticket_transition_record(self):
        tenant = Tenant.objects.create(name="测试企业")
        flow = TicketFlow.objects.create(name="流程", ticket_type="fault")
        node1 = TicketNode.objects.create(flow=flow, name="受理", order=1, role_required="operator")
        node2 = TicketNode.objects.create(flow=flow, name="处理", order=2, role_required="operator")
        user = User.objects.create_user(username="op1", password="pass", tenant=tenant, role="operator")
        ticket = Ticket.objects.create(
            tenant=tenant, ticket_no="TK-20260817-0002", title="测试",
            type="fault", priority="medium", status="pending",
            current_node=node1, submitter=user,
            sla_policy=SLAPolicy.objects.create(name="SLA", priority="medium", response_minutes=60, resolve_minutes=480),
        )
        transition = TicketTransition.objects.create(
            ticket=ticket, from_node=node1, to_node=node2,
            operator=user, comment="开始处理", duration_seconds=300,
        )
        assert transition.from_node == node1
        assert transition.to_node == node2

    def test_notification_model(self):
        tenant = Tenant.objects.create(name="测试企业")
        user = User.objects.create_user(username="notify_user", password="pass", tenant=tenant)
        notif = Notification.objects.create(
            user=user, type="ticket_created", title="工单已创建",
            content="您的工单 TK-20260817-0001 已创建",
        )
        assert not notif.is_read
        assert notif.user == user
```

- [ ] **Step 3: 运行测试确认失败**

```bash
cd backend && python -m pytest tests/test_tickets.py::TestTicketModels -v
```

Expected: FAIL — `apps.tickets` 不存在

- [ ] **Step 4: 编写模型代码**

```python
# backend/apps/tickets/models.py
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
            ("platform_admin", "平台管理员"),
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
```

- [ ] **Step 5: 注册 app 到 INSTALLED_APPS**

```python
# backend/config/settings/base.py — 在 INSTALLED_APPS 的 Local 部分追加
INSTALLED_APPS = [
    # ...
    # Local
    "apps.accounts",
    "apps.servers",
    "apps.executor",
    "apps.scripts",
    "apps.tasks",
    "apps.reports",
    "apps.repository",
    "apps.tickets",  # 新增
]
```

- [ ] **Step 6: 生成并运行 migration**

```bash
cd backend && python manage.py makemigrations tickets
cd backend && python manage.py migrate
```

- [ ] **Step 7: 运行测试确认通过**

```bash
cd backend && python -m pytest tests/test_tickets.py::TestTicketModels -v
```

Expected: PASS

- [ ] **Step 8: 提交**

```bash
git add backend/apps/tickets/ backend/config/settings/base.py backend/tests/test_tickets.py
git commit -m "feat(tickets): add ticket data models (Ticket, TicketFlow, TicketNode, SLAPolicy, etc.)"
```

---

## Task 3: 工单编号生成器

**Files:**
- Create: `backend/apps/tickets/ticket_no.py`
- Test: `backend/tests/test_tickets.py`

- [ ] **Step 1: 编写测试**

```python
# backend/tests/test_tickets.py — 追加
from apps.tickets.ticket_no import generate_ticket_no


@pytest.mark.django_db
class TestTicketNo:
    def test_generate_first_ticket_of_day(self):
        no = generate_ticket_no()
        assert no.startswith("TK-")
        assert len(no) == 17  # TK-YYYYMMDD-XXXX

    def test_sequential_numbers(self):
        no1 = generate_ticket_no()
        no2 = generate_ticket_no()
        # 序号递增
        seq1 = int(no1.split("-")[-1])
        seq2 = int(no2.split("-")[-1])
        assert seq2 == seq1 + 1
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && python -m pytest tests/test_tickets.py::TestTicketNo -v
```

- [ ] **Step 3: 实现工单编号生成器**

```python
# backend/apps/tickets/ticket_no.py
from datetime import date
from django.core.cache import cache


def generate_ticket_no() -> str:
    """生成工单编号 TK-{YYYYMMDD}-{4位序号}，使用 Redis 原子递增"""
    today = date.today().strftime("%Y%m%d")
    cache_key = f"ticket_no:{today}"
    # 使用 cache (Redis) 原子递增，设置 48 小时过期
    seq = cache.incr(cache_key)
    cache.expire(cache_key, 48 * 3600)
    return f"TK-{today}-{seq:04d}"
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend && python -m pytest tests/test_tickets.py::TestTicketNo -v
```

- [ ] **Step 5: 提交**

```bash
git add backend/apps/tickets/ticket_no.py backend/tests/test_tickets.py
git commit -m "feat(tickets): add ticket number generator with Redis atomic increment"
```

---

## Task 4: 流程引擎核心逻辑

**Files:**
- Create: `backend/apps/tickets/engine.py`
- Test: `backend/tests/test_tickets.py`

- [ ] **Step 1: 编写引擎测试**

```python
# backend/tests/test_tickets.py — 追加
from apps.tickets.engine import TicketEngine


@pytest.mark.django_db
class TestTicketEngine:
    @pytest.fixture
    def setup(self):
        tenant = Tenant.objects.create(name="测试企业")
        submitter = User.objects.create_user(username="sub", password="pass", tenant=tenant, role="enterprise_user")
        handler = User.objects.create_user(username="handler", password="pass", tenant=tenant, role="operator")
        flow = TicketFlow.objects.create(name="故障流程", ticket_type="fault")
        node1 = TicketNode.objects.create(flow=flow, name="一线受理", order=1, role_required="operator", auto_assign_rule="manual")
        node2 = TicketNode.objects.create(flow=flow, name="处理中", order=2, role_required="operator")
        node3 = TicketNode.objects.create(flow=flow, name="已解决", order=3, role_required="operator", is_terminal=True)
        policy = SLAPolicy.objects.create(name="默认SLA", priority="high", response_minutes=60, resolve_minutes=480)
        engine = TicketEngine()
        return {
            "tenant": tenant, "submitter": submitter, "handler": handler,
            "flow": flow, "node1": node1, "node2": node2, "node3": node3,
            "policy": policy, "engine": engine,
        }

    def test_create_ticket(self, setup):
        ticket = setup["engine"].create_ticket(
            data={"title": "数据库超时", "description": "连接池耗尽", "type": "fault", "priority": "high"},
            submitter=setup["submitter"],
        )
        assert ticket.status == "pending"
        assert ticket.current_node == setup["node1"]
        assert ticket.sla_policy == setup["policy"]
        assert ticket.ticket_no.startswith("TK-")

    def test_assign_ticket(self, setup):
        ticket = setup["engine"].create_ticket(
            data={"title": "测试", "type": "fault", "priority": "high"},
            submitter=setup["submitter"],
        )
        setup["engine"].assign(ticket, setup["handler"], setup["handler"])
        ticket.refresh_from_db()
        assert ticket.status == "assigned"
        assert ticket.assignee == setup["handler"]
        assert ticket.assigned_at is not None

    def test_transition_ticket(self, setup):
        ticket = setup["engine"].create_ticket(
            data={"title": "测试", "type": "fault", "priority": "high"},
            submitter=setup["submitter"],
        )
        setup["engine"].assign(ticket, setup["handler"], setup["handler"])
        setup["engine"].transition(ticket, setup["node2"], setup["handler"], comment="开始排查")
        ticket.refresh_from_db()
        assert ticket.status == "processing"
        assert ticket.current_node == setup["node2"]
        assert ticket.transitions.count() == 2

    def test_resolve_ticket(self, setup):
        ticket = setup["engine"].create_ticket(
            data={"title": "测试", "type": "fault", "priority": "high"},
            submitter=setup["submitter"],
        )
        setup["engine"].assign(ticket, setup["handler"], setup["handler"])
        setup["engine"].resolve(ticket, setup["handler"], "已修复连接池配置")
        ticket.refresh_from_db()
        assert ticket.status == "resolved"
        assert ticket.resolved_at is not None

    def test_cancel_ticket(self, setup):
        ticket = setup["engine"].create_ticket(
            data={"title": "测试", "type": "fault", "priority": "high"},
            submitter=setup["submitter"],
        )
        setup["engine"].cancel(ticket, setup["submitter"], "问题已自行解决")
        ticket.refresh_from_db()
        assert ticket.status == "cancelled"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && python -m pytest tests/test_tickets.py::TestTicketEngine -v
```

- [ ] **Step 3: 实现流程引擎**

```python
# backend/apps/tickets/engine.py
from django.utils import timezone
from django.db.models import Count, Q
from .models import Ticket, TicketFlow, TicketNode, TicketTransition, TicketComment, SLAPolicy
from .ticket_no import generate_ticket_no


class TicketEngine:
    """工单流程引擎"""

    def create_ticket(self, data: dict, submitter) -> Ticket:
        """创建工单，绑定流程模板，初始化 SLA"""
        ticket_type = data["type"]
        priority = data.get("priority", "medium")

        # 查找匹配的流程模板
        flow = TicketFlow.objects.filter(
            ticket_type=ticket_type, is_active=True,
        ).filter(
            Q(tenant=submitter.tenant) | Q(tenant__isnull=True)
        ).first()

        # 查找匹配的 SLA 策略
        sla_policy = SLAPolicy.objects.filter(priority=priority).first()

        # 获取第一个节点
        first_node = None
        if flow:
            first_node = flow.nodes.order_by("order").first()

        ticket = Ticket.objects.create(
            tenant=submitter.tenant,
            ticket_no=generate_ticket_no(),
            title=data["title"],
            description=data.get("description", ""),
            type=ticket_type,
            priority=priority,
            status="pending",
            current_node=first_node,
            submitter=submitter,
            sla_policy=sla_policy,
            related_job_id=data.get("related_job_id"),
        )

        # 创建系统评论
        TicketComment.objects.create(
            ticket=ticket, author=submitter,
            content=f"工单已创建，类型：{ticket.get_type_display()}",
            is_system=True,
        )

        return ticket

    def assign(self, ticket: Ticket, assignee, operator) -> None:
        """分派工单"""
        now = timezone.now()
        ticket.assignee = assignee
        ticket.status = "assigned"
        if not ticket.assigned_at:
            ticket.assigned_at = now
        if not ticket.first_response_at:
            ticket.first_response_at = now
        ticket.save(update_fields=["assignee", "status", "assigned_at", "first_response_at", "updated_at"])

        # 记录流转
        TicketTransition.objects.create(
            ticket=ticket,
            from_node=ticket.current_node,
            to_node=ticket.current_node,
            operator=operator,
            comment=f"分派给 {assignee.username}",
        )

    def transition(self, ticket: Ticket, target_node: TicketNode, operator, comment: str = "") -> None:
        """流转到下一个节点"""
        now = timezone.now()
        old_node = ticket.current_node

        # 计算在源节点停留时长
        duration = 0
        last_transition = ticket.transitions.order_by("-created_at").first()
        if last_transition:
            duration = int((now - last_transition.created_at).total_seconds())

        ticket.current_node = target_node
        # 根据目标节点设置状态
        if target_node.is_terminal:
            ticket.status = "resolved"
        elif ticket.assignee:
            ticket.status = "processing"
        ticket.save(update_fields=["current_node", "status", "updated_at"])

        TicketTransition.objects.create(
            ticket=ticket,
            from_node=old_node,
            to_node=target_node,
            operator=operator,
            comment=comment,
            duration_seconds=duration,
        )

    def resolve(self, ticket: Ticket, operator, resolution: str = "") -> None:
        """解决工单"""
        now = timezone.now()
        ticket.status = "resolved"
        ticket.resolved_at = now
        ticket.save(update_fields=["status", "resolved_at", "updated_at"])

        TicketTransition.objects.create(
            ticket=ticket,
            from_node=ticket.current_node,
            to_node=ticket.current_node,
            operator=operator,
            comment=resolution or "工单已解决",
        )

        TicketComment.objects.create(
            ticket=ticket, author=operator,
            content=resolution or "工单已解决",
            is_system=True,
        )

    def close(self, ticket: Ticket, operator) -> None:
        """关闭工单"""
        ticket.status = "closed"
        ticket.closed_at = timezone.now()
        ticket.save(update_fields=["status", "closed_at", "updated_at"])

        TicketComment.objects.create(
            ticket=ticket, author=operator,
            content="工单已关闭", is_system=True,
        )

    def cancel(self, ticket: Ticket, operator, reason: str = "") -> None:
        """取消工单"""
        if ticket.status in ("resolved", "closed", "cancelled"):
            raise ValueError(f"工单状态 {ticket.status} 不允许取消")

        ticket.status = "cancelled"
        ticket.closed_at = timezone.now()
        ticket.save(update_fields=["status", "closed_at", "updated_at"])

        TicketComment.objects.create(
            ticket=ticket, author=operator,
            content=f"工单已取消：{reason}" if reason else "工单已取消",
            is_system=True,
        )
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend && python -m pytest tests/test_tickets.py::TestTicketEngine -v
```

- [ ] **Step 5: 提交**

```bash
git add backend/apps/tickets/engine.py backend/tests/test_tickets.py
git commit -m "feat(tickets): implement ticket workflow engine (create, assign, transition, resolve, close, cancel)"
```

---

## Task 5: 序列化器与 API 视图

**Files:**
- Create: `backend/apps/tickets/serializers.py`
- Create: `backend/apps/tickets/views.py`
- Create: `backend/apps/tickets/urls.py`
- Modify: `backend/config/urls.py`
- Test: `backend/tests/test_tickets.py`

- [ ] **Step 1: 编写 API 测试**

```python
# backend/tests/test_tickets.py — 追加
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken


@pytest.mark.django_db
class TestTicketAPI:
    @pytest.fixture
    def api_client(self):
        tenant = Tenant.objects.create(name="测试企业")
        user = User.objects.create_user(username="api_user", password="pass", tenant=tenant, role="operator")
        client = APIClient()
        token = RefreshToken.for_user(user)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
        return client, user, tenant

    def test_create_ticket_api(self, api_client):
        client, user, tenant = api_client
        SLAPolicy.objects.create(name="SLA", priority="high", response_minutes=60, resolve_minutes=480)
        TicketFlow.objects.create(name="故障流程", ticket_type="fault")

        resp = client.post("/api/tickets/", {
            "title": "数据库超时",
            "description": "连接池耗尽",
            "type": "fault",
            "priority": "high",
        }, format="json")
        assert resp.status_code == 201
        assert resp.data["ticket_no"].startswith("TK-")
        assert resp.data["status"] == "pending"

    def test_list_tickets_api(self, api_client):
        client, user, tenant = api_client
        # 创建一个工单
        flow = TicketFlow.objects.create(name="流程", ticket_type="fault")
        node = TicketNode.objects.create(flow=flow, name="受理", order=1, role_required="operator")
        policy = SLAPolicy.objects.create(name="SLA", priority="medium", response_minutes=60, resolve_minutes=480)
        Ticket.objects.create(
            tenant=tenant, ticket_no="TK-20260817-0001", title="测试工单",
            type="fault", priority="medium", status="pending",
            current_node=node, submitter=user, sla_policy=policy,
        )
        resp = client.get("/api/tickets/")
        assert resp.status_code == 200
        assert len(resp.data["results"]) >= 1

    def test_ticket_detail_api(self, api_client):
        client, user, tenant = api_client
        flow = TicketFlow.objects.create(name="流程", ticket_type="fault")
        node = TicketNode.objects.create(flow=flow, name="受理", order=1, role_required="operator")
        policy = SLAPolicy.objects.create(name="SLA", priority="medium", response_minutes=60, resolve_minutes=480)
        ticket = Ticket.objects.create(
            tenant=tenant, ticket_no="TK-20260817-0002", title="详情测试",
            type="fault", priority="medium", status="pending",
            current_node=node, submitter=user, sla_policy=policy,
        )
        resp = client.get(f"/api/tickets/{ticket.id}/")
        assert resp.status_code == 200
        assert resp.data["title"] == "详情测试"

    def test_assign_ticket_api(self, api_client):
        client, user, tenant = api_client
        handler = User.objects.create_user(username="handler", password="pass", tenant=tenant, role="operator")
        flow = TicketFlow.objects.create(name="流程", ticket_type="fault")
        node = TicketNode.objects.create(flow=flow, name="受理", order=1, role_required="operator")
        policy = SLAPolicy.objects.create(name="SLA", priority="medium", response_minutes=60, resolve_minutes=480)
        ticket = Ticket.objects.create(
            tenant=tenant, ticket_no="TK-20260817-0003", title="分派测试",
            type="fault", priority="medium", status="pending",
            current_node=node, submitter=user, sla_policy=policy,
        )
        resp = client.post(f"/api/tickets/{ticket.id}/assign/", {"assignee_id": str(handler.id)}, format="json")
        assert resp.status_code == 200
        ticket.refresh_from_db()
        assert ticket.assignee == handler
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && python -m pytest tests/test_tickets.py::TestTicketAPI -v
```

- [ ] **Step 3: 编写序列化器**

```python
# backend/apps/tickets/serializers.py
from rest_framework import serializers
from .models import (
    Ticket, TicketFlow, TicketNode, SLAPolicy,
    TicketTransition, TicketComment, TicketAttachment, Notification,
)


class SLAPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = SLAPolicy
        fields = "__all__"


class TicketNodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = TicketNode
        fields = ["id", "name", "order", "role_required", "is_terminal", "sla_hours", "auto_assign_rule"]


class TicketFlowSerializer(serializers.ModelSerializer):
    nodes = TicketNodeSerializer(many=True, read_only=True)

    class Meta:
        model = TicketFlow
        fields = ["id", "name", "ticket_type", "is_active", "nodes", "created_at"]


class TicketFlowCreateSerializer(serializers.ModelSerializer):
    nodes = TicketNodeSerializer(many=True, required=False)

    class Meta:
        model = TicketFlow
        fields = ["id", "name", "ticket_type", "is_active", "nodes"]

    def create(self, validated_data):
        nodes_data = validated_data.pop("nodes", [])
        flow = TicketFlow.objects.create(**validated_data)
        for node_data in nodes_data:
            TicketNode.objects.create(flow=flow, **node_data)
        return flow


class TicketCommentSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.username", read_only=True)

    class Meta:
        model = TicketComment
        fields = ["id", "author", "author_name", "content", "is_system", "created_at"]
        read_only_fields = ["author", "is_system"]


class TicketTransitionSerializer(serializers.ModelSerializer):
    from_node_name = serializers.CharField(source="from_node.name", read_only=True, default="")
    to_node_name = serializers.CharField(source="to_node.name", read_only=True, default="")
    operator_name = serializers.CharField(source="operator.username", read_only=True)

    class Meta:
        model = TicketTransition
        fields = ["id", "from_node", "from_node_name", "to_node", "to_node_name",
                  "operator", "operator_name", "comment", "duration_seconds", "created_at"]


class TicketListSerializer(serializers.ModelSerializer):
    submitter_name = serializers.CharField(source="submitter.username", read_only=True)
    assignee_name = serializers.CharField(source="assignee.username", read_only=True, default="")
    type_display = serializers.CharField(source="get_type_display", read_only=True)
    priority_display = serializers.CharField(source="get_priority_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Ticket
        fields = [
            "id", "ticket_no", "title", "type", "type_display",
            "priority", "priority_display", "status", "status_display",
            "submitter", "submitter_name", "assignee", "assignee_name",
            "created_at", "updated_at",
        ]


class TicketDetailSerializer(serializers.ModelSerializer):
    submitter_name = serializers.CharField(source="submitter.username", read_only=True)
    assignee_name = serializers.CharField(source="assignee.username", read_only=True, default="")
    type_display = serializers.CharField(source="get_type_display", read_only=True)
    priority_display = serializers.CharField(source="get_priority_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    current_node_name = serializers.CharField(source="current_node.name", read_only=True, default="")
    sla_policy_detail = SLAPolicySerializer(source="sla_policy", read_only=True)
    comments = TicketCommentSerializer(many=True, read_only=True)
    transitions = TicketTransitionSerializer(many=True, read_only=True)

    class Meta:
        model = Ticket
        fields = [
            "id", "ticket_no", "title", "description", "type", "type_display",
            "priority", "priority_display", "status", "status_display",
            "current_node", "current_node_name",
            "submitter", "submitter_name", "assignee", "assignee_name",
            "related_job", "sla_policy_detail",
            "first_response_at", "assigned_at", "resolved_at", "closed_at",
            "created_at", "updated_at",
            "comments", "transitions",
        ]


class TicketCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ticket
        fields = ["title", "description", "type", "priority", "related_job"]


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "type", "title", "content", "ticket", "is_read", "created_at"]
```

- [ ] **Step 4: 编写视图**

```python
# backend/apps/tickets/views.py
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Q
from apps.accounts.permissions import WriteRequiresOperatorOrAbove, IsAdmin
from .models import Ticket, TicketFlow, SLAPolicy, TicketComment, Notification
from .engine import TicketEngine
from .serializers import (
    TicketListSerializer, TicketDetailSerializer, TicketCreateSerializer,
    TicketFlowSerializer, TicketFlowCreateSerializer,
    SLAPolicySerializer, TicketCommentSerializer,
    NotificationSerializer,
)


def get_tenant(request):
    return getattr(request, "tenant", None) or getattr(request.user, "tenant", None)


class TicketListView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return TicketCreateSerializer
        return TicketListSerializer

    def get_queryset(self):
        user = self.request.user
        qs = Ticket.objects.filter(tenant=get_tenant(self.request))
        # 企业员工只能看自己的工单
        if user.role == "enterprise_user":
            qs = qs.filter(submitter=user)
        # 筛选
        ticket_type = self.request.query_params.get("type")
        if ticket_type:
            qs = qs.filter(type=ticket_type)
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        priority = self.request.query_params.get("priority")
        if priority:
            qs = qs.filter(priority=priority)
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(Q(title__icontains=search) | Q(ticket_no__icontains=search))
        return qs.select_related("submitter", "assignee", "current_node")

    def perform_create(self, serializer):
        engine = TicketEngine()
        engine.create_ticket(data=serializer.validated_data, submitter=self.request.user)


class TicketDetailView(generics.RetrieveAPIView):
    serializer_class = TicketDetailSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = Ticket.objects.filter(tenant=get_tenant(self.request))
        if user.role == "enterprise_user":
            qs = qs.filter(submitter=user)
        return qs.select_related("submitter", "assignee", "current_node", "sla_policy")


class TicketAssignView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        ticket = self._get_ticket(pk)
        assignee_id = request.data.get("assignee_id")
        from apps.accounts.models import User
        assignee = User.objects.get(id=assignee_id)
        engine = TicketEngine()
        engine.assign(ticket, assignee, request.user)
        return Response({"status": "assigned"})

    def _get_ticket(self, pk):
        return Ticket.objects.get(pk=pk, tenant=get_tenant(self.request))


class TicketTransitionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        ticket = Ticket.objects.get(pk=pk, tenant=get_tenant(request))
        from .models import TicketNode
        target_node = TicketNode.objects.get(id=request.data.get("node_id"))
        comment = request.data.get("comment", "")
        engine = TicketEngine()
        engine.transition(ticket, target_node, request.user, comment)
        return Response({"status": ticket.status})


class TicketResolveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        ticket = Ticket.objects.get(pk=pk, tenant=get_tenant(request))
        resolution = request.data.get("resolution", "")
        engine = TicketEngine()
        engine.resolve(ticket, request.user, resolution)
        return Response({"status": "resolved"})


class TicketCloseView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        ticket = Ticket.objects.get(pk=pk, tenant=get_tenant(request))
        engine = TicketEngine()
        engine.close(ticket, request.user)
        return Response({"status": "closed"})


class TicketCancelView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        ticket = Ticket.objects.get(pk=pk, tenant=get_tenant(request))
        reason = request.data.get("reason", "")
        engine = TicketEngine()
        engine.cancel(ticket, request.user, reason)
        return Response({"status": "cancelled"})


class TicketCommentView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        ticket = Ticket.objects.get(pk=pk, tenant=get_tenant(request))
        serializer = TicketCommentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(ticket=ticket, author=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class TicketTransitionListView(generics.ListAPIView):
    serializer_class = TicketTransitionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        ticket = Ticket.objects.get(pk=self.kwargs["pk"], tenant=get_tenant(self.request))
        return ticket.transitions.select_related("from_node", "to_node", "operator")


class TicketFlowListView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsAdmin]  # IsAdmin 即平台管理员

    def get_serializer_class(self):
        if self.request.method == "POST":
            return TicketFlowCreateSerializer
        return TicketFlowSerializer

    def get_queryset(self):
        return TicketFlow.objects.filter(
            Q(tenant=get_tenant(self.request)) | Q(tenant__isnull=True)
        ).prefetch_related("nodes")


class SLAPolicyListView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsAdmin]  # IsAdmin 即平台管理员
    serializer_class = SLAPolicySerializer
    queryset = SLAPolicy.objects.all()


class NotificationListView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)[:20]


class NotificationReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        notif = Notification.objects.get(pk=pk, user=request.user)
        notif.is_read = True
        notif.save(update_fields=["is_read"])
        return Response({"status": "read"})


class NotificationReadAllView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({"status": "all_read"})


class NotificationUnreadCountView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        count = Notification.objects.filter(user=request.user, is_read=False).count()
        return Response({"count": count})
```

- [ ] **Step 5: 编写 URL 路由**

```python
# backend/apps/tickets/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path("", views.TicketListView.as_view(), name="ticket-list"),
    path("<uuid:pk>/", views.TicketDetailView.as_view(), name="ticket-detail"),
    path("<uuid:pk>/assign/", views.TicketAssignView.as_view(), name="ticket-assign"),
    path("<uuid:pk>/transition/", views.TicketTransitionView.as_view(), name="ticket-transition"),
    path("<uuid:pk>/resolve/", views.TicketResolveView.as_view(), name="ticket-resolve"),
    path("<uuid:pk>/close/", views.TicketCloseView.as_view(), name="ticket-close"),
    path("<uuid:pk>/cancel/", views.TicketCancelView.as_view(), name="ticket-cancel"),
    path("<uuid:pk>/comments/", views.TicketCommentView.as_view(), name="ticket-comment"),
    path("<uuid:pk>/transitions/", views.TicketTransitionListView.as_view(), name="ticket-transitions"),
    path("flows/", views.TicketFlowListView.as_view(), name="ticket-flow-list"),
    path("sla-policies/", views.SLAPolicyListView.as_view(), name="sla-policy-list"),
]
```

- [ ] **Step 6: 注册 URL 到主路由**

```python
# backend/config/urls.py
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/", include("apps.servers.urls")),
    path("api/", include("apps.executor.urls")),
    path("api/scripts/", include("apps.scripts.urls")),
    path("api/", include("apps.tasks.urls")),
    path("api/", include("apps.reports.urls")),
    path("api/", include("apps.repository.urls")),
    # 新增
    path("api/tickets/", include("apps.tickets.urls")),
    path("api/notifications/", include("apps.tickets.notification_urls")),
]
```

- [ ] **Step 7: 创建通知 URL 路由文件**

```python
# backend/apps/tickets/notification_urls.py
from django.urls import path
from . import views

urlpatterns = [
    path("", views.NotificationListView.as_view(), name="notification-list"),
    path("<uuid:pk>/read/", views.NotificationReadView.as_view(), name="notification-read"),
    path("read-all/", views.NotificationReadAllView.as_view(), name="notification-read-all"),
    path("unread-count/", views.NotificationUnreadCountView.as_view(), name="notification-unread-count"),
]
```

- [ ] **Step 8: 运行测试确认通过**

```bash
cd backend && python -m pytest tests/test_tickets.py::TestTicketAPI -v
```

- [ ] **Step 9: 提交**

```bash
git add backend/apps/tickets/ backend/config/urls.py backend/tests/test_tickets.py
git commit -m "feat(tickets): add ticket API endpoints (CRUD, assign, transition, resolve, close, cancel, comments)"
```

---

## Task 6: SLA 管理与 Celery 定时任务

**Files:**
- Create: `backend/apps/tickets/sla.py`
- Create: `backend/apps/tickets/celery_tasks.py`
- Modify: `backend/config/celery.py`
- Test: `backend/tests/test_tickets.py`

- [ ] **Step 1: 编写 SLA 测试**

```python
# backend/tests/test_tickets.py — 追加
from apps.tickets.sla import check_sla_timeouts


@pytest.mark.django_db
class TestSLA:
    def test_sla_warning_at_50_percent(self):
        """SLA 达到 50% 时应标记预警"""
        tenant = Tenant.objects.create(name="SLA测试")
        user = User.objects.create_user(username="sla_user", password="pass", tenant=tenant, role="operator")
        policy = SLAPolicy.objects.create(
            name="紧急SLA", priority="critical",
            response_minutes=60, resolve_minutes=240,
            escalation_rules={},
        )
        flow = TicketFlow.objects.create(name="流程", ticket_type="fault")
        node = TicketNode.objects.create(flow=flow, name="受理", order=1, role_required="operator")
        # 创建一个 35 分钟前提交的工单（已超过 50% 的 60 分钟时限）
        from django.utils import timezone
        from datetime import timedelta
        ticket = Ticket.objects.create(
            tenant=tenant, ticket_no="TK-SLA-0001", title="SLA测试",
            type="fault", priority="critical", status="pending",
            current_node=node, submitter=user, sla_policy=policy,
        )
        # 手动设置 created_at 为 35 分钟前
        Ticket.objects.filter(pk=ticket.pk).update(
            created_at=timezone.now() - timedelta(minutes=35)
        )
        # 运行 SLA 检查
        check_sla_timeouts()
        # 应该生成预警通知
        assert Notification.objects.filter(user=user, type="sla_warning").exists()
```

- [ ] **Step 2: 实现 SLA 检查逻辑**

```python
# backend/apps/tickets/sla.py
from django.utils import timezone
from datetime import timedelta
from .models import Ticket, Notification


def check_sla_timeouts():
    """检查所有未关闭工单的 SLA 状态，生成预警和违规通知"""
    now = timezone.now()
    open_tickets = Ticket.objects.filter(
        status__in=["pending", "assigned", "processing"]
    ).select_related("sla_policy", "submitter", "assignee")

    for ticket in open_tickets:
        if not ticket.sla_policy:
            continue

        policy = ticket.sla_policy

        # 检查响应 SLA
        if not ticket.first_response_at:
            response_deadline = ticket.created_at + timedelta(minutes=policy.response_minutes)
            elapsed = (now - ticket.created_at).total_seconds() / 60
            total = policy.response_minutes

            if elapsed >= total:
                # SLA 违规
                _create_notification(ticket, "sla_violated",
                    f"工单 {ticket.ticket_no} 响应 SLA 已超时",
                    f"响应时限 {policy.response_minutes} 分钟，已超时 {int(elapsed - total)} 分钟")
            elif elapsed >= total * 0.8:
                _create_notification(ticket, "sla_warning",
                    f"工单 {ticket.ticket_no} 响应 SLA 即将超时",
                    f"已用 {int(elapsed)} 分钟，时限 {policy.response_minutes} 分钟")

        # 检查处理 SLA（从分派开始计算）
        if ticket.assigned_at and not ticket.resolved_at:
            resolve_deadline = ticket.assigned_at + timedelta(minutes=policy.resolve_minutes)
            elapsed = (now - ticket.assigned_at).total_seconds() / 60
            total = policy.resolve_minutes

            if elapsed >= total:
                _create_notification(ticket, "sla_violated",
                    f"工单 {ticket.ticket_no} 处理 SLA 已超时",
                    f"处理时限 {policy.resolve_minutes} 分钟，已超时 {int(elapsed - total)} 分钟")
            elif elapsed >= total * 0.8:
                _create_notification(ticket, "sla_warning",
                    f"工单 {ticket.ticket_no} 处理 SLA 即将超时",
                    f"已用 {int(elapsed)} 分钟，时限 {policy.resolve_minutes} 分钟")


def _create_notification(ticket, notif_type, title, content):
    """创建通知（避免重复）"""
    # 同一工单同一类型 1 小时内不重复通知
    from datetime import timedelta
    recent = Notification.objects.filter(
        ticket=ticket, type=notif_type,
        created_at__gte=timezone.now() - timedelta(hours=1),
    ).exists()
    if recent:
        return

    # 通知处理人（如果有）或提交人
    target_user = ticket.assignee or ticket.submitter
    if target_user:
        Notification.objects.create(
            user=target_user, type=notif_type,
            title=title, content=content, ticket=ticket,
        )
```

- [ ] **Step 3: 编写 Celery 定时任务**

```python
# backend/apps/tickets/celery_tasks.py
from celery import shared_task
from .sla import check_sla_timeouts


@shared_task
def task_check_sla_timeouts():
    """Celery Beat 定时调用的 SLA 检查任务"""
    check_sla_timeouts()
```

- [ ] **Step 4: 注册 Celery Beat 定时任务**

```python
# backend/config/celery.py — 在文件末尾的 beat_schedule 中追加
from celery.schedules import crontab

app.conf.beat_schedule = {
    # ... 现有任务 ...
    "check-sla-timeouts": {
        "task": "apps.tickets.celery_tasks.task_check_sla_timeouts",
        "schedule": 300.0,  # 每 5 分钟
    },
}
```

- [ ] **Step 5: 运行测试**

```bash
cd backend && python -m pytest tests/test_tickets.py::TestSLA -v
```

- [ ] **Step 6: 提交**

```bash
git add backend/apps/tickets/sla.py backend/apps/tickets/celery_tasks.py backend/config/celery.py backend/tests/test_tickets.py
git commit -m "feat(tickets): add SLA management with Celery Beat periodic checks"
```

---

## Task 7: 前端 — API 封装与路由

**Files:**
- Create: `frontend/src/api/tickets.ts`
- Modify: `frontend/src/router/index.ts`

- [ ] **Step 1: 创建工单 API 封装**

```typescript
// frontend/src/api/tickets.ts
import request from './request'

export interface Ticket {
  id: string
  ticket_no: string
  title: string
  description?: string
  type: 'fault' | 'request' | 'internal' | 'change'
  type_display: string
  priority: 'critical' | 'high' | 'medium' | 'low'
  priority_display: string
  status: string
  status_display: string
  submitter: string
  submitter_name: string
  assignee: string | null
  assignee_name: string
  current_node?: string
  current_node_name?: string
  related_job?: string | null
  first_response_at?: string
  assigned_at?: string
  resolved_at?: string
  closed_at?: string
  created_at: string
  updated_at: string
  comments?: TicketComment[]
  transitions?: TicketTransition[]
  sla_policy_detail?: SLAPolicy
}

export interface TicketComment {
  id: string
  author: string
  author_name: string
  content: string
  is_system: boolean
  created_at: string
}

export interface TicketTransition {
  id: string
  from_node: string | null
  from_node_name: string
  to_node: string | null
  to_node_name: string
  operator: string
  operator_name: string
  comment: string
  duration_seconds: number
  created_at: string
}

export interface SLAPolicy {
  id: string
  name: string
  priority: string
  response_minutes: number
  resolve_minutes: number
}

export interface TicketFlow {
  id: string
  name: string
  ticket_type: string
  is_active: boolean
  nodes: TicketFlowNode[]
  created_at: string
}

export interface TicketFlowNode {
  id: string
  name: string
  order: number
  role_required: string
  is_terminal: boolean
  sla_hours: number
  auto_assign_rule: string
}

export interface Notification {
  id: string
  type: string
  title: string
  content: string
  ticket: string | null
  is_read: boolean
  created_at: string
}

export const ticketsApi = {
  list(params?: { type?: string; status?: string; priority?: string; search?: string; page?: number }) {
    return request.get('/tickets/', { params })
  },
  get(id: string) {
    return request.get<Ticket>(`/tickets/${id}/`)
  },
  create(data: { title: string; description?: string; type: string; priority: string; related_job?: string }) {
    return request.post<Ticket>('/tickets/', data)
  },
  assign(id: string, assigneeId: string) {
    return request.post(`/tickets/${id}/assign/`, { assignee_id: assigneeId })
  },
  transition(id: string, nodeId: string, comment?: string) {
    return request.post(`/tickets/${id}/transition/`, { node_id: nodeId, comment })
  },
  resolve(id: string, resolution?: string) {
    return request.post(`/tickets/${id}/resolve/`, { resolution })
  },
  close(id: string) {
    return request.post(`/tickets/${id}/close/`)
  },
  cancel(id: string, reason?: string) {
    return request.post(`/tickets/${id}/cancel/`, { reason })
  },
  addComment(id: string, content: string) {
    return request.post(`/tickets/${id}/comments/`, { content })
  },
  getTransitions(id: string) {
    return request.get<TicketTransition[]>(`/tickets/${id}/transitions/`)
  },
  // 流程模板
  listFlows() {
    return request.get<TicketFlow[]>('/tickets/flows/')
  },
  createFlow(data: Partial<TicketFlow>) {
    return request.post('/tickets/flows/', data)
  },
  // SLA 策略
  listSLAPolicies() {
    return request.get<SLAPolicy[]>('/tickets/sla-policies/')
  },
  createSLAPolicy(data: Partial<SLAPolicy>) {
    return request.post('/tickets/sla-policies/', data)
  },
}

export const notificationsApi = {
  list() {
    return request.get<Notification[]>('/notifications/')
  },
  markRead(id: string) {
    return request.post(`/notifications/${id}/read/`)
  },
  markAllRead() {
    return request.post('/notifications/read-all/')
  },
  unreadCount() {
    return request.get<{ count: number }>('/notifications/unread-count/')
  },
}
```

- [ ] **Step 2: 添加路由**

```typescript
// frontend/src/router/index.ts — 在 routes 数组中追加
{
  path: '/tickets',
  name: 'tickets',
  component: () => import('@/views/TicketsView.vue'),
  meta: { requiresAuth: true },
},
{
  path: '/tickets/create',
  name: 'ticket-create',
  component: () => import('@/views/TicketDetailView.vue'),
  meta: { requiresAuth: true },
},
{
  path: '/tickets/:id',
  name: 'ticket-detail',
  component: () => import('@/views/TicketDetailView.vue'),
  meta: { requiresAuth: true },
},
```

- [ ] **Step 3: 提交**

```bash
git add frontend/src/api/tickets.ts frontend/src/router/index.ts
git commit -m "feat(frontend): add ticket API client and routes"
```

---

## Task 8: 前端 — 工单列表页

**Files:**
- Create: `frontend/src/views/TicketsView.vue`

- [ ] **Step 1: 创建工单列表页**

参考现有 `JobsView.vue` 的风格，创建工单列表页，包含：
- 顶部筛选栏（类型、优先级、状态、搜索）
- 表格展示（编号、标题、类型标签、优先级标签、状态标签、提交人、处理人、创建时间）
- 创建工单按钮
- 分页

```vue
<!-- frontend/src/views/TicketsView.vue -->
<template>
  <AppLayout>
    <div class="tickets-page">
      <div class="page-header">
        <h2>工单管理</h2>
        <el-button type="primary" @click="$router.push('/tickets/create')">创建工单</el-button>
      </div>

      <!-- 筛选栏 -->
      <el-form :inline="true" class="filter-bar">
        <el-form-item label="类型">
          <el-select v-model="filters.type" clearable placeholder="全部" @change="fetchTickets">
            <el-option label="故障" value="fault" />
            <el-option label="需求" value="request" />
            <el-option label="内部请求" value="internal" />
            <el-option label="变更" value="change" />
          </el-select>
        </el-form-item>
        <el-form-item label="优先级">
          <el-select v-model="filters.priority" clearable placeholder="全部" @change="fetchTickets">
            <el-option label="紧急" value="critical" />
            <el-option label="高" value="high" />
            <el-option label="中" value="medium" />
            <el-option label="低" value="low" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="filters.status" clearable placeholder="全部" @change="fetchTickets">
            <el-option label="待受理" value="pending" />
            <el-option label="已分派" value="assigned" />
            <el-option label="处理中" value="processing" />
            <el-option label="已解决" value="resolved" />
            <el-option label="已关闭" value="closed" />
            <el-option label="已取消" value="cancelled" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-input v-model="filters.search" placeholder="搜索标题/编号" clearable @clear="fetchTickets" @keyup.enter="fetchTickets" />
        </el-form-item>
      </el-form>

      <!-- 工单表格 -->
      <el-table :data="tickets" v-loading="loading" stripe @row-click="goDetail">
        <el-table-column prop="ticket_no" label="工单编号" width="180" />
        <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
        <el-table-column prop="type_display" label="类型" width="100">
          <template #default="{ row }">
            <el-tag :type="typeTagMap[row.type]" size="small">{{ row.type_display }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="priority_display" label="优先级" width="90">
          <template #default="{ row }">
            <el-tag :type="priorityTagMap[row.priority]" size="small" effect="dark">{{ row.priority_display }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status_display" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTagMap[row.status]" size="small">{{ row.status_display }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="submitter_name" label="提交人" width="100" />
        <el-table-column prop="assignee_name" label="处理人" width="100">
          <template #default="{ row }">{{ row.assignee_name || '-' }}</template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="170">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <el-pagination
        v-model:current-page="page"
        :page-size="20"
        :total="total"
        layout="total, prev, pager, next"
        @current-change="fetchTickets"
        style="margin-top: 16px; justify-content: flex-end;"
      />
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import AppLayout from '@/components/AppLayout.vue'
import { ticketsApi, type Ticket } from '@/api/tickets'

const router = useRouter()
const loading = ref(false)
const tickets = ref<Ticket[]>([])
const total = ref(0)
const page = ref(1)
const filters = ref({ type: '', priority: '', status: '', search: '' })

const typeTagMap: Record<string, string> = { fault: 'danger', request: 'primary', internal: 'info', change: 'warning' }
const priorityTagMap: Record<string, string> = { critical: 'danger', high: 'warning', medium: '', low: 'info' }
const statusTagMap: Record<string, string> = { pending: 'info', assigned: '', processing: 'warning', resolved: 'success', closed: 'info', cancelled: 'info' }

function formatDate(d: string) {
  return new Date(d).toLocaleString('zh-CN')
}

async function fetchTickets() {
  loading.value = true
  try {
    const { data } = await ticketsApi.list({ ...filters.value, page: page.value })
    tickets.value = data.results || data
    total.value = data.count || tickets.value.length
  } finally {
    loading.value = false
  }
}

function goDetail(row: Ticket) {
  router.push(`/tickets/${row.id}`)
}

onMounted(fetchTickets)
</script>

<style scoped>
.tickets-page { max-width: 1400px; margin: 0 auto; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.filter-bar { margin-bottom: 16px; }
</style>
```

- [ ] **Step 3: 提交**

```bash
git add frontend/src/views/TicketsView.vue
git commit -m "feat(frontend): add ticket list page with filters and pagination"
```

---

## Task 9: 前端 — 工单详情页

**Files:**
- Create: `frontend/src/views/TicketDetailView.vue`

- [ ] **Step 1: 创建工单详情页**

参考设计文档中的布局，实现：
- 工单基本信息展示
- 流程进度条
- SLA 状态
- 操作按钮（分派、流转、解决、关闭、取消）
- 沟通记录时间线
- 评论输入框

```vue
<!-- frontend/src/views/TicketDetailView.vue -->
<template>
  <AppLayout>
    <div class="ticket-detail" v-loading="loading">
      <template v-if="ticket">
        <!-- 头部 -->
        <div class="ticket-header">
          <el-button @click="$router.back()" text>← 返回</el-button>
          <span class="ticket-no">{{ ticket.ticket_no }}</span>
          <el-tag :type="typeTagMap[ticket.type]" size="small">{{ ticket.type_display }}</el-tag>
          <el-tag :type="priorityTagMap[ticket.priority]" size="small" effect="dark">{{ ticket.priority_display }}</el-tag>
          <el-tag :type="statusTagMap[ticket.status]" size="small">{{ ticket.status_display }}</el-tag>
        </div>
        <h2>{{ ticket.title }}</h2>

        <!-- 基本信息 -->
        <el-descriptions :column="3" border class="ticket-info">
          <el-descriptions-item label="提交人">{{ ticket.submitter_name }}</el-descriptions-item>
          <el-descriptions-item label="处理人">{{ ticket.assignee_name || '未分派' }}</el-descriptions-item>
          <el-descriptions-item label="当前节点">{{ ticket.current_node_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatDate(ticket.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="首次响应">{{ ticket.first_response_at ? formatDate(ticket.first_response_at) : '-' }}</el-descriptions-item>
          <el-descriptions-item label="解决时间">{{ ticket.resolved_at ? formatDate(ticket.resolved_at) : '-' }}</el-descriptions-item>
        </el-descriptions>

        <!-- 描述 -->
        <el-card v-if="ticket.description" class="section">
          <template #header>问题描述</template>
          <div class="description">{{ ticket.description }}</div>
        </el-card>

        <!-- 操作区 -->
        <el-card class="section" v-if="showActions">
          <template #header>操作</template>
          <el-space>
            <el-button v-if="canAssign" type="primary" @click="showAssignDialog = true">分派</el-button>
            <el-button v-if="canResolve" type="success" @click="handleResolve">解决</el-button>
            <el-button v-if="canClose" @click="handleClose">关闭</el-button>
            <el-button v-if="canCancel" type="danger" @click="handleCancel">取消</el-button>
          </el-space>
        </el-card>

        <!-- 时间线 -->
        <el-card class="section">
          <template #header>沟通记录</template>
          <el-timeline>
            <el-timeline-item
              v-for="item in timelineItems"
              :key="item.id"
              :timestamp="formatDate(item.created_at)"
              :type="item.is_system ? 'info' : 'primary'"
            >
              <div v-if="item.is_system" class="system-event">
                <strong>{{ item.author_name }}</strong>: {{ item.content }}
              </div>
              <div v-else>
                <strong>{{ item.author_name }}</strong>
                <p>{{ item.content }}</p>
              </div>
            </el-timeline-item>
          </el-timeline>

          <!-- 评论输入 -->
          <el-input v-model="newComment" type="textarea" :rows="3" placeholder="输入评论..." />
          <el-button type="primary" @click="handleComment" :disabled="!newComment.trim()" style="margin-top: 8px;">发送</el-button>
        </el-card>
      </template>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppLayout from '@/components/AppLayout.vue'
import { ticketsApi, type Ticket, type TicketComment, type TicketTransition } from '@/api/tickets'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const loading = ref(false)
const ticket = ref<Ticket | null>(null)
const newComment = ref('')
const showAssignDialog = ref(false)

const typeTagMap: Record<string, string> = { fault: 'danger', request: 'primary', internal: 'info', change: 'warning' }
const priorityTagMap: Record<string, string> = { critical: 'danger', high: 'warning', medium: '', low: 'info' }
const statusTagMap: Record<string, string> = { pending: 'info', assigned: '', processing: 'warning', resolved: 'success', closed: 'info', cancelled: 'info' }

const isICTStaff = computed(() => ['admin', 'operator', 'viewer'].includes(auth.user?.role || ''))
const showActions = computed(() => ticket.value && !['closed', 'cancelled'].includes(ticket.value.status))
const canAssign = computed(() => isICTStaff.value && ticket.value?.status === 'pending')
const canResolve = computed(() => isICTStaff.value && ['assigned', 'processing'].includes(ticket.value?.status || ''))
const canClose = computed(() => ticket.value?.status === 'resolved')
const canCancel = computed(() => ticket.value && !['resolved', 'closed', 'cancelled'].includes(ticket.value.status))

// 合并评论和流转记录为时间线
const timelineItems = computed(() => {
  if (!ticket.value) return []
  const comments = (ticket.value.comments || []).map(c => ({ ...c, sortTime: c.created_at }))
  const transitions = (ticket.value.transitions || []).map(t => ({
    id: t.id, author_name: `${t.operator_name} (系统)`, content: `流转：${t.from_node_name || '开始'} → ${t.to_node_name}${t.comment ? ' - ' + t.comment : ''}`,
    is_system: true, created_at: t.created_at, sortTime: t.created_at,
  }))
  return [...comments, ...transactions].sort((a, b) => new Date(a.sortTime).getTime() - new Date(b.sortTime).getTime())
})

function formatDate(d: string) { return new Date(d).toLocaleString('zh-CN') }

async function fetchTicket() {
  loading.value = true
  try {
    const { data } = await ticketsApi.get(route.params.id as string)
    ticket.value = data
  } finally { loading.value = false }
}

async function handleResolve() {
  const { value } = await ElMessageBox.prompt('请输入解决方案', '解决工单', { confirmButtonText: '解决', cancelButtonText: '取消' })
  await ticketsApi.resolve(ticket.value!.id, value)
  ElMessage.success('工单已解决')
  fetchTicket()
}

async function handleClose() {
  await ticketsApi.close(ticket.value!.id)
  ElMessage.success('工单已关闭')
  fetchTicket()
}

async function handleCancel() {
  const { value } = await ElMessageBox.prompt('请输入取消原因', '取消工单', { confirmButtonText: '取消工单', cancelButtonText: '返回' })
  await ticketsApi.cancel(ticket.value!.id, value)
  ElMessage.success('工单已取消')
  fetchTicket()
}

async function handleComment() {
  if (!newComment.value.trim()) return
  await ticketsApi.addComment(ticket.value!.id, newComment.value)
  newComment.value = ''
  ElMessage.success('评论已发送')
  fetchTicket()
}

onMounted(fetchTicket)
</script>

<style scoped>
.ticket-detail { max-width: 1000px; margin: 0 auto; }
.ticket-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.ticket-no { font-size: 14px; color: #909399; font-family: monospace; }
.section { margin-top: 16px; }
.description { white-space: pre-wrap; }
.system-event { color: #909399; font-size: 13px; }
</style>
```

- [ ] **Step 2: 提交**

```bash
git add frontend/src/views/TicketDetailView.vue
git commit -m "feat(frontend): add ticket detail page with timeline and actions"
```

---

## Task 10: 前端 — 菜单与通知铃铛

**Files:**
- Modify: `frontend/src/components/AppLayout.vue`
- Modify: `frontend/src/stores/auth.ts`

- [ ] **Step 1: 更新 AppLayout 菜单**

在 `AppLayout.vue` 中：
1. 根据角色控制菜单可见性
2. 新增工单管理菜单项
3. 新增通知铃铛图标

关键修改点：
- 在 `nav-menu` 中新增工单菜单项（所有角色可见）
- 在 `header-right` 中新增通知铃铛
- 更新 `roleLabel` 映射以支持新角色
- 更新 `isAdmin` 计算属性以支持 `platform_admin`

```vue
<!-- 在 nav-menu 中，jobs 之后、audit-logs 之前追加 -->
<el-menu-item index="/tickets">工单管理</el-menu-item>

<!-- 在 header-right 中，guide-link 之后追加通知铃铛 -->
<el-badge :value="unreadCount" :hidden="unreadCount === 0" class="notification-badge">
  <el-icon style="cursor: pointer; font-size: 18px;" @click="showNotifications = true"><bell /></el-icon>
</el-badge>
```

```typescript
// script 部分更新
import { Bell } from '@element-plus/icons-vue'
import { notificationsApi } from '@/api/tickets'

const unreadCount = ref(0)
const showNotifications = ref(false)

// 更新角色判断
const isAdmin = computed(() => ['admin', 'platform_admin'].includes(auth.user?.role || ''))
const isICTStaff = computed(() => ['admin', 'platform_admin', 'operator', 'viewer'].includes(auth.user?.role || ''))

// 更新角色标签
const roleLabel = computed(() => {
  const map: Record<string, string> = {
    admin: '平台管理员', operator: '运维员', viewer: '只读',
    enterprise_admin: '企业管理员', enterprise_user: '企业员工',
  }
  return map[auth.user?.role || ''] || ''
})

// 轮询未读通知数
async function fetchUnreadCount() {
  try {
    const { data } = await notificationsApi.unreadCount()
    unreadCount.value = data.count
  } catch { /* ignore */ }
}

onMounted(() => {
  fetchUnreadCount()
  setInterval(fetchUnreadCount, 60000) // 每分钟轮询
})
```

- [ ] **Step 2: 提交**

```bash
git add frontend/src/components/AppLayout.vue frontend/src/stores/auth.ts
git commit -m "feat(frontend): add ticket menu, notification badge, and role-based menu visibility"
```

---

## Task 11: 工单导入导出

**Files:**
- Create: `backend/apps/tickets/import_export.py`
- Modify: `backend/apps/tickets/views.py`
- Modify: `backend/apps/tickets/urls.py`
- Modify: `frontend/src/views/TicketsView.vue`
- Test: `backend/tests/test_tickets.py`

- [ ] **Step 1: 编写导入导出测试**

```python
# backend/tests/test_tickets.py — 追加
import io
import csv
from django.core.files.uploadedfile import SimpleUploadedFile


@pytest.mark.django_db
class TestTicketImportExport:
    @pytest.fixture
    def api_client(self):
        tenant = Tenant.objects.create(name="测试企业")
        user = User.objects.create_user(username="exporter", password="pass", tenant=tenant, role="admin")
        client = APIClient()
        token = RefreshToken.for_user(user)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
        return client, user, tenant

    def test_export_tickets_csv(self, api_client):
        client, user, tenant = api_client
        flow = TicketFlow.objects.create(name="流程", ticket_type="fault")
        node = TicketNode.objects.create(flow=flow, name="受理", order=1, role_required="operator")
        policy = SLAPolicy.objects.create(name="SLA", priority="medium", response_minutes=60, resolve_minutes=480)
        Ticket.objects.create(
            tenant=tenant, ticket_no="TK-20260817-0001", title="测试导出",
            type="fault", priority="medium", status="pending",
            current_node=node, submitter=user, sla_policy=policy,
        )
        resp = client.get("/api/tickets/export/")
        assert resp.status_code == 200
        assert resp["Content-Type"] == "text/csv"
        content = resp.content.decode("utf-8-sig")
        assert "测试导出" in content

    def test_import_tickets_csv(self, api_client):
        client, user, tenant = api_client
        SLAPolicy.objects.create(name="SLA", priority="medium", response_minutes=60, resolve_minutes=480)
        csv_content = "标题,类型,优先级,描述\n导入测试工单,fault,medium,测试描述\n"
        upload = SimpleUploadedFile("tickets.csv", csv_content.encode("utf-8"), content_type="text/csv")
        resp = client.post("/api/tickets/import/", {"file": upload}, format="multipart")
        assert resp.status_code == 200
        assert len(resp.data["preview"]) == 1
        assert resp.data["preview"][0]["title"] == "导入测试工单"
```

- [ ] **Step 2: 实现导入导出逻辑**

```python
# backend/apps/tickets/import_export.py
import csv
import io
from django.http import HttpResponse
from .models import Ticket, SLAPolicy
from .ticket_no import generate_ticket_no


EXPORT_FIELDS = ["ticket_no", "title", "type", "priority", "status", "submitter_name", "assignee_name", "created_at", "resolved_at", "closed_at"]


def export_tickets_csv(queryset) -> HttpResponse:
    """导出工单为 CSV（UTF-8 with BOM）"""
    response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    response["Content-Disposition"] = 'attachment; filename="tickets_export.csv"'
    response.write("\ufeff")  # BOM
    writer = csv.writer(response)
    writer.writerow(["工单编号", "标题", "类型", "优先级", "状态", "提交人", "处理人", "创建时间", "解决时间", "关闭时间"])
    for t in queryset.select_related("submitter", "assignee"):
        writer.writerow([
            t.ticket_no, t.title, t.get_type_display(), t.get_priority_display(),
            t.get_status_display(), t.submitter.username if t.submitter else "",
            t.assignee.username if t.assignee else "",
            t.created_at.isoformat(), t.resolved_at.isoformat() if t.resolved_at else "",
            t.closed_at.isoformat() if t.closed_at else "",
        ])
    return response


def parse_import_csv(file) -> list[dict]:
    """解析导入的 CSV 文件，返回预览数据列表"""
    raw = file.read()
    # 自适应 UTF-8/GBK
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("gbk")
    reader = csv.DictReader(io.StringIO(text))
    results = []
    for row in reader:
        results.append({
            "title": row.get("标题", "").strip(),
            "type": row.get("类型", "fault").strip(),
            "priority": row.get("优先级", "medium").strip(),
            "description": row.get("描述", "").strip(),
        })
    return results


def confirm_import(parsed_data: list[dict], tenant, submitter) -> int:
    """确认导入，创建工单"""
    count = 0
    for item in parsed_data:
        if not item["title"]:
            continue
        from .engine import TicketEngine
        engine = TicketEngine()
        engine.create_ticket(data=item, submitter=submitter)
        count += 1
    return count
```

- [ ] **Step 3: 在 views.py 中追加导入导出视图**

```python
# backend/apps/tickets/views.py — 追加
from .import_export import export_tickets_csv, parse_import_csv, confirm_import
from django.core.cache import cache
import uuid


class TicketExportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Ticket.objects.filter(tenant=get_tenant(request))
        if request.user.role == "enterprise_user":
            qs = qs.filter(submitter=request.user)
        # 应用筛选条件
        for param in ("type", "status", "priority"):
            val = request.query_params.get(param)
            if val:
                qs = qs.filter(**{param: val})
        return export_tickets_csv(qs)


class TicketImportView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.role not in ("admin", "operator"):
            return Response({"detail": "无权限"}, status=403)
        f = request.FILES.get("file")
        if not f:
            return Response({"detail": "请上传文件"}, status=400)
        preview = parse_import_csv(f)
        # 缓存预览结果 10 分钟
        session_id = str(uuid.uuid4())
        cache.set(f"ticket_import:{session_id}", preview, 600)
        return Response({"session_id": session_id, "preview": preview, "count": len(preview)})


class TicketImportConfirmView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.role not in ("admin", "operator"):
            return Response({"detail": "无权限"}, status=403)
        session_id = request.data.get("session_id")
        preview = cache.get(f"ticket_import:{session_id}")
        if not preview:
            return Response({"detail": "导入数据已过期"}, status=400)
        count = confirm_import(preview, get_tenant(request), request.user)
        cache.delete(f"ticket_import:{session_id}")
        return Response({"imported": count})
```

- [ ] **Step 4: 注册 URL**

```python
# backend/apps/tickets/urls.py — 追加
path("export/", views.TicketExportView.as_view(), name="ticket-export"),
path("import/", views.TicketImportView.as_view(), name="ticket-import"),
path("import/confirm/", views.TicketImportConfirmView.as_view(), name="ticket-import-confirm"),
```

- [ ] **Step 5: 运行测试**

```bash
cd backend && python -m pytest tests/test_tickets.py::TestTicketImportExport -v
```

- [ ] **Step 6: 提交**

```bash
git add backend/apps/tickets/import_export.py backend/apps/tickets/views.py backend/apps/tickets/urls.py backend/tests/test_tickets.py
git commit -m "feat(tickets): add ticket import/export (CSV with UTF-8/GBK support)"
```

---

## Task 12: 工单模板（预设表单）

**Files:**
- Modify: `backend/apps/tickets/models.py`
- Modify: `backend/apps/tickets/serializers.py`
- Modify: `backend/apps/tickets/views.py`
- Modify: `backend/apps/tickets/urls.py`
- Test: `backend/tests/test_tickets.py`

- [ ] **Step 1: 编写测试**

```python
# backend/tests/test_tickets.py — 追加
from apps.tickets.models import TicketTemplate


@pytest.mark.django_db
class TestTicketTemplate:
    def test_create_ticket_template(self):
        template = TicketTemplate.objects.create(
            name="服务器故障报告",
            description="用于报告服务器相关故障",
            ticket_type="fault",
            fields={"custom_fields": [
                {"name": "server_ip", "label": "服务器IP", "type": "text", "required": True},
            ]},
        )
        assert template.name == "服务器故障报告"
        assert len(template.fields["custom_fields"]) == 1

    def test_template_api_list(self):
        from rest_framework.test import APIClient
        from rest_framework_simplejwt.tokens import RefreshToken
        tenant = Tenant.objects.create(name="测试")
        user = User.objects.create_user(username="tpl_admin", password="pass", tenant=tenant, role="admin")
        TicketTemplate.objects.create(name="模板1", ticket_type="fault", fields={})
        client = APIClient()
        token = RefreshToken.for_user(user)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
        resp = client.get("/api/tickets/templates/")
        assert resp.status_code == 200
```

- [ ] **Step 2: 添加 TicketTemplate 模型**

```python
# backend/apps/tickets/models.py — 追加
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
```

- [ ] **Step 3: 添加序列化器和视图**

```python
# backend/apps/tickets/serializers.py — 追加
class TicketTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TicketTemplate
        fields = "__all__"
```

```python
# backend/apps/tickets/views.py — 追加
class TicketTemplateListView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TicketTemplateSerializer

    def get_queryset(self):
        qs = TicketTemplate.objects.filter(is_active=True)
        if self.request.method == "POST":
            return TicketTemplate.objects.all()
        return qs


class TicketTemplateDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, IsAdmin]
    serializer_class = TicketTemplateSerializer
    queryset = TicketTemplate.objects.all()
```

- [ ] **Step 4: 注册 URL**

```python
# backend/apps/tickets/urls.py — 追加
path("templates/", views.TicketTemplateListView.as_view(), name="ticket-template-list"),
path("templates/<uuid:pk>/", views.TicketTemplateDetailView.as_view(), name="ticket-template-detail"),
```

- [ ] **Step 5: 生成 migration 并运行测试**

```bash
cd backend && python manage.py makemigrations tickets
cd backend && python manage.py migrate
cd backend && python -m pytest tests/test_tickets.py::TestTicketTemplate -v
```

- [ ] **Step 6: 提交**

```bash
git add backend/apps/tickets/models.py backend/apps/tickets/serializers.py backend/apps/tickets/views.py backend/apps/tickets/urls.py backend/apps/tickets/migrations/ backend/tests/test_tickets.py
git commit -m "feat(tickets): add ticket templates (pre-filled forms)"
```

---

## Task 13: 知识库 / FAQ

**Files:**
- Create: `backend/apps/kb/__init__.py`
- Create: `backend/apps/kb/apps.py`
- Create: `backend/apps/kb/models.py`
- Create: `backend/apps/kb/serializers.py`
- Create: `backend/apps/kb/views.py`
- Create: `backend/apps/kb/urls.py`
- Modify: `backend/config/settings/base.py`
- Modify: `backend/config/urls.py`
- Create: `frontend/src/api/kb.ts`
- Create: `frontend/src/views/KnowledgeBaseView.vue`
- Create: `frontend/src/views/ArticleDetailView.vue`
- Modify: `frontend/src/router/index.ts`
- Test: `backend/tests/test_kb.py`

- [ ] **Step 1: 创建 kb app 并编写模型**

```python
# backend/apps/kb/__init__.py
# (空文件)
```

```python
# backend/apps/kb/apps.py
from django.apps import AppConfig


class KbConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.kb"
    verbose_name = "知识库"
```

```python
# backend/apps/kb/models.py
import uuid
from django.db import models
from apps.accounts.models import User


class ArticleCategory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50, unique=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]
        verbose_name = "文章分类"

    def __str__(self):
        return self.name


class Article(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    content = models.TextField()
    category = models.ForeignKey(ArticleCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="articles")
    tags = models.CharField(max_length=500, blank=True, help_text="逗号分隔")
    is_published = models.BooleanField(default=False)
    view_count = models.PositiveIntegerField(default=0)
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="articles")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "文章"

    def __str__(self):
        return self.title
```

- [ ] **Step 2: 编写测试**

```python
# backend/tests/test_kb.py
import pytest
from apps.kb.models import Article, ArticleCategory
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from apps.accounts.models import Tenant, User


@pytest.mark.django_db
class TestKnowledgeBase:
    def test_create_article(self):
        cat = ArticleCategory.objects.create(name="常见故障")
        tenant = Tenant.objects.create(name="ICT")
        user = User.objects.create_user(username="author", password="pass", tenant=tenant, role="admin")
        article = Article.objects.create(
            title="如何重置密码", slug="reset-password",
            content="## 步骤\n1. 登录管理后台\n2. 找到用户管理",
            category=cat, is_published=True, author=user,
        )
        assert article.title == "如何重置密码"
        assert article.slug == "reset-password"

    def test_article_list_api(self):
        cat = ArticleCategory.objects.create(name="FAQ")
        tenant = Tenant.objects.create(name="ICT")
        user = User.objects.create_user(username="kb_user", password="pass", tenant=tenant, role="admin")
        Article.objects.create(title="文章1", slug="art-1", content="内容", category=cat, is_published=True, author=user)
        Article.objects.create(title="草稿", slug="draft", content="未发布", category=cat, is_published=False, author=user)

        client = APIClient()
        token = RefreshToken.for_user(user)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
        resp = client.get("/api/kb/articles/")
        assert resp.status_code == 200
        # 只返回已发布的文章
        assert len(resp.data["results"]) == 1

    def test_article_search(self):
        cat = ArticleCategory.objects.create(name="FAQ")
        tenant = Tenant.objects.create(name="ICT")
        user = User.objects.create_user(username="searcher", password="pass", tenant=tenant, role="admin")
        Article.objects.create(title="SSH连接失败", slug="ssh-fail", content="检查防火墙配置", category=cat, is_published=True, author=user)
        Article.objects.create(title="密码重置", slug="pwd-reset", content="忘记密码的处理流程", category=cat, is_published=True, author=user)

        client = APIClient()
        token = RefreshToken.for_user(user)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
        resp = client.get("/api/kb/articles/search/?q=SSH")
        assert resp.status_code == 200
        assert len(resp.data) >= 1
        assert resp.data[0]["title"] == "SSH连接失败"
```

- [ ] **Step 3: 编写序列化器和视图**

```python
# backend/apps/kb/serializers.py
from rest_framework import serializers
from .models import Article, ArticleCategory


class ArticleCategorySerializer(serializers.ModelSerializer):
    article_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = ArticleCategory
        fields = ["id", "name", "order", "article_count"]


class ArticleListSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True, default="")
    author_name = serializers.CharField(source="author.username", read_only=True)

    class Meta:
        model = Article
        fields = ["id", "title", "slug", "category", "category_name", "tags",
                  "is_published", "view_count", "author_name", "created_at", "updated_at"]


class ArticleDetailSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True, default="")
    author_name = serializers.CharField(source="author.username", read_only=True)

    class Meta:
        model = Article
        fields = "__all__"
```

```python
# backend/apps/kb/views.py
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Q, Count
from apps.accounts.permissions import IsAdmin
from .models import Article, ArticleCategory
from .serializers import ArticleListSerializer, ArticleDetailSerializer, ArticleCategorySerializer


class ArticleListView(generics.ListAPIView):
    serializer_class = ArticleListSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Article.objects.filter(is_published=True).select_related("category", "author")


class ArticleDetailView(generics.RetrieveAPIView):
    serializer_class = ArticleDetailSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "slug"

    def get_queryset(self):
        return Article.objects.filter(is_published=True)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        # 增加浏览次数
        Article.objects.filter(pk=instance.pk).update(view_count=models.F("view_count") + 1)
        return super().retrieve(request, *args, **kwargs)


class ArticleSearchView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        q = request.query_params.get("q", "").strip()
        if not q:
            return Response([])
        articles = Article.objects.filter(
            is_published=True,
        ).filter(
            Q(title__icontains=q) | Q(content__icontains=q) | Q(tags__icontains=q)
        ).select_related("category")[:20]
        return Response(ArticleListSerializer(articles, many=True).data)


class ArticleManageView(generics.ListCreateAPIView):
    """管理端：所有文章（含草稿）"""
    permission_classes = [IsAuthenticated, IsAdmin]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ArticleDetailSerializer
        return ArticleListSerializer

    def get_queryset(self):
        return Article.objects.all().select_related("category", "author")

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)


class ArticleUpdateView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, IsAdmin]
    serializer_class = ArticleDetailSerializer
    queryset = Article.objects.all()


class CategoryListView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ArticleCategorySerializer

    def get_queryset(self):
        return ArticleCategory.objects.annotate(
            article_count=Count("articles", filter=Q(articles__is_published=True))
        )

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), IsAdmin()]
        return super().get_permissions()
```

```python
# backend/apps/kb/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path("articles/", views.ArticleListView.as_view(), name="kb-article-list"),
    path("articles/manage/", views.ArticleManageView.as_view(), name="kb-article-manage"),
    path("articles/manage/<uuid:pk>/", views.ArticleUpdateView.as_view(), name="kb-article-update"),
    path("articles/search/", views.ArticleSearchView.as_view(), name="kb-article-search"),
    path("articles/<slug:slug>/", views.ArticleDetailView.as_view(), name="kb-article-detail"),
    path("categories/", views.CategoryListView.as_view(), name="kb-category-list"),
]
```

- [ ] **Step 4: 注册 app 和 URL**

```python
# backend/config/settings/base.py — INSTALLED_APPS 追加
"apps.kb",
```

```python
# backend/config/urls.py — 追加
path("api/kb/", include("apps.kb.urls")),
```

- [ ] **Step 5: 生成 migration 并运行测试**

```bash
cd backend && python manage.py makemigrations kb
cd backend && python manage.py migrate
cd backend && python -m pytest tests/test_kb.py -v
```

- [ ] **Step 6: 提交后端**

```bash
git add backend/apps/kb/ backend/config/settings/base.py backend/config/urls.py backend/tests/test_kb.py
git commit -m "feat(kb): add knowledge base / FAQ module (articles, categories, search)"
```

- [ ] **Step 7: 前端 — 知识库 API 和页面**

```typescript
// frontend/src/api/kb.ts
import request from './request'

export interface Article {
  id: string
  title: string
  slug: string
  content?: string
  category: string
  category_name: string
  tags: string
  is_published: boolean
  view_count: number
  author_name: string
  created_at: string
  updated_at: string
}

export interface ArticleCategory {
  id: string
  name: string
  order: number
  article_count: number
}

export const kbApi = {
  listArticles() {
    return request.get('/kb/articles/')
  },
  getArticle(slug: string) {
    return request.get<Article>(`/kb/articles/${slug}/`)
  },
  search(q: string) {
    return request.get<Article[]>('/kb/articles/search/', { params: { q } })
  },
  listCategories() {
    return request.get<ArticleCategory[]>('/kb/categories/')
  },
  createArticle(data: Partial<Article>) {
    return request.post('/kb/articles/manage/', data)
  },
  updateArticle(id: string, data: Partial<Article>) {
    return request.put(`/kb/articles/manage/${id}/`, data)
  },
  deleteArticle(id: string) {
    return request.delete(`/kb/articles/manage/${id}/`)
  },
}
```

```typescript
// frontend/src/router/index.ts — 追加路由
{
  path: '/kb',
  name: 'kb',
  component: () => import('@/views/KnowledgeBaseView.vue'),
  meta: { requiresAuth: true },
},
{
  path: '/kb/:slug',
  name: 'kb-article',
  component: () => import('@/views/ArticleDetailView.vue'),
  meta: { requiresAuth: true },
},
```

- [ ] **Step 8: 创建知识库页面**

```vue
<!-- frontend/src/views/KnowledgeBaseView.vue -->
<template>
  <AppLayout>
    <div class="kb-page">
      <div class="kb-header">
        <h2>知识库</h2>
        <el-input v-model="searchQuery" placeholder="搜索文章..." clearable @keyup.enter="handleSearch" style="width: 300px;">
          <template #append>
            <el-button @click="handleSearch">搜索</el-button>
          </template>
        </el-input>
      </div>

      <!-- 搜索结果 -->
      <div v-if="searchResults" class="search-results">
        <h3>搜索结果 ({{ searchResults.length }})</h3>
        <el-card v-for="article in searchResults" :key="article.id" class="article-card" @click="$router.push(`/kb/${article.slug}`)">
          <h4>{{ article.title }}</h4>
          <el-tag size="small">{{ article.category_name }}</el-tag>
          <span class="meta">浏览 {{ article.view_count }}</span>
        </el-card>
        <el-button v-if="searchResults.length" text @click="searchResults = null">清除搜索</el-button>
      </div>

      <!-- 分类列表 -->
      <div v-else>
        <el-row :gutter="16">
          <el-col :span="8" v-for="cat in categories" :key="cat.id">
            <el-card class="category-card">
              <h4>{{ cat.name }}</h4>
              <p>{{ cat.article_count }} 篇文章</p>
            </el-card>
          </el-col>
        </el-row>

        <!-- 最新文章 -->
        <h3 style="margin-top: 24px;">最新文章</h3>
        <el-table :data="articles" @row-click="(row: any) => $router.push(`/kb/${row.slug}`)" stripe>
          <el-table-column prop="title" label="标题" />
          <el-table-column prop="category_name" label="分类" width="120" />
          <el-table-column prop="view_count" label="浏览" width="80" />
          <el-table-column prop="updated_at" label="更新时间" width="170">
            <template #default="{ row }">{{ new Date(row.updated_at).toLocaleDateString() }}</template>
          </el-table-column>
        </el-table>
      </div>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import AppLayout from '@/components/AppLayout.vue'
import { kbApi, type Article, type ArticleCategory } from '@/api/kb'

const categories = ref<ArticleCategory[]>([])
const articles = ref<Article[]>([])
const searchQuery = ref('')
const searchResults = ref<Article[] | null>(null)

async function handleSearch() {
  if (!searchQuery.value.trim()) { searchResults.value = null; return }
  const { data } = await kbApi.search(searchQuery.value)
  searchResults.value = data
}

onMounted(async () => {
  const [catResp, artResp] = await Promise.all([kbApi.listCategories(), kbApi.listArticles()])
  categories.value = catResp.data.results || catResp.data
  articles.value = artResp.data.results || artResp.data
})
</script>

<style scoped>
.kb-page { max-width: 1200px; margin: 0 auto; }
.kb-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.category-card { cursor: pointer; margin-bottom: 16px; }
.article-card { cursor: pointer; margin-bottom: 8px; }
.meta { color: #909399; font-size: 12px; margin-left: 8px; }
</style>
```

```vue
<!-- frontend/src/views/ArticleDetailView.vue -->
<template>
  <AppLayout>
    <div class="article-page" v-loading="loading">
      <template v-if="article">
        <el-button @click="$router.back()" text>← 返回</el-button>
        <h1>{{ article.title }}</h1>
        <div class="article-meta">
          <el-tag size="small">{{ article.category_name }}</el-tag>
          <span>作者: {{ article.author_name }}</span>
          <span>浏览: {{ article.view_count }}</span>
          <span>更新: {{ new Date(article.updated_at).toLocaleDateString() }}</span>
        </div>
        <el-divider />
        <div class="article-content" v-html="renderedContent"></div>
      </template>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import AppLayout from '@/components/AppLayout.vue'
import { kbApi, type Article } from '@/api/kb'

const route = useRoute()
const loading = ref(false)
const article = ref<Article | null>(null)

const renderedContent = computed(() => {
  // 简单 Markdown 渲染（可后续引入 marked.js）
  return article.value?.content?.replace(/\n/g, '<br>') || ''
})

onMounted(async () => {
  loading.value = true
  try {
    const { data } = await kbApi.getArticle(route.params.slug as string)
    article.value = data
  } finally { loading.value = false }
})
</script>

<style scoped>
.article-page { max-width: 800px; margin: 0 auto; }
.article-meta { display: flex; gap: 16px; color: #909399; font-size: 13px; margin-top: 8px; align-items: center; }
.article-content { line-height: 1.8; font-size: 15px; }
</style>
```

- [ ] **Step 9: 提交前端**

```bash
git add frontend/src/api/kb.ts frontend/src/views/KnowledgeBaseView.vue frontend/src/views/ArticleDetailView.vue frontend/src/router/index.ts
git commit -m "feat(frontend): add knowledge base pages (list, search, article detail)"
```

---

## Task 14: 集成测试与最终验证

- [ ] **Step 1: 运行全部后端测试**

```bash
cd backend && python -m pytest tests/test_tickets.py -v
```

Expected: 全部 PASS

- [ ] **Step 2: 运行现有测试确保无回归**

```bash
cd backend && python -m pytest -q
```

Expected: 全部 148+ 测试 PASS

- [ ] **Step 3: 前端类型检查与构建**

```bash
cd frontend && npm run build
```

Expected: 无类型错误，构建成功

- [ ] **Step 4: 手动验证清单**

- [ ] 创建工单 → 返回工单编号
- [ ] 工单列表 → 按角色过滤数据
- [ ] 工单详情 → 显示完整信息和时间线
- [ ] 分派工单 → 状态变为 assigned
- [ ] 解决工单 → 记录 resolved_at
- [ ] 取消工单 → 状态变为 cancelled
- [ ] 添加评论 → 出现在时间线中
- [ ] 通知铃铛 → 显示未读数

- [ ] **Step 5: 最终提交**

```bash
git add -A
git commit -m "feat(tickets): complete ticket system implementation with SLA, notifications, and frontend"
```

---

## 任务依赖关系

```
Task 1 (角色扩展)
    ↓
Task 2 (数据模型)
    ↓
Task 3 (编号生成器)
    ↓
Task 4 (流程引擎)
    ↓
Task 5 (API 视图)  ←→  Task 6 (SLA 管理)
    ↓
Task 7 (前端 API + 路由)
    ↓
Task 8 (工单列表页)
    ↓
Task 9 (工单详情页)
    ↓
Task 10 (菜单 + 通知铃铛)
    ↓
Task 11 (工单导入导出)
    ↓
Task 12 (工单模板)
    ↓
Task 13 (知识库) ← 可与 Task 11/12 并行
    ↓
Task 14 (集成测试)
```

Task 1-6 为后端核心，Task 7-10 为前端核心，Task 11-13 为扩展功能，Task 14 为验证。后端任务必须顺序执行；Task 11/12/13 之间互相独立，可并行推进。
