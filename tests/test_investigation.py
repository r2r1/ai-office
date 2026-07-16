"""
Первое расследование компании (Company Investigation) — docs/first-investigation-
plan-2026-07-16.md, Фаза 4: живой агентский диалог вместо жёсткого 2-шагового
скрипта. Мокаем llm.run_agent (без реального платного вызова LLM), проверяем
только логику investigation.py: персистентную историю, сборку брифа из
finish_investigation, сброс состояния.

Запуск: python tests/test_investigation.py
"""

import asyncio
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.office import investigation
from src.office import brief as brief_module
from src.saas import context as ctx


def _fresh_tenant(name: str) -> None:
    ctx.set_tenant(name)
    ctx.wipe()
    ctx.set_tenant(name)


def test_active_false_before_first_turn():
    _fresh_tenant("investigation_active_unit")
    assert investigation.active() is False
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


def test_run_turn_without_finish_persists_history_and_not_finished():
    _fresh_tenant("investigation_persist_unit")

    async def fake_run_agent(**kwargs):
        assert kwargs["history"] == []  # первый ход — истории ещё нет
        return "Расскажите чуть больше про нишу?"

    with patch("src.core.llm.run_agent", side_effect=fake_run_agent):
        reply, finished = asyncio.run(investigation.run_turn("корпусная мебель"))

    assert finished is False
    assert "нишу" in reply
    assert investigation.active() is True
    assert brief_module.is_ready() is False
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


def test_run_turn_second_call_sees_prior_history():
    _fresh_tenant("investigation_history_unit")

    async def first_call(**kwargs):
        return "Уточните регион?"
    with patch("src.core.llm.run_agent", side_effect=first_call):
        asyncio.run(investigation.run_turn("корпусная мебель"))

    seen_history = {}

    async def second_call(**kwargs):
        seen_history["history"] = list(kwargs["history"])  # копия — история мутируется после вызова
        return "Понял, ищу дальше."
    with patch("src.core.llm.run_agent", side_effect=second_call):
        asyncio.run(investigation.run_turn("КМВ"))

    assert seen_history["history"] == [
        {"role": "user", "content": "корпусная мебель"},
        {"role": "assistant", "content": "Уточните регион?"},
    ]
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


def test_run_turn_finish_investigation_saves_brief_and_resets_state():
    _fresh_tenant("investigation_finish_unit")

    async def fake_run_agent(**kwargs):
        handler = kwargs["tool_handlers"]["finish_investigation"]
        await handler({
            "summary": "Корпусная мебель на заказ в КМВ.",
            "niche": "корпусная мебель",
            "goal": "привлечь заявки",
            "audience": "жители КМВ",
            "business_stage_key": "growth",
            "business_stage_label": "в активном росте",
            "business_stage_reason": "нашёл в 2ГИС с отзывами",
            "business_stage_confidence": "inferred",
        })
        return "Принял, команда приступает!"

    with patch("src.core.llm.run_agent", side_effect=fake_run_agent):
        reply, finished = asyncio.run(investigation.run_turn("Мебель+ КМВ"))

    assert finished is True
    assert "Принял" in reply
    assert brief_module.is_ready() is True
    b = brief_module.get()
    assert b["niche"] == "корпусная мебель"
    assert b["business_stage"]["key"] == "growth"
    assert b["business_stage"]["confidence"] == "inferred"
    assert investigation.active() is False  # состояние сброшено
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


def test_finish_investigation_rejects_invalid_enum_values_conservatively():
    """Модель может вернуть мусор вместо enum-значения — не должно упасть и не
    должно выдать БОЛЬШЕ уверенности, чем есть (см. Фаза 2)."""
    _fresh_tenant("investigation_finish_invalid_unit")

    async def fake_run_agent(**kwargs):
        handler = kwargs["tool_handlers"]["finish_investigation"]
        await handler({
            "summary": "тест", "niche": "тест", "goal": "тест",
            "business_stage_key": "не знаю", "business_stage_label": "х",
            "business_stage_reason": "х", "business_stage_confidence": "очень уверен",
        })
        return "готово"

    with patch("src.core.llm.run_agent", side_effect=fake_run_agent):
        asyncio.run(investigation.run_turn("тест"))

    b = brief_module.get()
    assert b["business_stage"]["key"] == "idea"          # безопасный дефолт
    assert b["business_stage"]["confidence"] == "unconfirmed"  # безопасный дефолт
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


def test_run_turn_passes_web_search_and_finish_tool_to_run_agent():
    _fresh_tenant("investigation_wiring_unit")
    captured = {}

    async def fake_run_agent(**kwargs):
        captured.update(kwargs)
        return "ок"

    with patch("src.core.llm.run_agent", side_effect=fake_run_agent):
        asyncio.run(investigation.run_turn("тест"))

    assert captured["use_search"] is True
    assert captured["max_searches"] == 3
    tool_names = {t["function"]["name"] for t in captured["extra_tools"]}
    assert "finish_investigation" in tool_names
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
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    _run()
