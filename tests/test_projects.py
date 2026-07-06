"""
Юнит-тесты параллельных проектов (src/office/projects.py) — лимит одновременных
Work (по умолчанию 3), очередь и автопродвижение при закрытии.

    python tests/test_projects.py
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.saas import context as ctx
from src.office import projects


def _fresh(name: str) -> None:
    ctx.set_tenant(name)
    ctx.wipe()
    ctx.set_tenant(name)


def test_default_limit_is_three():
    _fresh("proj_test_default_limit")
    assert projects.get_limit() == 3


def test_set_limit_persists():
    _fresh("proj_test_set_limit")
    projects.set_limit(5)
    assert projects.get_limit() == 5


def test_set_limit_floors_at_one():
    _fresh("proj_test_limit_floor")
    projects.set_limit(0)
    assert projects.get_limit() == 1


def test_projects_within_limit_all_active():
    _fresh("proj_test_within_limit")
    a = projects.create("A")
    b = projects.create("B")
    c = projects.create("C")
    assert a["status"] == b["status"] == c["status"] == "active"
    assert len(projects.active_list()) == 3


def test_project_over_limit_is_queued():
    _fresh("proj_test_over_limit")
    projects.create("A"); projects.create("B"); projects.create("C")
    d = projects.create("D")
    assert d["status"] == "queued"
    assert len(projects.active_list()) == 3
    assert len(projects.queued_list()) == 1


def test_closing_active_promotes_oldest_queued():
    _fresh("proj_test_promote")
    a = projects.create("A"); projects.create("B"); projects.create("C")
    d = projects.create("D")
    assert d["status"] == "queued"
    projects.close(a["id"])
    d_after = projects.get(d["id"])
    assert d_after["status"] == "active"
    assert len(projects.active_list()) == 3
    assert len(projects.queued_list()) == 0


def test_custom_limit_respected_on_create():
    _fresh("proj_test_custom_limit")
    projects.set_limit(1)
    a = projects.create("A")
    b = projects.create("B")
    assert a["status"] == "active"
    assert b["status"] == "queued"


def test_active_returns_first_active_not_none_with_multiple():
    _fresh("proj_test_active_singular")
    projects.create("A")
    projects.create("B")
    cur = projects.active()
    assert cur is not None
    assert cur["title"] == "A"


def test_ensure_active_reuses_existing_active_project():
    _fresh("proj_test_ensure_reuse")
    a = projects.create("A")
    assert projects.ensure_active()["id"] == a["id"]


def test_create_no_longer_force_closes_previous_active():
    """Раньше ЛЮБОЙ create() принудительно закрывал текущий активный проект —
    вторая принятая инициатива молча убивала первую. Теперь оба остаются
    активными, пока не упёрлись в лимит."""
    _fresh("proj_test_no_force_close")
    a = projects.create("A")
    projects.create("B")
    assert projects.get(a["id"])["status"] == "active"


def _cleanup_test_tenants() -> None:
    for d in ctx.ROOT.glob("proj_test_*"):
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
        _cleanup_test_tenants()
    print(f"ВСЕ {passed} ТЕСТОВ ПРОШЛИ")


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    _run()
