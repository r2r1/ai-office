"""
Юнит-тесты реального бронирования (src/office/booking.py) — защита от двойной
записи и разбор дат, введённых человеком (docs/product-capability-gaps.md п.2).

    python tests/test_booking.py
"""

import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.saas import context as ctx
from src.office import booking


def _fresh(name: str) -> None:
    ctx.set_tenant(name)
    ctx.wipe()
    ctx.set_tenant(name)


def test_parse_dm_without_year_assumes_current_or_next():
    now = datetime(2026, 1, 10)
    assert booking.parse_datetime("15.07 14:00", now=now) == ("2026-07-15", "14:00")
    # дата уже прошла в этом году → следующий год
    assert booking.parse_datetime("05.01 09:00", now=now) == ("2027-01-05", "09:00")


def test_parse_iso_format():
    assert booking.parse_datetime("2026-07-15 14:00") == ("2026-07-15", "14:00")


def test_parse_unrecognized_returns_none():
    assert booking.parse_datetime("завтра днём") is None
    assert booking.parse_datetime("") is None


def test_book_then_slot_is_no_longer_free():
    _fresh("bk_test_conflict")
    assert booking.is_free("2026-08-01", "14:00", 60)
    b = booking.book("2026-08-01", "14:00", "Иван", "+79990000000", "Стрижка", duration_min=60)
    assert b is not None
    assert not booking.is_free("2026-08-01", "14:00", 60)
    # перекрывающийся интервал (14:30-15:30 пересекается с 14:00-15:00)
    assert not booking.is_free("2026-08-01", "14:30", 60)
    # НЕ пересекается (15:00-16:00 начинается ровно на границе)
    assert booking.is_free("2026-08-01", "15:00", 60)


def test_book_conflicting_slot_returns_none():
    _fresh("bk_test_double_book")
    first = booking.book("2026-08-02", "10:00", "A", "111", duration_min=60)
    assert first is not None
    second = booking.book("2026-08-02", "10:00", "B", "222", duration_min=60)
    assert second is None  # двойная запись отклонена


def test_suggest_alternatives_skips_booked_slot():
    _fresh("bk_test_alts")
    booking.book("2026-08-03", "09:00", "A", "111", duration_min=60)
    alts = booking.suggest_alternatives("2026-08-03", duration_min=60, limit=3)
    assert "2026-08-03 09:00" not in alts
    assert len(alts) == 3


def test_attach_lead_updates_booking():
    _fresh("bk_test_attach")
    b = booking.book("2026-08-04", "11:00", "A", "111", duration_min=60)
    booking.attach_lead(b["id"], "lead_xyz")
    found = [x for x in booking.list_for_date("2026-08-04") if x["id"] == b["id"]][0]
    assert found["lead_id"] == "lead_xyz"


def test_cancel_frees_the_slot():
    _fresh("bk_test_cancel")
    b = booking.book("2026-08-05", "12:00", "A", "111", duration_min=60)
    assert not booking.is_free("2026-08-05", "12:00", 60)
    booking.cancel(b["id"])
    assert booking.is_free("2026-08-05", "12:00", 60)


def _cleanup_test_tenants() -> None:
    for d in ctx.ROOT.glob("bk_test_*"):
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
