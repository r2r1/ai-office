"""
Тест prior_blockers — unblock() больше не стирает причину провала бесследно
(functional-gaps-round2-2026-07-20.md, N2): раньше исполнитель, получивший
задачу заново после разблокировки владельцем, не знал АБСОЛЮТНО НИЧЕГО о
том, почему она уже 3 раза провалилась, и рисковал повторить тот же провал.

    python tests/test_prior_blockers.py
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.saas import context as ctx
from src.office import plan


def _wipe(tid: str):
    ctx.set_tenant(tid)
    ctx.wipe()
    ctx.set_tenant(tid)


def test_unblock_still_clears_active_last_feedback_and_blocked_reason():
    _wipe("prior_blockers_clear_active")
    t = plan.add_task("Собрать бренд-бук", "designer", project_id="p1")
    plan.block(t["id"], "не удаётся получить ответ владельца")
    plan.unblock(t["id"])
    got = plan.get_task(t["id"])
    assert got["blocked_reason"] == ""
    assert got["last_feedback"] == ""
    assert got["attempts"] == 0


def test_unblock_moves_blocked_reason_into_prior_blockers():
    _wipe("prior_blockers_moves_reason")
    t = plan.add_task("Собрать бренд-бук", "designer", project_id="p1")
    plan.block(t["id"], "нет доступа к Figma-макету")
    plan.unblock(t["id"])
    got = plan.get_task(t["id"])
    assert got["prior_blockers"] == ["нет доступа к Figma-макету"]


def test_unblock_falls_back_to_last_feedback_when_no_blocked_reason():
    _wipe("prior_blockers_fallback_feedback")
    t = plan.add_task("Собрать бренд-бук", "designer", project_id="p1")
    plan.set_feedback(t["id"], "критик отклонил: логотип не читается на тёмном фоне")
    plan.block(t["id"], "")
    plan.unblock(t["id"])
    got = plan.get_task(t["id"])
    assert got["prior_blockers"] == ["критик отклонил: логотип не читается на тёмном фоне"]


def test_prior_blockers_accumulate_across_multiple_unblocks():
    _wipe("prior_blockers_accumulate")
    t = plan.add_task("Собрать бренд-бук", "designer", project_id="p1")
    plan.block(t["id"], "причина 1")
    plan.unblock(t["id"])
    plan.block(t["id"], "причина 2")
    plan.unblock(t["id"])
    got = plan.get_task(t["id"])
    assert got["prior_blockers"] == ["причина 1", "причина 2"]


def test_prior_blockers_capped_at_max():
    _wipe("prior_blockers_capped")
    t = plan.add_task("Собрать бренд-бук", "designer", project_id="p1")
    for i in range(5):
        plan.block(t["id"], f"причина {i}")
        plan.unblock(t["id"])
    got = plan.get_task(t["id"])
    assert len(got["prior_blockers"]) == 3
    assert got["prior_blockers"] == ["причина 2", "причина 3", "причина 4"]


def _cleanup_test_tenants() -> None:
    for d in ctx.ROOT.glob("prior_blockers_*"):
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
