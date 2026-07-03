"""
Лиды, собранные формами лендингов — по тенанту. Реальные данные от посетителей.
"""

import time
import uuid

from src.saas import context as ctx

_FILE = "leads.json"
MAX_LEADS = 1000


def _all() -> list[dict]:
    return ctx.read_json(_FILE, [])


def add(slug: str, name: str, contact: str, message: str = "") -> dict:
    leads = _all()
    lead = {"id": uuid.uuid4().hex[:8], "slug": slug,
            "name": (name or "").strip()[:120], "contact": (contact or "").strip()[:160],
            "message": (message or "").strip()[:1000], "ts": time.time()}
    leads.append(lead)
    if len(leads) > MAX_LEADS:
        del leads[: len(leads) - MAX_LEADS]
    ctx.write_json(_FILE, leads)
    return lead


def all_leads() -> list[dict]:
    return sorted(_all(), key=lambda x: x["ts"], reverse=True)


def for_site(slug: str) -> list[dict]:
    return [l for l in all_leads() if l.get("slug") == slug]


def count() -> int:
    return len(_all())


def count_since(ts: float) -> int:
    """Число лидов, пришедших после метки времени ts (факт для Measurement)."""
    return sum(1 for l in _all() if l.get("ts", 0) >= ts)


def count_last_days(days: int = 7) -> int:
    """Число лидов за последние `days` суток — фактическая метрика «заявки/неделю»."""
    return count_since(time.time() - days * 86400)


def load() -> None:
    pass


def reset() -> None:
    ctx.delete_file(_FILE)
