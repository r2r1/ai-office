"""
Юнит-тесты минимального онбординга (BOS §5): результат первого впечатления
клиента (office/onboarding_result.py) и подсказка интеграций по тексту брифа
(integrations/registry.suggested_for). Без LLM, $0.

    python tests/test_onboarding_result.py
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.saas import context as ctx
from src.office import onboarding_result
from src.integrations import registry as integrations_registry


def _fresh(name: str) -> None:
    ctx.set_tenant(name)
    ctx.wipe()
    ctx.set_tenant(name)


# ── onboarding_result: идемпотентность (рестарт офиса не должен дублировать) ──

def test_exists_false_before_save():
    _fresh("obr_test_not_exists")
    assert onboarding_result.exists() is False
    assert onboarding_result.get() == {}


def test_save_and_get_roundtrip():
    _fresh("obr_test_roundtrip")
    onboarding_result.save(["вывод 1", "вывод 2"], ["точка роста 1"], ["i_abc123"])
    assert onboarding_result.exists() is True
    d = onboarding_result.get()
    assert d["analysis"] == ["вывод 1", "вывод 2"]
    assert d["growth_points"] == ["точка роста 1"]
    assert d["initiative_ids"] == ["i_abc123"]
    assert "ts" in d


def test_reset_clears():
    _fresh("obr_test_reset")
    onboarding_result.save(["x"], [], [])
    assert onboarding_result.exists() is True
    onboarding_result.reset()
    assert onboarding_result.exists() is False


# ── suggested_for: подбор интеграций по ключевым словам брифа ────────────────

def test_suggested_for_matches_telegram_bot_keywords():
    _fresh("obr_test_suggest_telegram")
    out = integrations_registry.suggested_for("Хочу бот для приёма заявок в телеграм")
    names = [i["name"] for i in out]
    assert "telegram" in names


def test_suggested_for_matches_multiple_relevant_integrations():
    _fresh("obr_test_suggest_multi")
    text = "Нужна таблица для учёта клиентов и рассылка по email"
    out = integrations_registry.suggested_for(text)
    names = {i["name"] for i in out}
    assert "google_sheets" in names
    assert "gmail" in names


def test_suggested_for_empty_text_returns_nothing():
    _fresh("obr_test_suggest_empty")
    assert integrations_registry.suggested_for("") == []
    assert integrations_registry.suggested_for("просто общие слова без триггеров") == []


def test_suggested_for_caps_at_three():
    _fresh("obr_test_suggest_cap")
    text = "бот телеграм таблица гугл документ календарь запись почта рассылка код github репозиторий"
    out = integrations_registry.suggested_for(text)
    assert len(out) <= 3


def test_suggested_for_includes_connected_flag():
    _fresh("obr_test_suggest_connected_flag")
    out = integrations_registry.suggested_for("нужен бот телеграм")
    assert out and "connected" in out[0]


def _cleanup_test_tenants() -> None:
    for d in ctx.ROOT.glob("obr_test_*"):
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
