from datetime import date
from django.core.cache import cache


def generate_ticket_no() -> str:
    """生成工单编号 TK-{YYYYMMDD}-{4位序号}，使用缓存原子递增"""
    today = date.today().strftime("%Y%m%d")
    cache_key = f"ticket_no:{today}"
    # Ensure key exists (add is no-op if key already present)
    cache.add(cache_key, 0, timeout=48 * 3600)
    seq = cache.incr(cache_key)
    return f"TK-{today}-{seq:04d}"
