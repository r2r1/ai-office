"""
Юнит-тесты автообновляемой карты проекта (src/office/project_map.py) —
материализованный кэш workspace.list_files() в docs/_project_map.md.

    python tests/test_project_map.py
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.saas import context as ctx
from src.office import workspace, project_map


def _fresh(name: str) -> None:
    ctx.set_tenant(name)
    ctx.wipe()
    ctx.set_tenant(name)


def test_refresh_on_empty_workspace_not_throttled_on_first_call():
    _fresh("pm_test_empty")
    text = project_map.refresh()
    assert text, "первый вызов не должен быть пропущен троттлингом"
    assert "Workspace пуст" in text


def test_refresh_produces_non_empty_text_with_files():
    _fresh("pm_test_files")
    workspace.write_file("index.html", "<html></html>")
    workspace.write_file("README.md", "# Проект\nОписание проекта для теста.")
    text = project_map.refresh(force=True)
    assert text
    assert "index.html" in text
    assert "README.md" in text
    assert "Описание проекта" in text


def test_refresh_writes_to_docs_project_map_file():
    _fresh("pm_test_write")
    workspace.write_file("app.js", "console.log(1)")
    project_map.refresh(force=True)
    paths = {f["path"] for f in workspace.list_files()}
    assert project_map._MAP_FILE in paths


def test_refresh_throttles_second_call():
    _fresh("pm_test_throttle")
    workspace.write_file("app.js", "console.log(1)")
    first = project_map.refresh()
    assert first
    second = project_map.refresh()
    assert second == "", "второй вызов сразу после первого должен быть пропущен троттлингом"


def _cleanup_test_tenants() -> None:
    for d in ctx.ROOT.glob("pm_test_*"):
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
