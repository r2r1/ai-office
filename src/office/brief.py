"""
Бриф клиента — то, что превращает универсальный офис в офис «под клиента».

Клиент присылает идею / соцсети / инструкции → онбординг формирует бриф →
офис работает именно над задачей клиента, а не над дефолтной.
"""

import asyncio
import json
from pathlib import Path
from typing import Optional

BRIEF_FILE = Path("reports/brief.json")

# Событие: бриф готов, офис может стартовать
ready = asyncio.Event()

_brief: dict = {}


def set_brief(data: dict) -> None:
    """Сохраняет готовый бриф и сигналит офису о старте."""
    global _brief
    _brief = data
    _save()
    ready.set()


def get() -> dict:
    return _brief


def is_ready() -> bool:
    return bool(_brief.get("summary"))


def research_question() -> str:
    """Вопрос для ресёрчера на основе брифа клиента."""
    if _brief.get("research_question"):
        return _brief["research_question"]
    niche = _brief.get("niche", "")
    goal = _brief.get("goal", "")
    if niche or goal:
        return (
            f"Проанализируй актуальные тренды 2026 года в нише: {niche}. "
            f"Цель клиента: {goal}. Найди что сейчас работает, кейсы, "
            f"каналы продвижения, как делать контент с максимальным охватом."
        )
    return ""


def summary() -> str:
    return _brief.get("summary", "")


def _save() -> None:
    BRIEF_FILE.parent.mkdir(parents=True, exist_ok=True)
    BRIEF_FILE.write_text(json.dumps(_brief, ensure_ascii=False, indent=2), encoding="utf-8")


def load() -> bool:
    """Загружает сохранённый бриф при перезапуске. True если бриф был."""
    global _brief
    if BRIEF_FILE.exists():
        try:
            _brief = json.loads(BRIEF_FILE.read_text(encoding="utf-8"))
            if is_ready():
                ready.set()
                return True
        except (json.JSONDecodeError, OSError):
            pass
    return False


def reset() -> None:
    global _brief
    _brief = {}
    ready.clear()
    if BRIEF_FILE.exists():
        BRIEF_FILE.unlink()
