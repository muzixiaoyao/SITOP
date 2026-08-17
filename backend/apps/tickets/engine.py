from django.utils import timezone
from django.db.models import Q
from .models import Ticket, TicketFlow, TicketNode, TicketTransition, TicketComment, SLAPolicy
from .ticket_no import generate_ticket_no


class TicketEngine:
    """工单流程引擎"""

    def create_ticket(self, data: dict, submitter) -> Ticket:
        """创建工单，绑定流程模板，初始化 SLA"""
        ticket_type = data["type"]
        priority = data.get("priority", "medium")

        flow = TicketFlow.objects.filter(
            ticket_type=ticket_type, is_active=True,
        ).filter(
            Q(tenant=submitter.tenant) | Q(tenant__isnull=True)
        ).first()

        sla_policy = SLAPolicy.objects.filter(priority=priority).first()

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

        duration = 0
        last_transition = ticket.transitions.order_by("-created_at").first()
        if last_transition:
            duration = int((now - last_transition.created_at).total_seconds())

        ticket.current_node = target_node
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
