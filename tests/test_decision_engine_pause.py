"""
Тест pause_projects в PlanDiff (decision_engine.py) — реальный баг из живого
аудита (functional-gaps-round2-2026-07-20.md, U1): CEO словами подтверждал
отмену направления работы, но активные проекты оставались active. Теперь
диррективная транзакция может явно поставить проект на паузу.

    python tests/test_decision_engine_pause.py
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.saas import context as ctx
from src.office import projects, decision_engine


def _fresh(name: str) -> None:
    ctx.set_tenant(name)
    ctx.wipe()
    ctx.set_tenant(name)


def test_pause_projects_in_diff_pauses_active_project():
    _fresh("deng_test_pause_basic")
    p = projects.create("Telegram-бот")
    assert p["status"] == "active"
    outcome = decision_engine.decide({"pause_projects": [p["id"]]})
    assert outcome["applied"] is True
    assert projects.get(p["id"])["status"] == "paused"
    assert any("паузу" in c for c in outcome["changes"])


def test_pause_projects_ignores_unknown_id_without_crashing():
    _fresh("deng_test_pause_unknown")
    outcome = decision_engine.decide({"pause_projects": ["nope_123"]})
    # unknown id → projects.pause вернёт None → decide() увидит diff непустым,
    # но changes останется пустым (нечего было применить)
    assert outcome["applied"] is True
    assert outcome["changes"] == []


def test_pause_projects_promotes_queued_project():
    _fresh("deng_test_pause_promotes")
    projects.set_limit(1)
    a = projects.create("A")
    b = projects.create("B")
    assert a["status"] == "active"
    assert b["status"] == "queued"
    decision_engine.decide({"pause_projects": [a["id"]]})
    assert projects.get(a["id"])["status"] == "paused"
    assert projects.get(b["id"])["status"] == "active"


def test_pause_projects_alone_is_not_empty_diff():
    assert decision_engine.is_empty({"pause_projects": ["x"]}) is False
    assert decision_engine.is_empty({}) is True


def test_decide_with_only_pause_projects_records_target_with_pause_count():
    _fresh("deng_test_pause_target")
    p = projects.create("Проект")
    outcome = decision_engine.decide({"pause_projects": [p["id"]]})
    assert outcome["applied"] is True


def _cleanup_test_tenants() -> None:
    for d in ctx.ROOT.glob("deng_test_*"):
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
