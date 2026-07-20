"""
Резерв бюджета ДО исполнения (production-readiness worklist п.2) —
src/office/costs.py reserve()/release_reservation()/reserved(): would_exceed()
должен учитывать УЖЕ зарезервированные, но ещё не record()'нутые суммы,
иначе несколько параллельных задач могли независимо пройти проверку по
одному и тому же totals() и совместно проскочить лимит.

    python tests/test_costs_reservation.py
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.saas import context as ctx
from src.office import costs


def _fresh(name: str) -> None:
    ctx.set_tenant(name)
    ctx.wipe()
    ctx.set_tenant(name)


def test_reserve_increases_reserved():
    _fresh("costs_res_basic")
    assert costs.reserved() == 0.0
    costs.reserve(0.5)
    assert costs.reserved() == 0.5
    costs.reserve(0.25)
    assert costs.reserved() == 0.75


def test_release_reservation_decreases_reserved():
    _fresh("costs_res_release")
    costs.reserve(1.0)
    costs.release_reservation(0.4)
    assert abs(costs.reserved() - 0.6) < 1e-9


def test_release_reservation_never_goes_negative():
    _fresh("costs_res_floor")
    costs.reserve(0.1)
    costs.release_reservation(999)
    assert costs.reserved() == 0.0


def test_would_exceed_accounts_for_reserved_amount():
    """Ядро фикса: totals()["cost"]=0, лимит=$1, но $0.9 уже ЗАРЕЗЕРВИРОВАНО
    другой параллельной задачей — новая оценка $0.5 обязана считаться
    превышением, хотя record() ещё ничего не списал."""
    _fresh("costs_res_would_exceed")
    costs.set_limits(total_usd=1.0)
    assert costs.would_exceed(0.5) is False  # без резерва — укладывается
    costs.reserve(0.9)
    assert costs.would_exceed(0.5) is True  # с резервом — уже нет


def test_reserved_is_per_tenant():
    _fresh("costs_res_tenant_a")
    costs.reserve(0.7)
    assert costs.reserved() == 0.7
    _fresh("costs_res_tenant_b")
    assert costs.reserved() == 0.0  # чужой резерв не виден


def test_full_reserve_then_release_cycle_matches_record():
    """Симулирует run_task(): reserve перед вызовом → record() реальной
    стоимости → release_reservation того же estimated_usd — reserved()
    возвращается к нулю, totals() отражает РЕАЛЬНУЮ, а не оценочную сумму."""
    _fresh("costs_res_cycle")
    estimated = 0.3
    costs.reserve(estimated)
    costs.record("developer_1", "gpt-5.4", 1000, 500)  # реальная стоимость != estimated
    costs.release_reservation(estimated)
    assert costs.reserved() == 0.0
    assert costs.totals()["cost"] > 0


def _cleanup_test_tenants() -> None:
    for d in ctx.ROOT.glob("costs_res_*"):
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
