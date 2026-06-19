"""
HR Agent — решает, кого нанять в офис следующим.
"""

import json
from typing import Optional, Callable, Awaitable

from src.core import llm
from src.office import registry

# Все роли, которые HR может нанять
HIREABLE_ROLES = {"salesman", "developer", "marketer", "analyst"}

SYSTEM_PROMPT = """Ты — HR-директор AI-стартапа. На основе стратегии и списка свободных ролей
реши: кого нанять следующим и какую задачу ему поставить.

Ответь ТОЛЬКО валидным JSON без markdown:
{"hire": true, "role": "одна_из_свободных_ролей", "task": "Конкретная задача на основе стратегии"}
или
{"hire": false, "reason": "причина"}"""


async def decide(
    strategy_summary: str,
    publish: Optional[Callable[[dict], Awaitable[None]]] = None,
) -> dict:
    existing_roles = {a.role for a in registry.all_agents()}
    available = HIREABLE_ROLES - existing_roles

    # Быстрая проверка — не тратим токены если нанимать некого
    if not available:
        if publish:
            await publish({"type": "speech", "agent_id": "hr_1",
                           "text": "Все ключевые роли укомплектованы, команда работает"})
        return {"hire": False, "reason": "Все роли уже заняты"}

    existing_str = ", ".join(sorted(existing_roles)) or "никого"
    available_str = ", ".join(sorted(available))

    user_msg = (
        f"Стратегический план:\n{strategy_summary[:1500]}\n\n"
        f"Уже в команде (НЕ нанимать повторно): {existing_str}\n"
        f"Доступные роли для найма: {available_str}\n"
        f"Свободных мест: {registry.MAX_DESKS - registry.count()}\n\n"
        f"Выбери одну роль из [{available_str}] и поставь задачу из стратегии."
    )

    if publish:
        await publish({"type": "thinking", "agent_id": "hr_1",
                       "text": "Анализирую команду, решаю кого нанять..."})

    raw = await llm.run_agent(
        system=SYSTEM_PROMPT,
        user=user_msg,
        max_tokens=300,
        use_search=False,
        agent_id="hr_1",
    )

    decision = _parse_json(raw)

    # Жёсткая защита — если LLM всё равно предложил занятую роль, блокируем
    if decision.get("hire") and decision.get("role") not in available:
        return {"hire": False, "reason": f"Роль {decision.get('role')} уже занята"}

    if publish:
        if decision.get("hire"):
            await publish({"type": "speech", "agent_id": "hr_1",
                           "text": f"Нанимаю {decision['role']}! {decision.get('task', '')[:60]}"})
        else:
            await publish({"type": "speech", "agent_id": "hr_1",
                           "text": f"Команда укомплектована. {decision.get('reason', '')}"})

    return decision


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1] if "```" in raw[3:] else raw[3:]
        if raw.startswith("json"):
            raw = raw[4:]
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start:end + 1]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"hire": False, "reason": "parse error"}
