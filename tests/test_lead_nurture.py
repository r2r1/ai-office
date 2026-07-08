"""
Юнит-тесты автодожима лидов (src/office/lead_nurture.py) —
docs/product-capability-gaps.md п.4: залежавшийся лид должен получать серию
сообщений САМ, без интеграций это TEST-заметка в историю, с интеграциями —
попытка реальной отправки.

    python tests/test_lead_nurture.py
"""

import asyncio
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.saas import context as ctx
from src.office import leads, lead_nurture


def _fresh(name: str) -> None:
    ctx.set_tenant(name)
    ctx.wipe()
    ctx.set_tenant(name)


def _backdate_lead(lead_id: str, hours_ago: float) -> None:
    """Автодожим срабатывает по возрасту лида — двигаем ts в прошлое напрямую
    в хранилище (публичного API для этого у leads.py нет и не должно быть)."""
    items = ctx.read_json("leads.json", [])
    for i in items:
        if i["id"] == lead_id:
            i["ts"] = time.time() - hours_ago * 3600
    ctx.write_json("leads.json", items)


def test_fresh_lead_gets_no_followup():
    _fresh("nurture_test_fresh")
    leads.add("site", "Иван", "+79990000000", "")
    n = asyncio.run(lead_nurture.run_due_followups())
    assert n == 0


def test_stale_lead_gets_first_step_as_test_note():
    _fresh("nurture_test_step1")
    lead = leads.add("site", "Иван", "+79990000000", "")
    _backdate_lead(lead["id"], 80)  # старше первого порога (72ч)
    n = asyncio.run(lead_nurture.run_due_followups())
    assert n == 1
    updated = leads.get(lead["id"])
    notes = [h["text"] for h in updated["history"] if h.get("kind") == "note"]
    assert any("Автодожим шаг 1/3" in t for t in notes)
    assert any("[TEST" in t for t in notes)  # без подключённых интеграций — mock


def test_same_step_not_sent_twice_in_one_cycle():
    _fresh("nurture_test_dedup")
    lead = leads.add("site", "Иван", "+79990000000", "")
    _backdate_lead(lead["id"], 80)
    asyncio.run(lead_nurture.run_due_followups())
    n_second = asyncio.run(lead_nurture.run_due_followups())
    assert n_second == 0  # шаг 1 уже отправлен, шаг 2 ещё не наступил (120ч)


def test_second_step_fires_after_next_threshold():
    _fresh("nurture_test_step2")
    lead = leads.add("site", "Иван", "+79990000000", "")
    _backdate_lead(lead["id"], 130)  # старше второго порога (120ч)
    asyncio.run(lead_nurture.run_due_followups())
    n2 = asyncio.run(lead_nurture.run_due_followups())
    assert n2 == 1
    updated = leads.get(lead["id"])
    notes = [h["text"] for h in updated["history"] if h.get("kind") == "note"]
    assert any("Автодожим шаг 2/3" in t for t in notes)


def test_contacted_lead_is_not_nurtured():
    _fresh("nurture_test_contacted")
    lead = leads.add("site", "Иван", "+79990000000", "")
    _backdate_lead(lead["id"], 80)
    leads.set_status(lead["id"], "contacted")
    n = asyncio.run(lead_nurture.run_due_followups())
    assert n == 0


def test_sequence_exhausts_after_all_steps():
    _fresh("nurture_test_exhaust")
    lead = leads.add("site", "Иван", "+79990000000", "")
    _backdate_lead(lead["id"], 500)  # старше всех трёх порогов сразу
    total = 0
    for _ in range(5):
        total += asyncio.run(lead_nurture.run_due_followups())
    assert total == len(lead_nurture.STEPS)  # ровно 3 шага, не больше


def _cleanup_test_tenants() -> None:
    for d in ctx.ROOT.glob("nurture_test_*"):
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
