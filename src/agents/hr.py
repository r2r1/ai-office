"""
HR Agent — решает, кого нанять в офис следующим.
Работает через единое ядро llm.py. Веб-поиск не нужен — только решение.
"""

import json
from typing import Optional, Callable, Awaitable

from src.core import llm
from src.office import registry

SYSTEM_PROMPT = """Ты — HR-директор AI-стартапа. Реши, нужен ли офису новый сотрудник.

Доступные роли:
- salesman — ищет клиентов, делает cold outreach
- developer — строит автоматизации и AI-продукты
- marketer — создаёт контент, ведёт соцсети
- analyst — анализирует данные, считает метрики

Ответь ТОЛЬКО валидным JSON без markdown:
{"hire": true, "role": "salesman", "task": "Найти 5 клиентов в нише e-commerce"}
или
{"hire": false, "reason": "Все нужные роли закрыты"}"""


async def decide(
    strategy_summary: str,
    publish: Optional[Callable[[dict], Awaitable[None]]] = None,
) -> dict:
    existing = ", ".join(f"{a.role}({a.agent_id})" for a in registry.all_agents())
    user_msg = (
        f"Стратегический план:\n{strategy_summary[:2000]}\n\n"
        f"Уже нанятые: {existing or 'никого'}\n"
        f"Свободных мест: {registry.MAX_DESKS - registry.count()}"
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

    if publish:
        if decision.get("hire"):
            await publish({"type": "speech", "agent_id": "hr_1",
                           "text": f"Нанимаю {decision['role']}! {decision.get('task', '')}"})
        else:
            await publish({"type": "speech", "agent_id": "hr_1",
                           "text": f"Команда укомплектована. {decision.get('reason', '')}"})

    return decision


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    # Убираем markdown-обёртку если есть
    if raw.startswith("```"):
        raw = raw.split("```")[1] if "```" in raw[3:] else raw[3:]
        if raw.startswith("json"):
            raw = raw[4:]
    # Ищем первый { ... }
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start:end + 1]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"hire": False, "reason": "parse error"}
