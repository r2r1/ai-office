"""
Опубликованные лендинги офиса — по тенанту (data/tenants/<tid>/sites.json).

Хостинг по адресу /site/{tenant}/{slug} (см. server). Slug уникален в пределах тенанта.
"""

import hashlib
import re
import time

from src.saas import context as ctx

_FILE = "sites.json"


def make_slug(title: str) -> str:
    ascii_slug = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")
    if len(ascii_slug) >= 3:
        return ascii_slug[:40]
    return "p" + hashlib.md5((title or "").encode("utf-8")).hexdigest()[:8]


def _all() -> dict:
    return ctx.read_json(_FILE, {})


def save(title: str, html: str, slug: str = "") -> dict:
    sites = _all()
    slug = slug or make_slug(title)
    now = time.time()
    existing = sites.get(slug)
    site = {"slug": slug, "title": (title or "").strip(), "html": html,
            "created_ts": existing["created_ts"] if existing else now, "updated_ts": now}
    sites[slug] = site
    ctx.write_json(_FILE, sites)
    return site


def get(slug: str) -> dict | None:
    return _all().get(slug)


def all_sites() -> list[dict]:
    items = sorted(_all().values(), key=lambda x: x["updated_ts"], reverse=True)
    return [{k: v for k, v in s.items() if k != "html"} for s in items]


def delete(slug: str) -> bool:
    sites = _all()
    if slug in sites:
        del sites[slug]
        ctx.write_json(_FILE, sites)
        return True
    return False


def load() -> None:
    pass


def reset() -> None:
    ctx.delete_file(_FILE)
