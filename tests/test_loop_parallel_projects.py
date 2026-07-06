"""
Юнит-тесты Фазы 4 параллельных проектов (office/loop.py): индивидуальное
завершение КАЖДОГО активного проекта, а не только когда закончены буквально
ВСЕ (см. loop._close_finished_projects, loop._project_progress_complete).

    python tests/test_loop_parallel_projects.py
"""

import asyncio
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.office import loop, plan, projects, workspace, autonomy
from src.agents import orchestrator
from src.saas import context as ctx, context


def _collect():
    published = []

    async def publish(e):
        published.append(e)
    return published, publish


def _fresh(name: str) -> None:
    ctx.set_tenant(name)
    ctx.wipe()
    ctx.set_tenant(name)
    # Дефолтный уровень автономии ("guided") требует одобрения publish_site и
    # блокирующе ждёт ответа пользователя (asyncio.wait_for(..., timeout=600)) —
    # в юнит-тесте отвечать некому. "trusted" публикует сайт без вопроса.
    autonomy.set_level("trusted")


_GOOD_SITE = (
    "<html lang='ru'><head><title>x</title><meta name='viewport' content='w'>"
    "<style>body{color:#000}</style></head><body>"
    "<form action='/api/site-lead' method='post'>"
    "<input name='contact'><button>Отправить</button></form>"
    + "текст " * 60 + "</body></html>"
)


async def _no_recurring(*a, **kw):
    """Подмена orchestrator.classify_recurring (реальный LLM-вызов) — юниты не
    должны трогать сеть/деньги; код planning-стороны уже деградирует к cls={}
    при ЛЮБОМ исключении (см. loop._close_finished_projects), это и используем."""
    raise RuntimeError("LLM отключён в юнит-тесте")


def _patch_classify_recurring():
    orig = orchestrator.classify_recurring
    orchestrator.classify_recurring = _no_recurring
    return orig


def _unpatch_classify_recurring(orig) -> None:
    orchestrator.classify_recurring = orig


# ── _project_progress_complete ───────────────────────────────────────────────

def test_project_progress_complete_false_when_no_tasks():
    _fresh("loop_pp_test_no_tasks")
    p = projects.create("Пустой проект")
    assert loop._project_progress_complete(p["id"]) is False
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


def test_project_progress_complete_true_when_all_done():
    _fresh("loop_pp_test_all_done")
    p = projects.create("Проект")
    context.write_json("plan.json", {"generated": True, "tasks": [
        {"id": "t1", "status": "done", "project": p["id"]},
        {"id": "t2", "status": "skipped", "project": p["id"]},
    ]})
    assert loop._project_progress_complete(p["id"]) is True
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


def test_project_progress_complete_false_with_pending_task():
    _fresh("loop_pp_test_pending")
    p = projects.create("Проект")
    context.write_json("plan.json", {"generated": True, "tasks": [
        {"id": "t1", "status": "done", "project": p["id"]},
        {"id": "t2", "status": "pending", "project": p["id"]},
    ]})
    assert loop._project_progress_complete(p["id"]) is False
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


# ── _close_finished_projects: суть Фазы 4 ────────────────────────────────────

def test_finished_project_closes_independently_of_unfinished_sibling():
    """ГЛАВНЫЙ тест Фазы 4: проект A готов, проект B ещё нет (оба активны
    параллельно) — A должен закрыться СЕЙЧАС, не дожидаясь B."""
    _fresh("loop_close_test_independent")
    a = projects.create("Проект A")
    b = projects.create("Проект B")
    context.write_json("plan.json", {"generated": True, "tasks": [
        {"id": "t1", "status": "done", "project": a["id"], "role": "developer", "title": "Сделать сайт A"},
        {"id": "t2", "status": "pending", "project": b["id"], "role": "developer", "title": "Сделать сайт B"},
    ]})
    workspace.set_project_dir(a["workspace_dir"])
    workspace.write_file("site/index.html", _GOOD_SITE)
    workspace.set_project_dir("")

    orig = _patch_classify_recurring()
    try:
        published, publish = _collect()
        asyncio.run(loop._close_finished_projects(publish))
    finally:
        _unpatch_classify_recurring(orig)

    assert projects.get(a["id"])["status"] == "done", "проект A должен закрыться"
    assert projects.get(b["id"])["status"] == "active", "проект B ещё не готов — не трогаем"
    assert any("закрыт" in e.get("text", "") for e in published)
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


