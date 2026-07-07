"""
Регрессия: публикация сайта из параллельного проекта не должна перезаписывать
адрес другого проекта тем же slug, а раздача файлов должна резолвить их из
ПРАВИЛЬНОЙ подпапки workspace/{project_dir}/ (BOS §10, Фаза 3).

Реальный кейс: два параллельных проекта («React», «статика») оба публиковались
под slug="site" (sites.main_slug()), sites.json хранил root="site" БЕЗ project_dir —
HTTP-раздача (server._serve_site_file) резолвила путь от КОРНЯ workspace тенанта,
где такой папки физически нет ни для одного проекта — 404 для ОБОИХ, независимо
от того, чей сайт был опубликован последним.

    python tests/test_sites_multi_project.py
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.saas import context as ctx
from src.office import workspace, sites, projects


def _fresh(name: str) -> None:
    ctx.set_tenant(name)
    ctx.wipe()
    ctx.set_tenant(name)


def test_slug_for_current_project_uses_project_dir():
    _fresh("sites_slug_test")
    workspace.set_project_dir("proj_a")
    assert sites.slug_for_current_project() == "proj_a"
    workspace.set_project_dir("")
    assert sites.slug_for_current_project() == sites.main_slug()


def test_parallel_projects_get_separate_slugs_no_clobber():
    _fresh("sites_parallel_test")
    a = projects.create("Проект А")
    b = projects.create("Проект Б")

    workspace.set_project_dir(a["workspace_dir"])
    workspace.write_file("site/index.html", "PROJECT A SITE")
    slug_a = sites.slug_for_current_project()
    site_a = sites.save_dir("Проект А", "site", slug_a, note="a")

    workspace.set_project_dir(b["workspace_dir"])
    workspace.write_file("site/index.html", "PROJECT B SITE")
    slug_b = sites.slug_for_current_project()
    site_b = sites.save_dir("Проект Б", "site", slug_b, note="b")

    workspace.set_project_dir("")
    assert slug_a != slug_b, "параллельные проекты не должны делить один slug"
    assert sites.get(slug_a) is not None
    assert sites.get(slug_b) is not None
    assert site_a["project_dir"] == a["workspace_dir"]
    assert site_b["project_dir"] == b["workspace_dir"]
    # Публикация проекта Б НЕ затёрла запись проекта А (реальный баг: оба
    # писали в один slug="site", вторая публикация убивала первую).
    assert sites.get(slug_a)["project_dir"] == a["workspace_dir"]


def test_save_dir_records_project_dir_of_current_scope_not_oldest_active():
    """projects.active() — «самый старый активный», НЕ обязательно тот, кто
    сейчас публикует. save_dir должен брать project_dir из ТЕКУЩЕГО workspace-
    скоупа, а не гадать по oldest-active (реальный баг: sites.json указывал на
    ДРУГОЙ параллельный проект, не тот, что реально написал файлы)."""
    _fresh("sites_scope_test")
    older = projects.create("Старый проект")   # создаётся первым → oldest active
    newer = projects.create("Новый проект")

    workspace.set_project_dir(newer["workspace_dir"])
    workspace.write_file("site/index.html", "NEWER PROJECT SITE")
    site = sites.save_dir("Новый проект", "site", sites.slug_for_current_project())
    workspace.set_project_dir("")

    assert site["project_dir"] == newer["workspace_dir"], (
        f"записан project_dir={site['project_dir']!r}, а публиковал {newer['workspace_dir']!r}"
    )
    assert site["project_dir"] != older["workspace_dir"]


def _cleanup() -> None:
    for d in ctx.ROOT.glob("sites_*"):
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)


def _run():
    passed = 0
    try:
        for name, fn in sorted(globals().items()):
            if name.startswith("test_") and callable(fn):
                fn()
                print(f"  ✓ {name}")
                passed += 1
    finally:
        workspace.set_project_dir("")
        _cleanup()
    print(f"ВСЕ {passed} ТЕСТОВ ПРОШЛИ")


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    _run()
