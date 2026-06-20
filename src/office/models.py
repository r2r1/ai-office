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

# Стартовая модель по умолчанию (из .env или дефолт).
# glm-4.5-flash — практически бесплатна ($0.01/$0.01 за 1M) и умеет tools/reasoning,
# что подходит для агентного офиса. Идеально для демо и первого запуска.
DEFAULT_FREE_MODEL = "glm-4.5-flash"
_default: str = os.getenv("LLM_MODEL", DEFAULT_FREE_MODEL)

# agent_id -> модель (если не задано — используется _default)
_per_agent: dict[str, str] = {}

# Подсказки моделей для выпадающего списка в UI — с расценками apinet.cloud
# (вход/выход за 1M токенов), отсортированы от дешёвых к топовым, чтобы пользователь
# мог сравнить цену и возможности. Можно ввести и любую другую модель вручную.
# Цены актуальны на момент составления (apinet.cloud/pricing) и могут меняться.
PRESETS = [
    {"id": "glm-4.5-flash",          "label": "GLM-4.5 Flash · $0.01/$0.01 за 1M · почти бесплатно ⭐"},
    {"id": "gpt-5-nano",             "label": "GPT-5 nano · $0.05/$0.40 за 1M · дёшево"},
    {"id": "gpt-5.3-codex",          "label": "GPT-5.3 Codex · $0.08/$0.64 за 1M · для кода"},
    {"id": "gpt-4.1-nano",           "label": "GPT-4.1 nano · $0.10/$0.40 за 1M"},
    {"id": "gpt-5.4",                "label": "GPT-5.4 · $0.12/$0.72 за 1M · баланс цена/ум"},
    {"id": "gpt-4o-mini",            "label": "GPT-4o mini · $0.15/$0.61 за 1M"},
    {"id": "qwen3-vl-flash",         "label": "Qwen3 VL Flash · $0.15/$1.50 за 1M · vision"},
    {"id": "kimi-k2",                "label": "Kimi K2 · $0.60/$1.50 за 1M"},
    {"id": "qwen3-vl-plus",          "label": "Qwen3 VL Plus · $1/$10 за 1M"},
    {"id": "gpt-4.1",                "label": "GPT-4.1 · $2/$8 за 1M"},
    {"id": "gpt-4o",                 "label": "GPT-4o · $2.5/$10 за 1M"},
    {"id": "claude-sonnet-4-6",      "label": "Claude Sonnet 4.6 · $3/$15 за 1M"},
    {"id": "claude-opus-4-8",        "label": "Claude Opus 4.8 · $5/$25 за 1M · топ"},
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
