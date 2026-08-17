from django.test import TestCase
from apps.accounts.models import Tenant, User


class TestRoleExtension(TestCase):
    def test_platform_admin_role_exists(self):
        tenant = Tenant.objects.create(name="ICT公司")
        # admin 角色即平台管理员（向后兼容，保留 admin 值）
        user = User.objects.create_user(
            username="plat_admin", password="pass", tenant=tenant, role="admin"
        )
        self.assertEqual(user.role, "admin")
        self.assertEqual(user.get_role_display(), "平台管理员")

    def test_enterprise_admin_role_exists(self):
        tenant = Tenant.objects.create(name="客户企业A")
        user = User.objects.create_user(
            username="ent_admin", password="pass", tenant=tenant, role="enterprise_admin"
        )
        self.assertEqual(user.role, "enterprise_admin")

    def test_enterprise_user_role_exists(self):
        tenant = Tenant.objects.create(name="客户企业B")
        user = User.objects.create_user(
            username="ent_user", password="pass", tenant=tenant, role="enterprise_user"
        )
        self.assertEqual(user.role, "enterprise_user")

    def test_operator_role_still_works(self):
        """向后兼容：operator 角色仍然可用"""
        tenant = Tenant.objects.create(name="测试租户")
        user = User.objects.create_user(
            username="op", password="pass", tenant=tenant, role="operator"
        )
        self.assertEqual(user.role, "operator")

from apps.tickets.models import (
    Ticket, TicketFlow, TicketNode, SLAPolicy,
    TicketTransition, TicketComment, TicketAttachment, Notification,
)


class TestTicketModels(TestCase):
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
        node2 = TicketNode.objects.create(flow=flow, name="二线处理", order=2, role_required="admin", sla_hours=4)
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


from apps.tickets.ticket_no import generate_ticket_no


class TestTicketNo(TestCase):
    def test_generate_first_ticket_of_day(self):
        no = generate_ticket_no()
        assert no.startswith("TK-")
        assert len(no) == 16  # TK-YYYYMMDD-XXXX

    def test_sequential_numbers(self):
        no1 = generate_ticket_no()
        no2 = generate_ticket_no()
        seq1 = int(no1.split("-")[-1])
        seq2 = int(no2.split("-")[-1])
        assert seq2 == seq1 + 1

from apps.tickets.engine import TicketEngine


class TestTicketEngine(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="测试企业")
        self.submitter = User.objects.create_user(username="sub", password="pass", tenant=self.tenant, role="enterprise_user")
        self.handler = User.objects.create_user(username="handler", password="pass", tenant=self.tenant, role="operator")
        self.flow = TicketFlow.objects.create(name="故障流程", ticket_type="fault")
        self.node1 = TicketNode.objects.create(flow=self.flow, name="一线受理", order=1, role_required="operator", auto_assign_rule="manual")
        self.node2 = TicketNode.objects.create(flow=self.flow, name="处理中", order=2, role_required="operator")
        self.node3 = TicketNode.objects.create(flow=self.flow, name="已解决", order=3, role_required="operator", is_terminal=True)
        self.policy = SLAPolicy.objects.create(name="默认SLA", priority="high", response_minutes=60, resolve_minutes=480)
        self.engine = TicketEngine()

    def test_create_ticket(self):
        ticket = self.engine.create_ticket(
            data={"title": "数据库超时", "description": "连接池耗尽", "type": "fault", "priority": "high"},
            submitter=self.submitter,
        )
        assert ticket.status == "pending"
        assert ticket.current_node == self.node1
        assert ticket.sla_policy == self.policy
        assert ticket.ticket_no.startswith("TK-")

    def test_assign_ticket(self):
        ticket = self.engine.create_ticket(
            data={"title": "测试", "type": "fault", "priority": "high"},
            submitter=self.submitter,
        )
        self.engine.assign(ticket, self.handler, self.handler)
        ticket.refresh_from_db()
        assert ticket.status == "assigned"
        assert ticket.assignee == self.handler
        assert ticket.assigned_at is not None

    def test_transition_ticket(self):
        ticket = self.engine.create_ticket(
            data={"title": "测试", "type": "fault", "priority": "high"},
            submitter=self.submitter,
        )
        self.engine.assign(ticket, self.handler, self.handler)
        self.engine.transition(ticket, self.node2, self.handler, comment="开始排查")
        ticket.refresh_from_db()
        assert ticket.status == "processing"
        assert ticket.current_node == self.node2
        assert ticket.transitions.count() == 2

    def test_resolve_ticket(self):
        ticket = self.engine.create_ticket(
            data={"title": "测试", "type": "fault", "priority": "high"},
            submitter=self.submitter,
        )
        self.engine.assign(ticket, self.handler, self.handler)
        self.engine.resolve(ticket, self.handler, "已修复连接池配置")
        ticket.refresh_from_db()
        assert ticket.status == "resolved"
        assert ticket.resolved_at is not None

    def test_cancel_ticket(self):
        ticket = self.engine.create_ticket(
            data={"title": "测试", "type": "fault", "priority": "high"},
            submitter=self.submitter,
        )
        self.engine.cancel(ticket, self.submitter, "问题已自行解决")
        ticket.refresh_from_db()
        assert ticket.status == "cancelled"

