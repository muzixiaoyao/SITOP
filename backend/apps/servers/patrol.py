"""Scheduled connectivity patrol (M4).

Runs periodically via Celery Beat; also callable manually through
POST /api/groups/{id}/patrol/ for development/testing.
"""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


def patrol_group(group) -> dict:
    """Check connectivity for every server in a group. Returns counts."""
    from django.utils import timezone

    from apps.executor.ssh import SSHExecutor

    results = {"total": 0, "success": 0, "failed": 0}
    servers = list(group.servers.all())
    if not servers:
        return results

    with SSHExecutor(connect_timeout=8) as executor:
        for server in servers:
            results["total"] += 1
            try:
                result = executor.check_connectivity(server)
                ok = result.exit_code == 0 and "SITOP_CONNECTIVITY_OK" in result.output
            except Exception as e:  # noqa: BLE001
                logger.warning("Patrol check failed for %s: %s", server.ip, e)
                ok = False
            server.connectivity_status = "success" if ok else "failed"
            server.last_check_time = timezone.now()
            server.save(update_fields=["connectivity_status", "last_check_time"])
            results["success" if ok else "failed"] += 1
    return results


@shared_task(name="servers.patrol_all_groups")
def patrol_all_groups():
    """Beat task: patrol all groups that opted in."""
    from apps.servers.models import ServerGroup

    for group in ServerGroup.objects.filter(auto_patrol=True):
        try:
            counts = patrol_group(group)
            logger.info(
                "Patrol %s: %s/%s reachable", group.name, counts["success"], counts["total"]
            )
        except Exception as e:  # noqa: BLE001
            logger.error("Patrol failed for group %s: %s", group.name, e)
