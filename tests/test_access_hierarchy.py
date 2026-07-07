"""
Юнит-тесты иерархии доступа (BOS §6.1): лидеры/CEO/сервисные роли видят бизнес
насквозь (кросс-проектное ЧТЕНИЕ), рядовой воркер заперт в своём проекте.

    python tests/test_access_hierarchy.py
"""

import asyncio
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.saas import context as ctx
from src.office import projects, workspace
from src.agents import portfolio_tool_handlers


def _fresh(name: str) -> None:
    ctx.set_tenant(name)
    ctx.wipe()
    ctx.set_tenant(name)


async def _noop(_event: dict) -> None:
    pass


def _handlers(role: str) -> dict:
    return portfolio_tool_handlers.build("test_agent", role, _noop, _noop)


# ── valid_workspace_dir: отсекает инъекции ───────────────────────────────────

def test_valid_workspace_dir_accepts_known_project():
    _fresh("ah_valid_known")
    p = projects.create("Лендинг")
    assert projects.valid_workspace_dir(p["workspace_dir"]) == p["workspace_dir"]


def test_valid_workspace_dir_rejects_unknown_and_traversal():
    _fresh("ah_valid_reject")
    projects.create("Лендинг")
    assert projects.valid_workspace_dir("../other_tenant") is None
    assert projects.valid_workspace_dir("nonexistent_9") is None
    assert projects.valid_workspace_dir("") is None


# ── Кросс-проектное чтение (workspace) ───────────────────────────────────────

def test_leader_reads_other_project_file():
    _fresh("ah_cross_read")
    a = projects.create("Проект А")
    b = projects.create("Проект Б")
    workspace.set_project_dir(a["workspace_dir"])
    workspace.write_file("app.js", "AAA")
    workspace.set_project_dir(b["workspace_dir"])
    workspace.write_file("app.js", "BBB")
    workspace.set_project_dir("")
    # Читаем оба проекта явно по их папкам
    assert "AAA" in workspace.read_file_in(a["workspace_dir"], "app.js")
    assert "BBB" in workspace.read_file_in(b["workspace_dir"], "app.js")


def test_read_file_in_restores_scope_afterwards():
    _fresh("ah_scope_restore")
    a = projects.create("Проект А")
    workspace.set_project_dir("outer")
    workspace.read_file_in(a["workspace_dir"], "nope.txt")  # файла нет — неважно
    assert workspace.get_project_dir() == "outer"  # scope вернулся
    workspace.set_project_dir("")


# ── Хендлеры (portfolio_tool_handlers) ───────────────────────────────────────

def test_list_projects_handler_lists_all():
    _fresh("ah_list")
    projects.create("Первый")
    projects.create("Второй")
    h = _handlers("cto")
    out = asyncio.run(h["list_projects"]({}))
    assert "Первый" in out and "Второй" in out


def test_read_project_file_handler_rejects_bad_dir():
    _fresh("ah_reject_handler")
    projects.create("Проект")
    h = _handlers("orchestrator")
    out = asyncio.run(h["read_project_file"]({"project_dir": "../etc/passwd", "path": "x"}))
    assert "не найден" in out.lower()


def test_read_project_file_handler_reads_valid():
    _fresh("ah_read_handler")
    a = projects.create("Проект А")
    workspace.set_project_dir(a["workspace_dir"])
    workspace.write_file("readme.md", "СОДЕРЖИМОЕ")
    workspace.set_project_dir("")
    h = _handlers("cmo")
    out = asyncio.run(h["read_project_file"]({"project_dir": a["workspace_dir"], "path": "readme.md"}))
    assert "СОДЕРЖИМОЕ" in out


# ── Гейт по ролям (agent_factory) ────────────────────────────────────────────

def test_portfolio_gated_by_role():
    """Лидер/CEO/сервис получают портфельные инструменты, рядовой воркер — нет."""
    from src.office import org
    leaders = {"orchestrator", "architect", "strategist", "researcher", "hr"} | org.LEAD_ROLES
    workers = {"developer", "designer", "integrator", "marketer", "analyst", "salesman"}
    for r in leaders:
        assert org.is_portfolio_role(r), r
    for r in workers:
        assert not org.is_portfolio_role(r), r


# ── Портфельный слот промпта (prompt_builder) ────────────────────────────────

def test_portfolio_digest_present_for_leader():
    _fresh("ah_digest_leader")
    projects.create("Лендинг доставки")
    from src.office import prompt_builder
    ctxt = prompt_builder.task_context("cto", "проверь техотдел", department="tech")
    assert "ПОРТФЕЛЬ ПРОЕКТОВ" in ctxt
    assert "Лендинг доставки" in ctxt


def test_portfolio_digest_absent_for_worker():
    _fresh("ah_digest_worker")
    projects.create("Лендинг доставки")
    from src.office import prompt_builder
    ctxt = prompt_builder.task_context("developer", "напиши сайт", department="tech")
    assert "ПОРТФЕЛЬ ПРОЕКТОВ" not in ctxt


def test_portfolio_digest_empty_when_no_projects():
    _fresh("ah_digest_empty")
    from src.office import prompt_builder
    ctxt = prompt_builder.task_context("orchestrator", "реши что делать")
    assert "ПОРТФЕЛЬ ПРОЕКТОВ" not in ctxt


def _cleanup() -> None:
    for d in ctx.ROOT.glob("ah_*"):
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
