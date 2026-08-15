"""HMAC-SHA256 script signing (M4).

Every script's content is signed on save. The engine verifies the
signature before remote execution; tampered content is refused.
"""
import hashlib
import hmac

from django.conf import settings


def _key() -> bytes:
    return getattr(settings, "SCRIPT_SIGNING_KEY", "dev-signing-key").encode("utf-8")


def compute_signature(content: str) -> str:
    return hmac.new(_key(), content.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_signature(content: str, signature: str) -> bool:
    expected = compute_signature(content)
    return hmac.compare_digest(expected, signature or "")
