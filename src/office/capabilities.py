"""
Слой возможностей (Capabilities) и режимов качества — Execution Engine.

Пользователь мыслит не моделями, а качеством: выбирает РЕЖИМ (🟣 Экономия →
⚫ Эксперт), а система сама подбирает лучшую модель под ТИП задачи (capability).
«Основная модель ≠ единственная модель»: код может уходить на одну модель,
картинки — на другую, видео — на третью.

Хранилище: data/tenants/<tid>/capabilities.json
  {"mode": "standard", "expert": {"coding": "claude-opus-4-8", ...}}

Если режим/оверрайды пусты — слой прозрачен: возвращается базовая модель офиса
(models.get_default), и старый поток не меняется.
"""

from src.saas import context as ctx

_FILE = "capabilities.json"

# Типы возможностей, по которым роутятся задачи.
CAPABILITIES = ["text", "reasoning", "coding", "image", "video", "search", "voice"]

# Режимы качества — то, что видит пользователь.
QUALITY_MODES: dict[str, dict] = {
    "economy":  {"icon": "🟣", "label": "Экономия",  "desc": "Самые дешёвые модели — для черновиков и рутины"},
    "standard": {"icon": "🟢", "label": "Стандарт",  "desc": "Баланс цены и качества для большинства задач"},
    "quality":  {"icon": "🟡", "label": "Качественно", "desc": "Умные модели — заметно лучше результат"},
    "max":      {"icon": "🔵", "label": "Максимум",  "desc": "Топовые модели на всё, без экономии"},
    "expert":   {"icon": "⚫", "label": "Эксперт",   "desc": "Ручной выбор модели под каждый тип задачи"},
}
_DEFAULT_MODE = "standard"

# Матрица режим × capability → model_id (из models.PRESETS).
# text/reasoning/search/voice идут на «базовую» модель режима; coding/image/video
# при наличии переопределяются специализированной моделью.
_MATRIX: dict[str, dict[str, str]] = {
    "economy": {
        "base": "glm-4.5-flash",
        # код в режиме «Экономия» идёт на базовую модель: спец-кодеры у провайдера
        # все премиальные ($1+/1M), что ломает обещание «самые дешёвые».
    },
    "standard": {
        # ПУСТО НАРОЧНО: это режим по умолчанию для КАЖДОГО нового тенанта, который
        # ещё не открывал «Компания → Интеллект». Если положить сюда конкретный "base",
        # он молча подменяет собой models.get_default() (реально настроенную модель
        # оператора) для всех, кто ничего не выбирал — ровно так уронился прод: у
        # тенанта .env-модель работала, а жёстко зашитая тут "gpt-5-nano" — нет, и
        # ошибка выглядела как «нет баланса», хотя баланс был. "Стандарт" должен
        # означать «как настроено», а не «всегда конкретная модель».
    },
    "quality": {
        "base": "gpt-5.4",
        "coding": "claude-sonnet-4-6",
    },
    "max": {
        "base": "claude-opus-4-8",
        "coding": "claude-opus-4-8",
    },
}

def _load() -> dict:
    return ctx.read_json(_FILE, None) or {}


def _save(d: dict) -> None:
    ctx.write_json(_FILE, d)


def get_mode() -> str:
    return _load().get("mode", _DEFAULT_MODE)


def set_mode(mode: str) -> None:
    if mode in QUALITY_MODES:
        d = _load()
        d["mode"] = mode
        _save(d)


def expert_overrides() -> dict:
    return _load().get("expert", {}) or {}


def set_expert(capability: str, model: str) -> None:
    """Назначить/сбросить модель для capability в эксперт-режиме. '' = сброс."""
    if capability not in CAPABILITIES:
        return
    d = _load()
    exp = d.setdefault("expert", {})
    if (model or "").strip():
        exp[capability] = model.strip()
    else:
        exp.pop(capability, None)
    _save(d)


def role_capability(role: str) -> str:
    """Тип задачи роли — единственный источник данных: roles.capability_of
    (было независимым hardcoded-словарём здесь, дублировавшим roles.py)."""
    from src.office import roles as roles_module
    return roles_module.capability_of(role)


def model_for(capability: str) -> str:
    """
    Модель для типа задачи в текущем режиме. Пустая строка = режим прозрачен,
    вызывающий код берёт базовую модель офиса (models.get_default).
    """
    mode = get_mode()
    if mode == "expert":
        return expert_overrides().get(capability, "")
    matrix = _MATRIX.get(mode)
    if not matrix:
        return ""
    return matrix.get(capability) or matrix.get("base", "")


def model_for_role(role: str) -> str:
    return model_for(role_capability(role))


def payload() -> dict:
    """Для UI «Компания → Интеллект»."""
    mode = get_mode()
    # Эффективная раскладка по capability в текущем режиме — для наглядности.
    resolved = {cap: model_for(cap) for cap in CAPABILITIES}
    return {
        "mode": mode,
        "modes": [{"id": k, **v} for k, v in QUALITY_MODES.items()],
        "capabilities": CAPABILITIES,
        "expert": expert_overrides(),
        "resolved": resolved,
    }