from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken


class TestTicketAPI(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="测试企业")
        self.user = User.objects.create_user(username="api_user", password="pass", tenant=self.tenant, role="operator")
        self.client = APIClient()
        token = RefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")

    def test_create_ticket_api(self):
        SLAPolicy.objects.create(name="SLA", priority="high", response_minutes=60, resolve_minutes=480)
        TicketFlow.objects.create(name="故障流程", ticket_type="fault")

        resp = self.client.post("/api/tickets/", {
            "title": "数据库超时",
            "description": "连接池耗尽",
            "type": "fault",
            "priority": "high",
        }, format="json")
        assert resp.status_code == 201
        assert resp.data["ticket_no"].startswith("TK-")
        assert resp.data["status"] == "pending"

    def test_list_tickets_api(self):
        flow = TicketFlow.objects.create(name="流程", ticket_type="fault")
        node = TicketNode.objects.create(flow=flow, name="受理", order=1, role_required="operator")
        policy = SLAPolicy.objects.create(name="SLA", priority="medium", response_minutes=60, resolve_minutes=480)
        Ticket.objects.create(
            tenant=self.tenant, ticket_no="TK-20260817-0001", title="测试工单",
            type="fault", priority="medium", status="pending",
            current_node=node, submitter=self.user, sla_policy=policy,
        )
        resp = self.client.get("/api/tickets/")
        assert resp.status_code == 200
        assert len(resp.data["results"]) >= 1

    def test_ticket_detail_api(self):
        flow = TicketFlow.objects.create(name="流程", ticket_type="fault")
        node = TicketNode.objects.create(flow=flow, name="受理", order=1, role_required="operator")
        policy = SLAPolicy.objects.create(name="SLA", priority="medium", response_minutes=60, resolve_minutes=480)
        ticket = Ticket.objects.create(
            tenant=self.tenant, ticket_no="TK-20260817-0002", title="详情测试",
            type="fault", priority="medium", status="pending",
            current_node=node, submitter=self.user, sla_policy=policy,
        )
        resp = self.client.get(f"/api/tickets/{ticket.id}/")
        assert resp.status_code == 200
        assert resp.data["title"] == "详情测试"

    def test_assign_ticket_api(self):
        handler = User.objects.create_user(username="handler", password="pass", tenant=self.tenant, role="operator")
        flow = TicketFlow.objects.create(name="流程", ticket_type="fault")
        node = TicketNode.objects.create(flow=flow, name="受理", order=1, role_required="operator")
        policy = SLAPolicy.objects.create(name="SLA", priority="medium", response_minutes=60, resolve_minutes=480)
        ticket = Ticket.objects.create(
            tenant=self.tenant, ticket_no="TK-20260817-0003", title="分派测试",
            type="fault", priority="medium", status="pending",
            current_node=node, submitter=self.user, sla_policy=policy,
        )
        resp = self.client.post(f"/api/tickets/{ticket.id}/assign/", {"assignee_id": str(handler.id)}, format="json")
        assert resp.status_code == 200
        ticket.refresh_from_db()
        assert ticket.assignee == handler

from apps.tickets.sla import check_sla_timeouts
from django.utils import timezone
from datetime import timedelta


class TestSLA(TestCase):
    def test_sla_warning_at_80_percent(self):
        tenant = Tenant.objects.create(name="SLA测试")
        user = User.objects.create_user(username="sla_user", password="pass", tenant=tenant, role="operator")
        policy = SLAPolicy.objects.create(
            name="紧急SLA", priority="critical",
            response_minutes=60, resolve_minutes=240,
            escalation_rules={},
        )
        flow = TicketFlow.objects.create(name="流程", ticket_type="fault")
        node = TicketNode.objects.create(flow=flow, name="受理", order=1, role_required="operator")
        ticket = Ticket.objects.create(
            tenant=tenant, ticket_no="TK-SLA-0001", title="SLA测试",
            type="fault", priority="critical", status="pending",
            current_node=node, submitter=user, sla_policy=policy,
        )
        # 手动设置 created_at 为 50 分钟前（超过 80% 的 60 分钟时限）
        Ticket.objects.filter(pk=ticket.pk).update(
            created_at=timezone.now() - timedelta(minutes=50)
        )
        check_sla_timeouts()
        assert Notification.objects.filter(user=user, type="sla_warning").exists()
