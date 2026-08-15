"""Webhook notifications for finished jobs (M4).

Called by the engine after finalize. Failures are logged and never
break job execution.
"""
import logging

import requests

logger = logging.getLogger(__name__)


def notify_job_finished(job):
    """POST job result to the template's webhook_url, if configured."""
    template = job.template
    if template is None or not getattr(template, "webhook_url", ""):
        return

    summary = job.summary or {}
    duration = None
    if job.start_time and job.end_time:
        duration = (job.end_time - job.start_time).total_seconds()

    payload = {
        "job_id": str(job.id),
        "status": job.status,
        "group": job.group.name,
        "template": template.name,
        "total": summary.get("total", 0),
        "success_count": summary.get("success", 0),
        "failed_count": summary.get("failed", 0),
        "duration_seconds": duration,
    }
    try:
        resp = requests.post(template.webhook_url, json=payload, timeout=10)
        logger.info("Webhook for job %s -> %s (HTTP %s)", job.id, template.webhook_url, resp.status_code)
    except Exception as e:  # noqa: BLE001 — webhook failure must not affect the job
        logger.warning("Webhook delivery failed for job %s: %s", job.id, e)
