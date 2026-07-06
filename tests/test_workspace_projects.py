"""
Юнит-тесты Фазы 3 параллельных проектов — читаемые имена папок workspace/ на
проект (src/office/projects.py) и изоляция workspace по проекту через
contextvars (src/office/workspace.py).

    python tests/test_workspace_projects.py
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.saas import context as ctx
from src.office import projects, workspace


def _fresh(name: str) -> None:
    ctx.set_tenant(name)
    ctx.wipe()
    ctx.set_tenant(name)


# ── Читаемые имена папок (projects.py) ───────────────────────────────────────

def test_workspace_dir_is_readable_ascii_not_project_id():
    _fresh("ws_test_readable")
    p = projects.create("Лендинг для доставки суши")
    wd = p["workspace_dir"]
    assert wd, "workspace_dir должен быть заполнен"
    assert wd != p["id"]
    assert all(ord(c) < 128 for c in wd), f"ожидались только ASCII-символы, получили: {wd}"
    assert wd.endswith("_1")


def test_workspace_dir_transliterates_cyrillic():
    _fresh("ws_test_translit")
    p = projects.create("Проверка вкладки лидов")
    assert p["workspace_dir"].startswith("proverka")


def test_workspace_dir_unique_on_collision():
    _fresh("ws_test_collision")
    a = projects.create("Сайт")
    b = projects.create("Сайт")
    assert a["workspace_dir"] != b["workspace_dir"]
    assert a["workspace_dir"].rsplit("_", 1)[0] == b["workspace_dir"].rsplit("_", 1)[0]


def test_workspace_dir_falls_back_to_work_for_empty_title():
    _fresh("ws_test_empty_title")
    p = projects.create("")
    assert p["workspace_dir"].startswith("work_")


def test_workspace_dir_of_resolves_by_project_id():
    _fresh("ws_test_dir_of")
    p = projects.create("Бот для записи")
    assert projects.workspace_dir_of(p["id"]) == p["workspace_dir"]


def test_workspace_dir_of_empty_for_legacy_project_without_field():
    """Проекты, созданные ДО появления workspace_dir, не должны падать —
    легаси-поведение: работают в корне workspace/ (пусто = root)."""
    _fresh("ws_test_legacy")
    p = projects.create("Обычный проект")
    d = ctx.read_json("projects.json", {"items": []})
    for item in d["items"]:
        if item["id"] == p["id"]:
            del item["workspace_dir"]
    ctx.write_json("projects.json", d)
    assert projects.workspace_dir_of(p["id"]) == ""


def test_workspace_dir_of_empty_for_unknown_project():
    _fresh("ws_test_unknown")
    assert projects.workspace_dir_of("nope") == ""
    assert projects.workspace_dir_of("") == ""


# ── Изоляция workspace по проекту (workspace.py) ─────────────────────────────

def test_default_scope_is_root_legacy_behavior():
    """Без явного set_project_dir/project_scope — поведение НЕ ИЗМЕНИЛОСЬ:
    write_file пишет прямо в корень workspace/, как до Фазы 3."""
    _fresh("ws_test_default_root")
    assert workspace.get_project_dir() == ""
    workspace.write_file("app.js", "console.log(1)")
    paths = {f["path"] for f in workspace.list_files()}
    assert "app.js" in paths


def test_set_project_dir_scopes_write_and_read():
    _fresh("ws_test_scope_write_read")
    workspace.set_project_dir("landing_1")
    workspace.write_file("app.js", "console.log('A')")
    assert "console.log('A')" in workspace.read_file("app.js")
    paths = {f["path"] for f in workspace.list_files()}
    assert "app.js" in paths  # list_files рекурсивно видит поддерево ОТНОСИТЕЛЬНО текущего scope
    workspace.set_project_dir("")  # не оставляем scope другим тестам этого файла


def test_two_projects_do_not_collide_on_same_filename():
    """Ради этого и делается Фаза 3: два проекта, оба пишущие app.js, не должны
    видеть содержимое друг друга."""
    _fresh("ws_test_no_collision")
    workspace.set_project_dir("proj_a")
    workspace.write_file("app.js", "PROJECT A")
    workspace.set_project_dir("proj_b")
    workspace.write_file("app.js", "PROJECT B")
    assert "PROJECT B" in workspace.read_file("app.js")
    workspace.set_project_dir("proj_a")
    assert "PROJECT A" in workspace.read_file("app.js")
    workspace.set_project_dir("")
    # На диске — реально разные файлы (полный обход из корня видит оба с префиксом).
    root = workspace.base_dir()  # scope уже "" — это и есть сам корень workspace/
    all_files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    assert "proj_a/app.js" in all_files
    assert "proj_b/app.js" in all_files


def test_project_scope_restores_previous_value_on_exit():
    _fresh("ws_test_scope_restore")
    workspace.set_project_dir("outer")
    with workspace.project_scope("inner"):
        assert workspace.get_project_dir() == "inner"
    assert workspace.get_project_dir() == "outer"
    workspace.set_project_dir("")


def test_project_scope_restores_on_exception():
    _fresh("ws_test_scope_restore_exc")
    workspace.set_project_dir("outer")
    try:
        with workspace.project_scope("inner"):
            raise ValueError("boom")
    except ValueError:
        pass
    assert workspace.get_project_dir() == "outer"
    workspace.set_project_dir("")


def test_project_scope_restores_on_continue_like_early_exit():
    """Симулирует паттерн loop.py: 'continue' внутри with-блока — контекст-менеджер
    обязан отработать __exit__ ДО перехода к следующей итерации цикла."""
    _fresh("ws_test_scope_continue")
    workspace.set_project_dir("")
    for i in range(2):
        with workspace.project_scope(f"iter_{i}"):
            if i == 0:
                continue
        # к этой строке доходим только когда i == 1 (i == 0 ушёл через continue)
    assert workspace.get_project_dir() == ""


def _cleanup_test_tenants() -> None:
    for d in ctx.ROOT.glob("ws_test_*"):
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
        _cleanup_test_tenants()
    print(f"ВСЕ {passed} ТЕСТОВ ПРОШЛИ")


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    _run()
