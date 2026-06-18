"""
HR Agent — решает, кого нанять в офис следующим.
Использует дешёвую модель (haiku) для JSON-решения.
"""

import json
import os
from typing import Optional, Callable, Awaitable

import anthropic
from dotenv import load_dotenv

from src.office import registry

load_dotenv()

SYSTEM_PROMPT = """Ты — HR-директор AI-стартапа. Твоя задача — решить, нужен ли офису новый сотрудник.

Тебе дадут:
1. Текущий стратегический план бизнеса
2. Список уже нанятых агентов и их роли

Доступные роли для найма:
- salesman — ищет клиентов, делает cold outreach
- developer — строит автоматизации и AI-продукты
- marketer — создаёт контент, ведёт соцсети
- analyst — анализирует данные, считает метрики

Ответь ТОЛЬКО валидным JSON (без markdown, без пояснений):
{"hire": true, "role": "salesman", "task": "Найти 5 потенциальных клиентов в нише e-commerce"}
или
{"hire": false, "reason": "Все нужные роли уже закрыты"}"""


async def decide(
    strategy_summary: str,
    publish: Optional[Callable[[dict], Awaitable[None]]] = None,
) -> dict:
    client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    existing = ", ".join(f"{a.role}({a.agent_id})" for a in registry.all_agents())
    user_msg = (
        f"Стратегический план:\n{strategy_summary[:2000]}\n\n"
        f"Уже нанятые агенты: {existing or 'никого'}\n"
        f"Свободных мест: {registry.MAX_DESKS - registry.count()}"
    )

    if publish:
        await publish({"type": "thinking", "agent_id": "hr_1", "text": "Анализирую команду, решаю кого нанять..."})

    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )

    raw = response.content[0].text.strip()

    try:
        decision = json.loads(raw)
    except json.JSONDecodeError:
        decision = {"hire": False, "reason": "parse error"}

    if publish:
        if decision.get("hire"):
            await publish({
                "type": "speech",
                "agent_id": "hr_1",
                "text": f"Нанимаю {decision['role']}! Задача: {decision.get('task', '')}",
            })
        else:
            await publish({
                "type": "speech",
                "agent_id": "hr_1",
                "text": f"Команда укомплектована. {decision.get('reason', '')}",
            })

    return decision
