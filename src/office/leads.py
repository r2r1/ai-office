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


def load() -> None:
    pass


def reset() -> None:
    ctx.delete_file(_FILE)
