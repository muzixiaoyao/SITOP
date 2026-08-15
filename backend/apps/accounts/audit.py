"""Audit logging helper. Call from views after sensitive operations."""
import logging

logger = logging.getLogger(__name__)


def audit(request, action: str, resource_type: str, resource_id="", details=None):
    """Record an audit log entry. Never raises — auditing must not break requests."""
    try:
        from .models import AuditLog

        tenant = getattr(request, "tenant", None) or getattr(request.user, "tenant", None)
        AuditLog.objects.create(
            tenant=tenant,
            user=request.user if request.user.is_authenticated else None,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id),
            details=details or {},
            ip_address=_client_ip(request),
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to write audit log: %s", e)


def _client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
