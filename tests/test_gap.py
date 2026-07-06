"""
Юнит-тесты Gap Analysis (src/office/gap.py) — покрывает Шаг 1 и Шаг 2 из
docs/prompts/system-audit-prompt.md «Путь до идеального SaaS»:
  Шаг 1: whitelist метрик для measured_by + явный сигнал "не резолвится"
         (gap.resolvable(), objectives.context_block())
  Шаг 2: Gap Analysis не заперт внутри "план полностью завершён"
         (см. tests/test_loop_heartbeat.py-подобный паттерн для loop.py части)

    python tests/test_gap.py
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.saas import context as ctx
from src.office import gap, objectives


def _fresh(name: str) -> None:
    ctx.set_tenant(name)
    ctx.wipe()
    ctx.set_tenant(name)


# ── Шаг 1: resolvable() и её использование ───────────────────────────────────

def test_resolvable_true_for_known_leads_metric():
    assert gap.resolvable("leads.count() за 7 дней")
    assert gap.resolvable("Количество лидов")
    assert gap.resolvable("заявки за неделю")


def test_resolvable_false_for_unknown_metric():
    assert not gap.resolvable("MRR growth month over month")
    assert not gap.resolvable("Конверсия в оплату")


def test_resolvable_false_for_empty_measured_by():
    assert not gap.resolvable("")
    assert not gap.resolvable(None)


def test_current_value_and_resolvable_agree():
    """_current_value() и resolvable() должны использовать ОДИН источник правды
    (_METRIC_RESOLVERS) — не должно быть случая, когда resolvable()==True, но
    _current_value() всё равно вернула None (или наоборот)."""
    _fresh("gap_test_agree")
    resolvable_obj = {"measured_by": "лидов в неделю"}
    unresolvable_obj = {"measured_by": "MRR"}
    assert gap.resolvable(resolvable_obj["measured_by"])
    assert gap._current_value(resolvable_obj) is not None
    assert not gap.resolvable(unresolvable_obj["measured_by"])
    assert gap._current_value(unresolvable_obj) is None


def test_context_block_flags_unresolved_objective_explicitly():
    """Раньше objective с неизвестным measured_by выглядела как обычная
    отслеживаемая цель в промпте CEO — теперь явно помечена."""
    _fresh("gap_test_context_unresolved")
    objectives.add("Рост MRR", desired="+20%", measured_by="MRR")
    block = objectives.context_block()
    assert "НЕ отслеживается автоматически" in block
    assert "MRR" in block


def test_context_block_shows_normal_metric_for_resolvable_objective():
    _fresh("gap_test_context_resolved")
    objectives.add("Заявки в неделю", desired="10 заявок/неделю",
                   measured_by="leads.count() за 7 дней")
    block = objectives.context_block()
    assert "метрика: leads.count()" in block
    assert "НЕ отслеживается" not in block


def test_unresolvable_objective_excluded_from_gap_compute():
    """Подтверждение существующего (осознанного) поведения: неизвестная метрика
    не попадает в compute()/unmet() — resolvable() лишь делает это ВИДИМЫМ,
    не меняет сам факт исключения (см. докстринг gap.py)."""
    _fresh("gap_test_excluded_from_compute")
    objectives.add("Рост MRR", desired="+20%", measured_by="MRR")
    gaps = gap.compute()
    assert not any(g["title"] == "Рост MRR" for g in gaps)


def test_world_snapshot_marks_objective_resolvable_field():
    _fresh("gap_test_world_field")
    from src.office import world
    objectives.add("Заявки в неделю", desired="10", measured_by="лиды за неделю")
    objectives.add("Рост MRR", desired="+20%", measured_by="MRR")
    s = world.snapshot()
    by_title = {o["title"]: o for o in s["objectives"]}
    assert by_title["Заявки в неделю"]["resolvable"] is True
    assert by_title["Рост MRR"]["resolvable"] is False


def _cleanup_test_tenants() -> None:
    for d in ctx.ROOT.glob("gap_test_*"):
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
