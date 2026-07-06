"""
Регрессия: офис не должен молчать НАВСЕГДА, когда единственная незакрытая работа —
заблокированная задача (реальный прод-инцидент — см. handoff.md, «офис молча замирает»).

`loop._heartbeat_if_blocked` — периодическое (не на каждом цикле) напоминание
владельцу, пока `has_actionable_move()` ложно и есть blocked-задачи. Без LLM, $0.

    python tests/test_loop_heartbeat.py
"""

import asyncio
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.office import loop, plan
from src.saas import context as ctx, context


def _collect():
    published = []

    async def publish(e):
        published.append(e)
    return published, publish


def test_no_blocked_tasks_is_silent():
    ctx.set_tenant("hb_unit_silent")
    context.write_json("plan.json", {"generated": True, "tasks": []})
    published, publish = _collect()
    asyncio.run(loop._heartbeat_if_blocked(publish))
    assert not published
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


def test_blocked_task_triggers_one_reminder_then_throttles():
    ctx.set_tenant("hb_unit_blocked")
    context.write_json("plan.json", {"generated": True, "tasks": [
        {"id": "t7", "title": "Усилить привлечение заявок", "role": "marketer",
         "status": "blocked", "blocked_reason": "бот: main.py не импортируется aiogram"},
    ]})
    published, publish = _collect()
    asyncio.run(loop._heartbeat_if_blocked(publish))
    assert len(published) == 1
    assert "Усилить привлечение" in published[0]["text"]

    published.clear()
    asyncio.run(loop._heartbeat_if_blocked(publish))
    assert not published, "повторный вызов сразу должен молчать (троттлинг)"
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


def test_forget_tenant_clears_heartbeat_state():
    loop._last_blocked_heartbeat["hb_unit_forget"] = 123.0
    loop.forget_tenant("hb_unit_forget")
    assert "hb_unit_forget" not in loop._last_blocked_heartbeat


# ── _engagement_stuck: Gap Analysis не должен ждать полного завершения плана ──
# (docs/prompts/system-audit-prompt.md, «Путь до идеального SaaS», Шаг 2 —
# раньше gap.replan() вызывался ТОЛЬКО внутри _engagement_complete(), и один
# застрявший blocked-таск останавливал Gap-driven replanning навсегда.)

def test_not_stuck_when_no_plan_generated():
    ctx.set_tenant("stuck_unit_no_plan")
    context.write_json("plan.json", {"generated": False, "tasks": []})
    assert not loop._engagement_stuck()
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


def test_not_stuck_when_no_blocked_tasks():
    ctx.set_tenant("stuck_unit_no_blocked")
    context.write_json("plan.json", {"generated": True, "tasks": [
        {"id": "t1", "status": "pending"},
        {"id": "t2", "status": "done"},
    ]})
    assert not loop._engagement_stuck()
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


def test_not_stuck_when_something_still_in_progress():
    """Заблокированная задача есть, но офис ещё что-то реально делает — не считаем
    план застрявшим, чтобы не подсовывать gap-задачу поверх легитимной работы."""
    ctx.set_tenant("stuck_unit_active_elsewhere")
    context.write_json("plan.json", {"generated": True, "tasks": [
        {"id": "t1", "status": "blocked"},
        {"id": "t2", "status": "in_progress"},
    ]})
    assert not loop._engagement_stuck()
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


def test_stuck_when_blocked_and_nothing_in_progress():
    ctx.set_tenant("stuck_unit_real")
    context.write_json("plan.json", {"generated": True, "tasks": [
        {"id": "t1", "status": "blocked"},
        {"id": "t2", "status": "pending"},
    ]})
    assert loop._engagement_stuck()
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


def test_stuck_plan_still_triggers_gap_replan():
    """Интеграционная проверка сквозь границу loop/gap: застрявший план с
    незакрытой измеримой целью реально порождает задачу через gap.replan() —
    не просто флаг _engagement_stuck()==True без последствий."""
    from src.office import gap, objectives
    ctx.set_tenant("stuck_unit_gap_integration")
    ctx.wipe()
    ctx.set_tenant("stuck_unit_gap_integration")
    objectives.add("Заявки в неделю", desired="10 заявок/неделю",
                   measured_by="leads.count() за 7 дней")
    context.write_json("plan.json", {"generated": True, "tasks": [
        {"id": "t1", "status": "blocked", "role": "developer"},
    ]})
    assert loop._engagement_stuck()
    created = gap.replan()
    assert created, "gap.replan() должен создать задачу под незакрытый разрыв"
    assert any(t.get("role") == "marketer" for t in created)
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


def _run():
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ✓ {name}")
            passed += 1
    print(f"ВСЕ {passed} ТЕСТОВ ПРОШЛИ")


if __name__ == "__main__":
    # Windows-консоль часто в cp1251 — "✓" ронял ЛЮБОЙ тест этого файла
    # UnicodeEncodeError ДО единой строки реального результата (found: весь
    # набор tests/*.py был непроверяем из этой сессии на Windows).
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    _run()
