"""
Управление моделями ИИ — глобальная модель по умолчанию + индивидуальные
модели для отдельных агентов.

Пользователь может задать одну модель всему офису или назначить каждому
агенту свою. Сохраняется в reports/models.json, переживает перезапуски.
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

MODELS_FILE = Path("reports/models.json")

# Стартовая модель по умолчанию (из .env или дефолт)
_default: str = os.getenv("LLM_MODEL", "qwen3-vl-plus")

# agent_id -> модель (если не задано — используется _default)
_per_agent: dict[str, str] = {}

# Подсказки популярных моделей для выпадающего списка в UI.
# Пользователь может ввести и любую другую вручную.
PRESETS = [
    {"id": "qwen3-vl-plus", "label": "Qwen3 VL Plus (быстро, дёшево)"},
    {"id": "qwen-max", "label": "Qwen Max (умнее)"},
    {"id": "gpt-4o", "label": "GPT-4o"},
    {"id": "gpt-4o-mini", "label": "GPT-4o mini (быстро)"},
    {"id": "claude-opus-4-8", "label": "Claude Opus 4.8 (топ)"},
    {"id": "claude-sonnet-4-6", "label": "Claude Sonnet 4.6"},
    {"id": "deepseek-chat", "label": "DeepSeek Chat"},
]


def get_default() -> str:
    return _default


def set_default(model: str) -> None:
    global _default
    if model.strip():
        _default = model.strip()
        _save()


def for_agent(agent_id: str) -> str:
    """Модель конкретного агента — индивидуальная или глобальная."""
    return _per_agent.get(agent_id, _default)


def set_for_agent(agent_id: str, model: str) -> None:
    """Назначает агенту индивидуальную модель. Пустая строка — сбросить к общей."""
    if not model.strip():
        _per_agent.pop(agent_id, None)
    else:
        _per_agent[agent_id] = model.strip()
    _save()


def assignments() -> dict[str, str]:
    return dict(_per_agent)


def reset() -> None:
    """Сбрасывает индивидуальные модели (глобальную оставляем как выбрана)."""
    global _per_agent
    _per_agent = {}
    _save()


def load() -> None:
    global _default, _per_agent
    if MODELS_FILE.exists():
        try:
            d = json.loads(MODELS_FILE.read_text(encoding="utf-8"))
            _default = d.get("default", _default)
            _per_agent = d.get("per_agent", {})
        except (json.JSONDecodeError, OSError):
            pass


def _save() -> None:
    MODELS_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {"default": _default, "per_agent": _per_agent}
    MODELS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
