"""Report generators: CSV and PDF for job results."""
import csv
import io

PHASE_LABELS = {
    "connectivity": "连通性检查",
    "health": "健康检查",
    "init": "初始化",
    "completion": "完成度检查",
}


def _job_rows(job):
    """Build per-server summary rows for a job."""
    rows = []
    steps = list(job.template.steps.all().order_by("step_order")) if job.template else []
    for task in job.server_tasks.select_related("server").all():
        completion = task.completion_result or {}
        step_results = completion.get("steps", {})
        row = {
            "hostname": task.server.hostname,
            "ip": task.server.ip,
            "status": task.status,
            "steps": {},
        }
        for i, step in enumerate(steps, start=1):
            name = f"step{step.step_order}: {step.script.name}"
            row["steps"][name] = (
                step_results.get(name)
                or step_results.get(f"step{i}")
                or step_results.get(str(i))
                or "-"
            )
        rows.append(row)
    return steps, rows


def generate_csv_report(job) -> bytes:
    """Generate a CSV report (UTF-8 with BOM for Excel compatibility)."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    steps, rows = _job_rows(job)
    step_names = [f"step{s.step_order}: {s.script.name}" for s in steps]

    writer.writerow(["SITOP 初始化报告"])
    writer.writerow(["任务 ID", str(job.id)])
    writer.writerow(["模板", job.template.name if job.template else "-"])
    writer.writerow(["服务器组", job.group.name])
    writer.writerow(["状态", job.status])
    writer.writerow(["开始时间", job.start_time])
    writer.writerow(["结束时间", job.end_time])
    writer.writerow([])

    header = ["主机名", "IP", "任务状态"] + step_names
    writer.writerow(header)
    for row in rows:
        writer.writerow(
            [row["hostname"], row["ip"], row["status"]]
            + [row["steps"].get(n, "-") for n in step_names]
        )

    writer.writerow([])
    summary = job.summary or {}
    writer.writerow(["总计", summary.get("total", 0)])
    writer.writerow(["成功", summary.get("success", 0)])
    writer.writerow(["失败", summary.get("failed", 0)])
    writer.writerow(["跳过", summary.get("skipped", 0)])

    # UTF-8 BOM so Excel detects encoding correctly
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def generate_pdf_report(job) -> bytes:
    """Generate a PDF report using reportlab."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=15 * mm, bottomMargin=15 * mm)
    styles = getSampleStyleSheet()

    # Try to register a CJK font so Chinese renders; fall back silently
    _register_cjk_font()
    title_style = ParagraphStyle("title", parent=styles["Title"], fontName=_cjk_font(), fontSize=18)
    normal = ParagraphStyle("normal", parent=styles["Normal"], fontName=_cjk_font(), fontSize=10)

    steps, rows = _job_rows(job)
    step_names = [f"step{s.step_order}" for s in steps]

    elements = []
    elements.append(Paragraph("SITOP 初始化报告", title_style))
    elements.append(Spacer(1, 8))
    summary = job.summary or {}
    meta = [
        ["任务 ID", str(job.id)],
        ["模板", job.template.name if job.template else "-"],
        ["服务器组", job.group.name],
        ["状态", job.status],
        ["成功 / 失败 / 总计", f"{summary.get('success', 0)} / {summary.get('failed', 0)} / {summary.get('total', 0)}"],
    ]
    meta_table = Table(meta, colWidths=[50 * mm, 110 * mm])
    meta_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTNAME", (0, 0), (-1, -1), _cjk_font()),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f0f2f5")),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 12))

    header = ["主机名", "IP", "状态"] + step_names
    table_data = [header]
    for row in rows:
        table_data.append(
            [row["hostname"], row["ip"], row["status"]]
            + [str(row["steps"].get(n, "-")) for n in [f"step{s.step_order}: {s.script.name}" for s in steps]]
        )
    if len(table_data) > 1:
        result_table = Table(table_data)
        style = [
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTNAME", (0, 0), (-1, -1), _cjk_font()),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#409eff")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ]
        # Color status column
        for i, row in enumerate(rows, start=1):
            color = colors.HexColor("#67c23a") if row["status"] == "success" else colors.HexColor("#f56c6c")
            style.append(("TEXTCOLOR", (2, i), (2, i), color))
        result_table.setStyle(TableStyle(style))
        elements.append(result_table)
    else:
        elements.append(Paragraph("无服务器任务数据", normal))

    doc.build(elements)
    return buf.getvalue()


_cjk_font_name = "Helvetica"


def _register_cjk_font():
    """Register a CJK-capable font if one is available on the system."""
    global _cjk_font_name
    import os
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    candidates = [
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Supplemental/Songti.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("CJK", path, subfontIndex=0))
                _cjk_font_name = "CJK"
                return
            except Exception:
                continue


def _cjk_font():
    return _cjk_font_name
