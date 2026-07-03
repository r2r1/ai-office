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


def _run():
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ✓ {name}")
            passed += 1
    print(f"ВСЕ {passed} ТЕСТОВ ПРОШЛИ")


if __name__ == "__main__":
    _run()
