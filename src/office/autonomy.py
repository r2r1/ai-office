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

# Минимальный уровень для авто-выполнения без вопроса пользователю.
# ⚠️ Здесь только ВНЕШНЕ-ВИДИМЫЕ действия, которые реально гейтятся:
#   publish_site — в loop/website; launch_bot/create_repo/send_message/use_integration —
#   в agent_factory._execute_integration. Внутренние действия в песочнице (write_file,
#   run_command, hire, open_department) НЕ гейтятся намеренно — они безопасны и без них
#   офис не может работать; держать их здесь = врать пользователю про «scout».
_ACTION_MIN_LEVEL: dict[str, str] = {
    # publish_site — самое ответственное (публичный сайт), с отдельным диалогом-одобрением.
    "publish_site":    "trusted",
    # push_code — тот же уровень строгости, что publish_site: CLAUDE.md §4 обещает
    # клиенту явно «пушит в GitHub только после одобрения» — раньше это было заявлено
    # текстом, но действие технически проходило под тем же action_type, что «создать
    # пустой репозиторий» (create_repo, "guided" = дефолтный уровень), и потому
    # пушило код БЕЗ вопроса владельцу на дефолтных настройках (аудит
    # docs/invariant-enforcement-audit-2026-07-17.md). Отдельный тип с более
    # строгим порогом закрывает разрыв между обещанием и поведением.
    "push_code":       "trusted",
    # Прочие внешние действия разрешены с «guided» (дефолт) и выше; блокируются только
    # на «scout» («только рекомендации»), где офис не действует во внешнем мире без клиента.
    "launch_bot":      "guided",
    "create_repo":     "guided",
    "send_message":    "guided",
    "use_integration": "guided",
}


def _action_type_for(action_name: str) -> str:
    """Имя действия интеграции → тип для гейта автономии."""
    a = (action_name or "").lower()
    if "publish" in a:
        return "publish_site"
    if "launch_bot" in a or a in ("start_bot",):
        return "launch_bot"
    if a == "push":
        return "push_code"
    if "repo" in a:
        return "create_repo"
    if "send" in a or "message" in a or "email" in a:
        return "send_message"
    return "use_integration"


def needs_approval(action_type: str) -> bool:
    """
    Единая точка governance: требует ли действие явного OK клиента прямо сейчас.
    Базовое решение — заработанный уровень автономии (+ «одобрено один раз»). Поверх —
    ЖЁСТКИЙ оверрайд Конституции: если компания явно задала правило для действия, оно
    имеет приоритет (True → всегда спрашивать, False → всегда разрешать).

    Между ними — обучаемый риск (см. risk.py, портрет §5a/§16): если реальные исходы
    подняли риск этого типа действия выше стартовой гипотезы, требуем подтверждение
    ДАЖЕ на высоком уровне доверия и даже если разово уже одобряли — статическая
    таблица `_ACTION_MIN_LEVEL` ниже НЕ трогается, это аддитивный слой поверх неё,
    не замена (сначала должна доказать себя, прежде чем на неё полагаться полностью).
    """
    try:
        from src.office import constitution
        ov = constitution.override_for(action_type)
        if ov is not None:
            return ov
    except Exception:
        pass
    try:
        from src.office import risk
        if risk.escalated(action_type):
            return True
    except Exception:
        pass
    return not can_auto(action_type) and not was_approved_once(action_type)

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


def mark_action_approved(action_type: str) -> None:
    """
    Пользователь один раз явно одобрил действие этого типа в рамках текущего офиса —
    больше не переспрашиваем на итеративных повторах (например повторная публикация
    того же сайта после серии мелких правок критика). Видели в проде: guided-режим
    спрашивал «опубликовать?» 5+ раз за один прогон для одного и того же сайта —
    для пользователя это шум, не новое решение. Сбрасывается вместе с офисом/паузой.
    """
    d = ctx.read_json("autonomy", None) or {}
    approved = d.setdefault("approved_once", [])
    if action_type not in approved:
        approved.append(action_type)
    ctx.write_json("autonomy", d)


def was_approved_once(action_type: str) -> bool:
    d = ctx.read_json("autonomy", None) or {}
    return action_type in (d.get("approved_once") or [])


def reset_approvals() -> None:
    """
    Сбрасывает разовые одобрения. Разрешение «опубликовать» действовало в рамках
    ТЕКУЩЕГО прогона/цели, а не навсегда — но сброса не было, и однажды одобрив
    публикацию, клиент включал авто-публикацию на весь срок жизни тенанта. Зовётся
    при паузе/возобновлении и смене цели.
    """
    d = ctx.read_json("autonomy", None) or {}
    if d.get("approved_once"):
        d["approved_once"] = []
        ctx.write_json("autonomy", d)


def next_level() -> str:
    """Следующий уровень автономии вверх, или '' если уже максимум."""
    i = _idx(get_level())
    return LEVELS[i + 1] if i + 1 < len(LEVELS) else ""


def upgrade() -> str:
    """Поднять автономию на один уровень. Возвращает новый уровень (или текущий, если макс)."""
    nl = next_level()
    if nl:
        set_level(nl)
        return nl
    return get_level()


def prev_level() -> str:
    """Следующий уровень автономии вниз, или '' если уже минимум (scout)."""
    i = _idx(get_level())
    return LEVELS[i - 1] if i > 0 else ""


def downgrade(reason: str = "") -> str:
    """Откатить автономию на один уровень — симметрично upgrade(), портрет §13:
    серьёзная видимая ошибка (не просто внутренний trust.py-декремент) откатывает
    заработанный уровень доверия автоматически, не дожидаясь, пока владелец
    заметит и понизит сам. `reason` — для лога/уведомления, не хранится здесь."""
    pl = prev_level()
    if pl:
        set_level(pl)
        return pl
    return get_level()


def payload() -> dict:
    level = get_level()
    info = LEVEL_INFO[level]
    nl = next_level()
    return {
        "level": level,
        "icon": info["icon"],
        "name": info["name"],
        "desc": info["desc"],
        # Для actionable-предложения «повысить доверие» одним нажатием (B3).
        "next_level": nl,
        "can_upgrade": bool(nl),
        "levels": [
            {**LEVEL_INFO[l], "key": l, "active": l == level}
            for l in LEVELS
        ],
    }

