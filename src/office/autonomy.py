"""
Уровни автономности офиса — механизм доверия.

Офис ЗАРАБАТЫВАЕТ доверие постепенно, а не требует его с первого дня.
4 уровня: scout → guided → trusted → autonomous.
Каждый action-type имеет минимальный уровень для авто-выполнения.
При уровне ниже требуемого — офис принудительно спрашивает OK у пользователя.
"""

from src.saas import context as ctx

LEVELS = ["scout", "guided", "trusted", "autonomous"]

LEVEL_INFO = {
    "scout": {
        "icon": "🔍",
        "name": "Разведка",
        "desc": "Только рекомендации — ничего не делает без явного разрешения",
    },
    "guided": {
        "icon": "🤝",
        "name": "Под руководством",
        "desc": "Работает самостоятельно, но спрашивает перед важными действиями",
    },
    "trusted": {
        "icon": "✅",
        "name": "Доверенный",
        "desc": "Действует самостоятельно в рамках Конституции компании",
    },
    "autonomous": {
        "icon": "🚀",
        "name": "Автономный",
        "desc": "Полная свобода в рамках бюджетного лимита",
    },
}

# Минимальный уровень для авто-выполнения без вопроса пользователю
_ACTION_MIN_LEVEL: dict[str, str] = {
    "publish_site":    "trusted",
    "launch_bot":      "trusted",
    "create_repo":     "trusted",
    "hire":            "trusted",
    "send_message":    "guided",
    "open_department": "guided",
    "use_integration": "guided",
    "write_file":      "guided",
    "run_command":     "guided",
}

_DEFAULT_LEVEL = "guided"


def _idx(level: str) -> int:
    try:
        return LEVELS.index(level)
    except ValueError:
        return LEVELS.index(_DEFAULT_LEVEL)


def get_level() -> str:
    d = ctx.read_json("autonomy", None) or {}
    level = d.get("level", _DEFAULT_LEVEL)
    return level if level in LEVELS else _DEFAULT_LEVEL


def set_level(level: str) -> None:
    if level not in LEVELS:
        raise ValueError(f"Неизвестный уровень: {level}. Допустимые: {LEVELS}")
    d = ctx.read_json("autonomy", None) or {}
    d["level"] = level
    ctx.write_json("autonomy", d)


def can_auto(action_type: str) -> bool:
    """
    Может ли офис выполнить это действие без явного OK пользователя?
    Возвращает False → нужно принудительно вызвать ask_user.
    """
    current = get_level()
    required = _ACTION_MIN_LEVEL.get(action_type, "guided")
    return _idx(current) >= _idx(required)


def payload() -> dict:
    level = get_level()
    info = LEVEL_INFO[level]
    return {
        "level": level,
        "icon": info["icon"],
        "name": info["name"],
        "desc": info["desc"],
        "levels": [
            {**LEVEL_INFO[l], "key": l, "active": l == level}
            for l in LEVELS
        ],
    }

