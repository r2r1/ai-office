"""
Unit-тесты Execution (Phase 6, расслоение loop.py) — чистые помощники и состояние
живости БЕЗ поднятия офис-цикла (run_task/assign требуют LLM и здесь не гоняются).

    python tests/test_execution.py
"""

import sys
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.office import execution as ex
from src.saas import context as ctx, context


def test_tk_isolates_by_tenant():
    ctx.set_tenant("t_a")
    assert ex.tk("developer_1") == "t_a:developer_1"
    ctx.set_tenant("t_b")
    assert ex.tk("developer_1") == "t_b:developer_1"


def test_current_milestone_state():
    ctx.set_tenant("exec_unit_ms")
    ex.set_cur_ms("build")
    assert ex.cur_ms() == "build"


def test_forget_tenant_clears_liveness():
    ctx.set_tenant("exec_unit_forget")
    ex.set_cur_ms("x")
    ex._thinking_since["exec_unit_forget:a"] = 1.0
    ex._agent_task["exec_unit_forget:a"] = "t1"
    ex._model_fail_count["exec_unit_forget:a"] = 2
    ex.forget_tenant("exec_unit_forget")
    assert not any(k.startswith("exec_unit_forget:") for k in ex._thinking_since)
    assert not any(k.startswith("exec_unit_forget:") for k in ex._agent_task)
    assert not any(k.startswith("exec_unit_forget:") for k in ex._model_fail_count)
    assert ex.cur_ms() == ""  # _current_ms этого тенанта тоже очищен


def test_engagement_needs_bot():
    ctx.set_tenant("exec_unit_bot")
    context.write_json("brief.json", {"goal": "нужен телеграм-бот записи", "niche": "салон"})
    assert ex.engagement_needs_bot() is True
    context.write_json("brief.json", {"goal": "лендинг под звонки", "niche": "потолки"})
    assert ex.engagement_needs_bot() is False
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
    _run()
