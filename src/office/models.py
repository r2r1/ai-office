"""
Выбор LLM-модели: глобальная модель тенанта + индивидуальные на агента (по тенанту).
Хранится в data/tenants/<tid>/models.json. PRESETS — общий каталог с расценками.
"""

import os

from dotenv import load_dotenv

from src.saas import context as ctx

load_dotenv()

_FILE = "models.json"

DEFAULT_FREE_MODEL = "glm-4.5-flash"
ENV_DEFAULT = os.getenv("LLM_MODEL", DEFAULT_FREE_MODEL)

# Каталог моделей с расценками apinet (вход/выход за 1M) — от дешёвых к топовым.
PRESETS = [
    {"id": "glm-4.5-flash",          "label": "GLM-4.5 Flash · $0.01/$0.01 за 1M · почти бесплатно ⭐"},
    {"id": "gpt-5-nano",             "label": "GPT-5 nano · $0.05/$0.40 за 1M · дёшево"},
    {"id": "gpt-5-codex",            "label": "GPT-5 Codex · $1.25/$10 за 1M · для кода"},
    {"id": "gpt-4.1-nano",           "label": "GPT-4.1 nano · $0.10/$0.40 за 1M"},
    {"id": "gpt-5.4",                "label": "GPT-5.4 · $2.5/$15 за 1M · умная, не из дешёвых"},
    {"id": "gpt-4o-mini",            "label": "GPT-4o mini · $0.15/$0.61 за 1M"},
    {"id": "qwen3-vl-flash",         "label": "Qwen3 VL Flash · $0.15/$1.50 за 1M · vision"},
    {"id": "kimi-k2",                "label": "Kimi K2 · $0.60/$1.50 за 1M"},
    {"id": "qwen3-vl-plus",          "label": "Qwen3 VL Plus · $1/$10 за 1M"},
    {"id": "gpt-4.1",                "label": "GPT-4.1 · $2/$8 за 1M"},
    {"id": "gpt-4o",                 "label": "GPT-4o · $2.5/$10 за 1M"},
    {"id": "claude-sonnet-4-6",      "label": "Claude Sonnet 4.6 · $3/$15 за 1M"},
    {"id": "claude-opus-4-8",        "label": "Claude Opus 4.8 · $5/$25 за 1M · топ"},
]


def _cfg() -> dict:
    return ctx.read_json(_FILE, {"default": ENV_DEFAULT, "per_agent": {}})


def get_default() -> str:
    return _cfg().get("default", ENV_DEFAULT)


def set_default(model: str) -> None:
    if model.strip():
        cfg = _cfg()
        cfg["default"] = model.strip()
        ctx.write_json(_FILE, cfg)


# Роли, которым осмысленно назначать отдельную модель (для UI-списка).
# По умолчанию НИ ОДНА не переопределена — все берут глобальную модель тенанта.
ROLE_LABELS = {
    "orchestrator": "CEO / оркестрация",
    "cto": "CTO (лидер)", "cmo": "CMO (лидер)", "sales_lead": "Head of Sales (лидер)",
    "researcher": "Ресёрчер", "strategist": "Стратег", "architect": "Архитектор",
    "designer": "Дизайнер", "developer": "Разработчик", "integrator": "Интегратор",
    "marketer": "Маркетолог", "salesman": "Продажник", "analyst": "Аналитик",
}


def _role_of(agent_id: str) -> str:
    """developer_1 → developer (отрезаем числовой суффикс)."""
    return agent_id.rsplit("_", 1)[0] if "_" in agent_id else agent_id


def for_agent(agent_id: str) -> str:
    """
    Модель агента: точечная на agent_id → на роль → режим качества (capability) →
    глобальная по умолчанию. Режим качества переопределяет лишь специализированные
    capability (код/картинки/видео); если режим прозрачен — берётся дефолт офиса.
    """
    cfg = _cfg()
    pa = cfg.get("per_agent", {})
    if agent_id in pa:
        return pa[agent_id]
    role = _role_of(agent_id)
    pr = cfg.get("per_role", {})
    if role in pr:
        return pr[role]
    # Режим качества (capabilities) — мягкий слой поверх дефолта офиса.
    try:
        from src.office import capabilities
        cap_model = capabilities.model_for_role(role)
        if cap_model:
            return cap_model
    except Exception:
        pass
    return cfg.get("default", ENV_DEFAULT)


def set_for_agent(agent_id: str, model: str) -> None:
    cfg = _cfg()
    pa = cfg.setdefault("per_agent", {})
    if not model.strip():
        pa.pop(agent_id, None)
    else:
        pa[agent_id] = model.strip()
    ctx.write_json(_FILE, cfg)


def for_role(role: str) -> str:
    """Модель роли (или глобальная, если не переопределена)."""
    cfg = _cfg()
    return cfg.get("per_role", {}).get(role, cfg.get("default", ENV_DEFAULT))


def set_for_role(role: str, model: str) -> None:
    """Назначить/сбросить модель для роли. Пустая строка = сброс (вернётся к глобальной)."""
    cfg = _cfg()
    pr = cfg.setdefault("per_role", {})
    if not (model or "").strip():
        pr.pop(role, None)
    else:
        pr[role] = model.strip()
    ctx.write_json(_FILE, cfg)


def role_assignments() -> dict:
    """Текущие переопределения по ролям (только заданные)."""
    return dict(_cfg().get("per_role", {}))


def role_catalog() -> list[dict]:
    """Список ролей для UI с текущей моделью (или '' = по умолчанию)."""
    pr = _cfg().get("per_role", {})
    return [{"role": r, "label": lbl, "model": pr.get(r, "")} for r, lbl in ROLE_LABELS.items()]


def assignments() -> dict:
    return dict(_cfg().get("per_agent", {}))


def load() -> None:
    pass


def reset() -> None:
    """Сбрасывает индивидуальные модели, глобальную оставляет."""
    cfg = _cfg()
    cfg["per_agent"] = {}
    cfg["per_role"] = {}
    ctx.write_json(_FILE, cfg)
