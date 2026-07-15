"""
Общий канал офиса — лента сообщений всех агентов и пользователя. По тенанту.
"""

import time
import uuid

from src.saas import context as ctx

_FILE = "office_channel.json"
MAX_MESSAGES = 200


def post(from_id: str, role: str, text: str) -> dict:
    msgs = ctx.read_json(_FILE, [])
    msg = {"id": uuid.uuid4().hex[:8], "from": from_id, "role": role,
           "text": text.strip(), "ts": time.time()}
    msgs.append(msg)
    if len(msgs) > MAX_MESSAGES:
        del msgs[: len(msgs) - MAX_MESSAGES]
    ctx.write_json(_FILE, msgs)
    return msg


def recent(n: int = 50) -> list[dict]:
    return ctx.read_json(_FILE, [])[-n:]


# Аудит (docs/pre-release-audit-2026-07-15.md, находка Low): между тостом "hired"
# и первым РЕАЛЬНЫМ сообщением агента в общем чате не было ничего — новый агент
# мог молчать заметное время, пока не доберётся до своей первой задачи. Роли
# без записи в roles.ROLE_META (штаб CEO — не привязаны к отделу) — короткий
# запасной словарь только для этого представления.
_ROLE_LABELS_FALLBACK = {
    "orchestrator": "CEO", "researcher": "Ресёрчер", "strategist": "Стратег",
    "architect": "Архитектор", "hr": "HR",
}


def greet_text(role: str, agent_id: str, task: str) -> str:
    from src.office import roles as roles_module
    title = roles_module.ROLE_META.get(role, {}).get("title") or _ROLE_LABELS_FALLBACK.get(role, role)
    task = (task or "").strip()
    return f"Привет, я {title} ({agent_id}). Займусь: {task}" if task else f"Привет, я {title} ({agent_id})."


def greet(agent_id: str, role: str, task: str) -> dict:
    """Детерминированное представление сразу после найма — без LLM (DEMO_MODE и
    реальный офис одинаково бесплатны на этом шаге, см. CLAUDE.md §2)."""
    return post(agent_id, role, greet_text(role, agent_id, task))


def clear() -> None:
    ctx.delete_file(_FILE)


def load() -> None:
    pass


def reset() -> None:
    clear()