def test_finished_project_not_closed_twice():
    _fresh("loop_close_test_idempotent")
    a = projects.create("Проект A")
    context.write_json("plan.json", {"generated": True, "tasks": [
        {"id": "t1", "status": "done", "project": a["id"], "role": "developer", "title": "Сделать сайт"},
    ]})
    workspace.set_project_dir(a["workspace_dir"])
    workspace.write_file("site/index.html", _GOOD_SITE)
    workspace.set_project_dir("")

    orig = _patch_classify_recurring()
    try:
        published, publish = _collect()
        asyncio.run(loop._close_finished_projects(publish))
        assert projects.get(a["id"])["status"] == "done"
        published.clear()
        asyncio.run(loop._close_finished_projects(publish))
        assert not published, "закрытый проект не обрабатывается второй раз"
    finally:
        _unpatch_classify_recurring(orig)
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


def test_process_type_never_auto_closed():
    """Процессы (BOS §5) не завершаются сами — даже со 100% "прогрессом" их
    задач _close_finished_projects не должен их закрывать."""
    _fresh("loop_close_test_process")
    proc = projects.create("Продажи", type="process")
    context.write_json("plan.json", {"generated": True, "tasks": [
        {"id": "t1", "status": "done", "project": proc["id"]},
    ]})
    orig = _patch_classify_recurring()
    try:
        published, publish = _collect()
        asyncio.run(loop._close_finished_projects(publish))
    finally:
        _unpatch_classify_recurring(orig)
    assert projects.get(proc["id"])["status"] == "active"
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


def test_critical_site_problem_blocks_close_and_adds_fix_task():
    """Сайт с критической проблемой (нет index/форма и т.п.) НЕ должен закрывать
    проект — вместо этого добавляется фикс-задача В ТОТ ЖЕ проект."""
    _fresh("loop_close_test_critical")
    a = projects.create("Проект с багом")
    context.write_json("plan.json", {"generated": True, "tasks": [
        {"id": "t1", "status": "done", "project": a["id"], "role": "developer", "title": "Сделать сайт"},
    ]})
    # НЕ пишем site/index.html вовсе — check_site() вернёт critical "no_index".
    orig = _patch_classify_recurring()
    try:
        published, publish = _collect()
        asyncio.run(loop._close_finished_projects(publish))
    finally:
        _unpatch_classify_recurring(orig)

    assert projects.get(a["id"])["status"] == "active", "проект НЕ должен закрыться с критической проблемой"
    fix_tasks = [t for t in plan.for_project(a["id"]) if "исправить критические" in t["title"].lower()]
    assert fix_tasks, "должна была добавиться фикс-задача"
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


def test_forget_tenant_clears_per_project_completion_keys():
    tid = "loop_close_test_forget"
    loop._completion_announced[tid] = True
    loop._completion_announced[f"{tid}:p1_123"] = True
    loop._completion_announced["other_tenant"] = True
    loop.forget_tenant(tid)
    assert tid not in loop._completion_announced
    assert f"{tid}:p1_123" not in loop._completion_announced
    assert "other_tenant" in loop._completion_announced
    loop._completion_announced.pop("other_tenant", None)


def _cleanup_test_tenants() -> None:
    for pattern in ("loop_pp_test_*", "loop_close_test_*"):
        for d in ctx.ROOT.glob(pattern):
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
