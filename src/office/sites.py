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
    sites = ctx.read_json(_FILE, {})
    # Лениво помечаем проектом старые записи (заведены до Work-модели — BOS §5) —
    # тот же приём, что milestones._load()/plan.adopt_orphan_tasks.
    from src.office import projects
    pid = None
    changed = False
    for s in sites.values():
        if not s.get("project"):
            if pid is None:
                p = projects.active()
                pid = p["id"] if p else ""
            if pid:
                s["project"] = pid
                changed = True
    if changed:
        ctx.write_json(_FILE, sites)
    return sites


def for_project(project_id: str) -> list[dict]:
    items = [{k: v for k, v in s.items() if k != "html"} for s in _all().values() if s.get("project") == project_id]
    return sorted(items, key=lambda x: x["updated_ts"], reverse=True)


# Стабильный слаг ОСНОВНОГО сайта тенанта. Раньше и авто-публикация, и ручной
# publish_site считали слаг от разных заголовков → у одного контента появлялось
# два адреса («будто новый сайт каждый раз»). Теперь главный сайт живёт по ОДНОМУ
# адресу, а публикация лишь обновляет его файлы и версию.
_MAIN_SLUG = "site"


def main_slug() -> str:
    return _MAIN_SLUG


def save(title: str, html: str, slug: str = "") -> dict:
    from src.office import projects
    sites = _all()
    slug = slug or make_slug(title)
    now = time.time()
    existing = sites.get(slug)
    proj = projects.active()
    site = {"slug": slug, "title": (title or "").strip(), "html": html,
            "created_ts": existing["created_ts"] if existing else now, "updated_ts": now,
            "project": (existing or {}).get("project") or (proj["id"] if proj else "")}
    sites[slug] = site
    ctx.write_json(_FILE, sites)
    return site


def save_dir(title: str, root: str, slug: str = "", note: str = "") -> dict:
    """
    Публикует МНОГОФАЙЛОВЫЙ сайт: хостится живая папка `root` рабочей директории
    (index.html + css/js/картинки/другие страницы). В отличие от save() здесь не
    инлайн-html, а ссылка на папку — сайт обновляется вместе с файлами агентов.

    `note` — краткое «что изменилось» в этой правке. Копится в журнал ревизий,
    чтобы каждая публикация была понятной правкой, а не «новым сайтом».
    """
    from src.office import projects
    sites = _all()
    slug = slug or make_slug(title)
    now = time.time()
    existing = sites.get(slug)
    revision = (existing.get("revision", 0) + 1) if existing else 1
    changelog = list(existing.get("changelog", [])) if existing else []
    if note:
        changelog.append({"rev": revision, "note": note.strip()[:200], "ts": now})
        changelog = changelog[-30:]
    proj = projects.active()
    site = {"slug": slug, "title": (title or "").strip(), "root": (root or "").strip("/"),
            "created_ts": existing["created_ts"] if existing else now, "updated_ts": now,
            "revision": revision, "changelog": changelog,
            "project": (existing or {}).get("project") or (proj["id"] if proj else "")}
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
