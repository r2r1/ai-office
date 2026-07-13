"""
Опубликованные лендинги офиса — по тенанту (data/tenants/<tid>/sites.json).

Хостинг по адресу /site/{tenant}/{slug} (см. server). Slug уникален в пределах тенанта.
"""

import hashlib
import re
import time

from src.saas import context as ctx
from src.office import results

_FILE = "sites.json"

results.register(results.ResultKind(
    id="sites", label="Сайты", icon="results", order=1,
    counter=lambda: len(_all()),
))


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


# Стабильный слаг ОСНОВНОГО сайта тенанта — легаси-случай (project_dir == "",
# т.е. публикация из КОРНЯ workspace, как было до Фазы 3 параллельных проектов).
# Раньше и авто-публикация, и ручной publish_site считали слаг от разных
# заголовков → у одного контента появлялось два адреса («будто новый сайт
# каждый раз»). Теперь главный сайт живёт по ОДНОМУ адресу для этого случая.
_MAIN_SLUG = "site"


def main_slug() -> str:
    return _MAIN_SLUG


def slug_for_current_project() -> str:
    """Слаг публикации для ТЕКУЩЕГО workspace-скоупа (BOS §10, Фаза 3 параллельных
    проектов). Каждый проект получил СВОЮ подпапку workspace/{workspace_dir}/ —
    у каждого должен быть и свой адрес сайта, иначе публикация из проекта B
    перезаписывает запись slug="site" проекта A в sites.json, а раздача (server.py
    _serve_site_file) резолвит файлы БЕЗ project-скоупа и ищет несуществующую
    workspace/site/ в корне тенанта — 404 независимо от того, чей это сайт
    (реальный кейс: 2 параллельных проекта, оба «опубликованы» на /site/{tid}/site,
    страница не открывалась ни для одного). project_dir="" (легаси/корень) —
    поведение не меняется, как и было."""
    from src.office import workspace
    pd = workspace.get_project_dir()
    return pd or _MAIN_SLUG


def save(title: str, html: str, slug: str = "") -> dict:
    from src.office import workspace
    sites = _all()
    slug = slug or make_slug(title)
    now = time.time()
    existing = sites.get(slug)
    site = {"slug": slug, "title": (title or "").strip(), "html": html,
            "created_ts": existing["created_ts"] if existing else now, "updated_ts": now,
            "project_dir": workspace.get_project_dir(),
            "project": (existing or {}).get("project") or _current_project_id()}
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

    `project_dir` фиксируется ТЕКУЩИМ workspace-скоупом (`workspace.get_project_dir()`
    на момент вызова, не `projects.active()` — «самый старый активный проект» может
    быть НЕ тем, что реально сейчас публикует при нескольких параллельных проектах)
    — server.py использует его, чтобы раздавать файлы из ПРАВИЛЬНОЙ папки проекта.
    """
    from src.office import workspace
    sites = _all()
    slug = slug or make_slug(title)
    now = time.time()
    existing = sites.get(slug)
    revision = (existing.get("revision", 0) + 1) if existing else 1
    changelog = list(existing.get("changelog", [])) if existing else []
    if note:
        changelog.append({"rev": revision, "note": note.strip()[:200], "ts": now})
        changelog = changelog[-30:]
    site = {"slug": slug, "title": (title or "").strip(), "root": (root or "").strip("/"),
            "created_ts": existing["created_ts"] if existing else now, "updated_ts": now,
            "revision": revision, "changelog": changelog,
            "project_dir": workspace.get_project_dir(),
            "project": (existing or {}).get("project") or _current_project_id()}
    sites[slug] = site
    ctx.write_json(_FILE, sites)
    return site


def _current_project_id() -> str:
    """id проекта, которому принадлежит ТЕКУЩИЙ workspace-скоуп — по обратному
    поиску workspace_dir в реестре проектов, а не projects.active() («самый
    старый активный»), которая может указать на ДРУГОЙ параллельный проект."""
    from src.office import workspace, projects
    pd = workspace.get_project_dir()
    if not pd:
        p = projects.active()
        return p["id"] if p else ""
    for p in projects.all_projects():
        if p.get("workspace_dir") == pd:
            return p["id"]
    return ""


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
