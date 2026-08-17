import csv
import io
from django.http import HttpResponse
from .models import Ticket, SLAPolicy
from .ticket_no import generate_ticket_no


def export_tickets_csv(queryset) -> HttpResponse:
    """导出工单为 CSV（UTF-8 with BOM）"""
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="tickets_export.csv"'
    response.write("﻿")
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
