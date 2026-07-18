"""
Тест control.summary_text() — сводка «на чём остановились», публикуемая
сразу после постановки офиса на паузу (Корень 14, форензик-аудит прогона
2026-07-18: прогон оборвался на автопаузе по балансу LLM-провайдера, и
последним сообщением в ленте оказался случайный вопрос агента, а не
сводка состояния).

    python tests/test_control_summary.py
"""

import asyncio
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.saas import context as ctx
from src.office import control, plan, questions


def _wipe(tid: str):
    ctx.set_tenant(tid)
    ctx.wipe()
    ctx.set_tenant(tid)


def test_summary_empty_when_nothing_notable():
    _wipe("control_summary_empty")
    plan.add_task("Готовая задача", "developer", project_id="p1")
    plan.complete(plan.all_tasks()[0]["id"])
    assert control.summary_text() == ""
    _wipe("control_summary_empty")


def test_summary_lists_in_progress_tasks():
    _wipe("control_summary_doing")
    t = plan.add_task("Собрать сайт", "developer", project_id="p1")
    plan.assign(t["id"], "developer_1")
    text = control.summary_text()
    assert "в работе" in text
    assert t["id"] in text
    _wipe("control_summary_doing")


def test_summary_lists_blocked_tasks():
    _wipe("control_summary_blocked")
    t = plan.add_task("Задача-блокер", "developer", project_id="p1")
    plan.block(t["id"], "нет доступа")
    text = control.summary_text()
    assert "заблокировано" in text
    assert t["id"] in text
    _wipe("control_summary_blocked")


def test_summary_counts_open_questions():
    _wipe("control_summary_questions")
    plan.add_task("Задача", "developer", project_id="p1")  # чтобы is_generated()=True
    asyncio.run(_ask_question())
    text = control.summary_text()
    assert "неотвеченных вопросов" in text
    _wipe("control_summary_questions")


async def _ask_question():
    questions.ask("Какой стиль выбираем?", None, agent_id="orchestrator_1")


def test_summary_empty_when_plan_not_generated():
    _wipe("control_summary_no_plan")
    assert control.summary_text() == ""
    _wipe("control_summary_no_plan")


def _cleanup():
    for d in ctx.ROOT.glob("control_summary_*"):
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
        _cleanup()
    print(f"ВСЕ {passed} ТЕСТОВ ПРОШЛИ")


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    _run()
