"""Real-time progress publishing for job execution.

Publishes events to the Django Channels group "job_{job_id}".
Consumers (WebSocket) relay them to connected clients.
Frontend also polls GET /api/jobs/{id}/ as a fallback.
"""
import logging

from asgiref.sync import async_to_sync

logger = logging.getLogger(__name__)


def publish_job_update(job_id, event_type: str, data: dict | None = None):
    """Publish an update event for a job. Never raises — failures are logged."""
    try:
        from channels.layers import get_channel_layer

        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        async_to_sync(channel_layer.group_send)(
            f"job_{job_id}",
            {
                "type": "job.update",
                "data": {
                    "job_id": str(job_id),
                    "event": event_type,
                    "payload": data or {},
                },
            },
        )
    except Exception as e:  # noqa: BLE001 — progress must never break execution
        logger.warning("Failed to publish job update for %s: %s", job_id, e)
