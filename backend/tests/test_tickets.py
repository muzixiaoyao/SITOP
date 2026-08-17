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
