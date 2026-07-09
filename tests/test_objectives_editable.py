"""
Юнит-тест: автоматическая цель "10 заявок/неделю" (objectives.py::
ensure_leads_objective) должна быть редактируемой — реальная жалоба клиента
после прогона (лог 2026-07-09): "откуда взялось 10 и нет способа поменять".
Бэкенд (objectives.update) уже это умел, интерфейс (CompanyView.tsx GoalsTab)
не давал редактировать существующие цели — только добавлять новые и
архивировать. Этот тест фиксирует контракт бэкенда, на который опирается фикс.

    python tests/test_objectives_editable.py
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.saas import context as ctx
from src.office import objectives


def _fresh(name: str) -> None:
    ctx.set_tenant(name)
    ctx.wipe()
    ctx.set_tenant(name)


def test_auto_leads_objective_has_default_10_per_week():
    _fresh("obj_test_default")
    obj = objectives.ensure_leads_objective()
    assert obj["desired"] == "10 заявок/неделю"
    assert obj["source"] == "company"


def test_auto_leads_objective_desired_is_editable():
    _fresh("obj_test_edit")
    obj = objectives.ensure_leads_objective()
    updated = objectives.update(obj["id"], desired="25 заявок/неделю")
    assert updated["desired"] == "25 заявок/неделю"
    stored = [o for o in objectives.all_objectives() if o["id"] == obj["id"]][0]
    assert stored["desired"] == "25 заявок/неделю"


def test_ensure_leads_objective_idempotent_after_edit():
    _fresh("obj_test_idempotent")
    obj = objectives.ensure_leads_objective()
    objectives.update(obj["id"], desired="25 заявок/неделю")
    # Повторный вызов при новой публикации сайта НЕ должен затереть правку клиента
    again = objectives.ensure_leads_objective()
    assert again is None  # уже есть измеримая цель по заявкам — новую не создаёт
    stored = [o for o in objectives.all_objectives() if o["id"] == obj["id"]][0]
    assert stored["desired"] == "25 заявок/неделю"


def _cleanup_test_tenants() -> None:
    for d in ctx.ROOT.glob("obj_test_*"):
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
