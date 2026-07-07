"""
Platform Self-Knowledge (BOS §6.1) — узкая версия: агент видит СВОЮ роль,
скилл и список СВОИХ инструментов, а не исходный код платформы (auth.py,
crypto.py и т.д.). Аналог того, как Claude Code показывает свой system prompt
и список тулов по запросу, но не открывает исходники харнесса/модели.

Изначальная реализация (см. историю коммита) давала read-only доступ ко ВСЕМУ
репозиторию ai-office кроме data/ — владелец счёл это избыточным: architect/cto
видели бы даже security-чувствительные модули (auth.py, crypto.py), которые не
нужны для их задач. Заменено на чистую функцию без файлового доступа вообще.
"""


def describe(role: str, tools: list[str], skill: str = "", department: str = "") -> str:
    lines = [f"Твоя роль: {role}."]
    if skill:
        lines.append(f"Активный скилл: {skill}.")
    if department:
        lines.append(f"Твой отдел: {department}.")
    lines.append("Доступные тебе инструменты: " + ", ".join(sorted(tools)) + ".")
    lines.append(
        "Полный текст твоей роли и командных политик — в системном промпте этой задачи "
        "(office/builtin_roles/<роль>.md, office/policies/*.md) — он уже был тебе передан "
        "в начале диалога, отдельно читать не нужно."
    )
    return "\n".join(lines)
