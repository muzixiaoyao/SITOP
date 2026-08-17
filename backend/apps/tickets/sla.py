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
            elapsed = (now - ticket.created_at).total_seconds() / 60
            total = policy.response_minutes

            if elapsed >= total:
                _create_notification(ticket, "sla_violated",
                    f"工单 {ticket.ticket_no} 响应 SLA 已超时",
                    f"响应时限 {policy.response_minutes} 分钟，已超时 {int(elapsed - total)} 分钟")
            elif elapsed >= total * 0.8:
                _create_notification(ticket, "sla_warning",
                    f"工单 {ticket.ticket_no} 响应 SLA 即将超时",
                    f"已用 {int(elapsed)} 分钟，时限 {policy.response_minutes} 分钟")

        # 检查处理 SLA（从分派开始计算）
        if ticket.assigned_at and not ticket.resolved_at:
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
    recent = Notification.objects.filter(
        ticket=ticket, type=notif_type,
        created_at__gte=timezone.now() - timedelta(hours=1),
    ).exists()
    if recent:
        return

    target_user = ticket.assignee or ticket.submitter
    if target_user:
        Notification.objects.create(
            user=target_user, type=notif_type,
            title=title, content=content, ticket=ticket,
        )
