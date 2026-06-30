"""
Конституция компании — правила, которые CEO не вправе нарушать.

Задаёт ограничения и полномочия: что офис может делать автономно,
а что требует явного одобрения владельца. Встраивается в промпт CEO
и используется loop.py / agent_factory.py для принудительного ask_user
перед «опасными» действиями независимо от воли LLM.
"""

from src.saas import context as ctx

# Тип действия → True если требует явного OK от пользователя по умолчанию
_DEFAULT_RULES: dict[str, bool] = {
    "publish_site":    True,   # публикация лендинга
    "launch_bot":      True,   # запуск Telegram-бота
    "send_message":    False,  # отправка сообщения (интеграция)
    "create_repo":     True,   # создание GitHub-репозитория
    "open_department": False,  # открытие отдела
    "hire":            False,  # найм нового сотрудника
    "use_integration": False,  # вызов внешней интеграции
    "write_file":      False,  # запись файла в workspace
    "run_command":     False,  # выполнение команды
}

_DEFAULT: dict = {
    "budget_auto_limit": 0,      # $ до которого CEO действует сам (0 = нет лимита)
    "rules_override": {},         # {action_type: bool} — переопределяет defaults
    "custom_rules": [],           # список текстовых правил компании
}


def load() -> dict:
    data = ctx.read_json("constitution") or {}
    return {**_DEFAULT, **data}


def save(data: dict) -> None:
    current = load()
    for k in _DEFAULT:
        if k in data:
            current[k] = data[k]
    ctx.write_json("constitution", current)


def requires_ok(action_type: str) -> bool:
    """Нужно ли явное разрешение пользователя для этого типа действия."""
    d = load()
    override = d.get("rules_override") or {}
    if action_type in override:
        return bool(override[action_type])
    return _DEFAULT_RULES.get(action_type, False)


def set_action_rule(action_type: str, requires: bool) -> None:
    d = load()
    d.setdefault("rules_override", {})[action_type] = requires
    ctx.write_json("constitution", d)


def add_custom_rule(rule: str) -> None:
    d = load()
    rules = d.get("custom_rules") or []
    if rule not in rules:
        rules.append(rule)
    d["custom_rules"] = rules[-20:]  # макс 20 правил
    ctx.write_json("constitution", d)


def rule_block() -> str:
    """Блок ограничений для промпта CEO."""
    d = load()
    custom = d.get("custom_rules") or []
    if not custom:
        return ""
    lines = ["=== КОНСТИТУЦИЯ КОМПАНИИ (обязательные правила) ==="]
    for r in custom:
        lines.append(f"• {r}")
    lines.append("Нарушение этих правил недопустимо.")
    return "\n".join(lines)


def payload() -> dict:
    d = load()
    rules = {**_DEFAULT_RULES, **(d.get("rules_override") or {})}
    return {
        "budget_auto_limit": d.get("budget_auto_limit", 0),
        "action_rules": rules,
        "custom_rules": d.get("custom_rules") or [],
    }
