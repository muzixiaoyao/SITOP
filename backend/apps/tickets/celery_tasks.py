from celery import shared_task
from .sla import check_sla_timeouts


@shared_task
def task_check_sla_timeouts():
    """Celery Beat 定时调用的 SLA 检查任务"""
    check_sla_timeouts()
