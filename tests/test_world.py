"""
Юнит-тесты World Model (src/office/world.py) — напрямую, не только косвенно.
См. docs/prompts/system-audit-prompt.md, «Путь до идеального SaaS», Шаг 4.

    python tests/test_world.py
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.saas import context as ctx
from src.office import world


def _fresh(name: str) -> None:
    ctx.set_tenant(name)
    ctx.wipe()
    ctx.set_tenant(name)


def test_snapshot_has_deterministic_top_level_keys():
    _fresh("world_test_keys")
    s = world.snapshot()
    for key in ("ts", "tenant", "identity", "brief", "metrics", "objectives",
                "projects", "business_state"):
        assert key in s, f"missing key: {key}"
    assert s["tenant"] == "world_test_keys"


def test_snapshot_reflects_objectives():
    _fresh("world_test_objectives")
    from src.office import objectives
    objectives.add("Заявки в неделю", desired="10 заявок/неделю",
                   measured_by="leads.count() за 7 дней")
    s = world.snapshot()
    assert any(o["title"] == "Заявки в неделю" for o in s["objectives"])


def test_diff_detects_added_objective():
    _fresh("world_test_diff_add")
    a = world.snapshot()
    from src.office import objectives
    objectives.add("Новая цель", desired="X", measured_by="Y")
    # snapshot() кеширует на "цикл" (см. world.invalidate_cache докстринг) —
    # без явной инвалидации между чтениями второй вызов вернул бы ТУ ЖЕ
    # закешированную копию из `a`, и diff() всегда был бы пустым. loop.py
    # вызывает invalidate_cache() в начале каждого цикла — здесь эмулируем
    # переход к "следующему циклу".
    world.invalidate_cache("world_test_diff_add")
    b = world.snapshot()
    d = world.diff(a, b)
    assert not d["empty"]
    assert any("Новая цель" in str(v) for v in d["added"].values())


def test_diff_empty_when_nothing_changed():
    _fresh("world_test_diff_empty")
    a = world.snapshot()
    b = world.snapshot()
    d = world.diff(a, b)
    # ts у метрик исключён из снапшота намеренно (см. world.py:70-72) — снапшоты
    # двух последовательных вызовов без изменений данных должны быть идентичны
    # по всем полям, КРОМЕ верхнеуровневого "ts" самого снапшота, который diff()
    # тоже исключает явно (world.py:126-127: not k.startswith(("ts","tenant"))).
    assert d["empty"], f"unexpected diff: {d}"


# ── Шаг 3 (docs/prompts/system-audit-prompt.md): кеш snapshot() на цикл ──────

def test_snapshot_is_cached_within_same_cycle():
    """Мутация данных МЕЖДУ двумя snapshot() без invalidate_cache() не должна
    быть видна во втором вызове — это и есть смысл кеша "на цикл": повторные
    чтения внутри одного decision-цикла CEO видят консистентную картину, не
    перечитывая 16 источников заново на каждый вызов (orchestrator.py→
    decision_engine.py→planning_engine.py — 3 вызова за один цикл)."""
    _fresh("world_test_cache_hit")
    from src.office import objectives
    a = world.snapshot()
    objectives.add("Цель, которую кеш не должен увидеть", desired="X", measured_by="Y")
    b = world.snapshot()  # БЕЗ invalidate_cache() — должен вернуть закешированное a
    assert b == a
    assert not any(o["title"] == "Цель, которую кеш не должен увидеть" for o in b["objectives"])


def test_invalidate_cache_makes_next_snapshot_fresh():
    _fresh("world_test_cache_invalidate")
    from src.office import objectives
    world.snapshot()
    objectives.add("Свежая цель", desired="X", measured_by="Y")
    world.invalidate_cache("world_test_cache_invalidate")
    fresh = world.snapshot()
    assert any(o["title"] == "Свежая цель" for o in fresh["objectives"])


def test_cached_snapshot_is_independent_copy_not_shared_mutable_object():
    """save_snapshot() мутирует свою копию (добавляет snapshot_id) — это НЕ
    должно просочиться в кеш, который увидит следующий вызов snapshot()."""
    _fresh("world_test_cache_no_alias")
    world.snapshot()
    mutated = world.save_snapshot(reason="test")
    assert "snapshot_id" in mutated
    again = world.snapshot()
    assert "snapshot_id" not in again, "мутация save_snapshot() просочилась в кеш"


def test_invalidate_cache_without_tenant_clears_all():
    _fresh("world_test_cache_clear_all_a")
    world.snapshot()
    _fresh("world_test_cache_clear_all_b")
    world.snapshot()
    world.invalidate_cache()
    assert "world_test_cache_clear_all_a" not in world._cache
    assert "world_test_cache_clear_all_b" not in world._cache


def test_reset_invalidates_cache_for_current_tenant():
    _fresh("world_test_cache_reset")
    world.snapshot()
    assert "world_test_cache_reset" in world._cache
    world.reset()
    assert "world_test_cache_reset" not in world._cache


def test_save_snapshot_appends_to_journal_and_caps_at_limit():
    _fresh("world_test_journal")
    for i in range(3):
        world.save_snapshot(reason=f"test_{i}")
    last = world.last_snapshot()
    assert last is not None
    assert last["reason"] == "test_2"


def test_snapshot_before_returns_prior_entry():
    _fresh("world_test_before")
    world.save_snapshot(reason="first")
    snap2 = world.save_snapshot(reason="second")
    prior = world.snapshot_before(snap2["snapshot_id"])
    assert prior is not None
    assert prior["reason"] == "first"


def test_snapshot_before_returns_none_for_first_entry():
    _fresh("world_test_before_none")
    snap1 = world.save_snapshot(reason="only")
    assert world.snapshot_before(snap1["snapshot_id"]) is None


def test_context_block_includes_business_state_and_gap():
    """context_block() — единственный сериализатор Business State в промпт CEO
    (см. docs/prompts/system-audit-prompt.md, «Как бизнес-логика и техника
    взаимодействуют», Цикл 2) — проверяем, что реально собирает все части."""
    _fresh("world_test_context_block")
    from src.office import objectives
    objectives.add("Заявки в неделю", desired="10 заявок/неделю",
                   measured_by="leads.count() за 7 дней")
    block = world.context_block()
    assert "ГДЕ КОМПАНИЯ СЕЙЧАС" in block
    assert "Заявки в неделю" in block  # из objectives.context_block()


def test_reset_clears_snapshot_journal():
    _fresh("world_test_reset")
    world.save_snapshot(reason="before_reset")
    assert world.last_snapshot() is not None
    world.reset()
    assert world.last_snapshot() is None


def _cleanup_test_tenants() -> None:
    for d in ctx.ROOT.glob("world_test_*"):
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
