"""
Чат с агентами — пользователь может кликнуть на агента и поговорить с ним.
Каждый агент помнит контекст диалога. Использует web_search при необходимости.
"""

from typing import Optional, Callable, Awaitable

from src.core import llm
from src.office import registry

# Системные промпты по ролям — задают характер и компетенции агента
ROLE_SYSTEM = {
    "researcher": (
        "Ты — агент-исследователь AI-офиса. Ты эксперт по поиску трендов, рынков, "
        "кейсов и данных. Отвечай по делу, опирайся на факты. Можешь искать в интернете "
        "через web_search. Отвечай дружелюбно, как коллега по офису."
    ),
    "strategist": (
        "Ты — агент-стратег AI-офиса. Ты строишь бизнес-планы, считаешь юнит-экономику, "
        "декомпозируешь цели на задачи. Отвечай структурно и конкретно, как коллега."
    ),
    "hr": (
        "Ты — HR-директор AI-офиса. Ты решаешь кого нанять, управляешь командой агентов. "
        "Отвечай по-деловому, но дружелюбно."
    ),
    "salesman": (
        "Ты — агент продаж AI-офиса. Ты ищешь клиентов, пишешь офферы и cold outreach. "
        "Энергичный, ориентированный на результат. Отвечай как коллега."
    ),
    "developer": (
        "Ты — технический агент AI-офиса. Ты строишь автоматизации и AI-продукты. "
        "Объясняешь технически, но понятно. Отвечай как коллега."
    ),
    "marketer": (
        "Ты — маркетинговый агент AI-офиса. Ты создаёшь контент и стратегии продвижения. "
        "Креативный, в курсе трендов. Отвечай как коллега."
    ),
    "analyst": (
        "Ты — аналитик AI-офиса. Ты работаешь с данными, метриками, цифрами. "
        "Отвечай точно и с числами. Отвечай как коллега."
    ),
}

# История диалогов: agent_id -> [{role, content}]
_histories: dict[str, list[dict[str, str]]] = {}

MAX_HISTORY = 12  # храним последние N реплик, чтобы не раздувать токены


async def ask(
    agent_id: str,
    message: str,
    publish: Optional[Callable[[dict], Awaitable[None]]] = None,
) -> str:
    """Задаёт вопрос конкретному агенту и возвращает его ответ."""
    rec = registry.get(agent_id)
    role = rec.role if rec else "researcher"
    system = ROLE_SYSTEM.get(role, f"Ты — {role} агент AI-офиса. Отвечай как дружелюбный коллега.")

    # Добавляем контекст о текущей задаче агента
    if rec and rec.task:
        system += f"\n\nТвоя текущая задача в офисе: {rec.task}"

    history = _histories.setdefault(agent_id, [])

    if publish:
        await publish({"type": "thinking", "agent_id": agent_id,
                       "text": "печатает ответ..."})

    reply = await llm.run_agent(
        system=system,
        user=message,
        history=history,
        max_tokens=1500,
        max_iterations=5,
        use_search=True,
        publish=None,  # не спамим пузырями во время диалога — покажем только финал
        agent_id=agent_id,
    )

    # Обновляем историю
    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": reply})
    if len(history) > MAX_HISTORY:
        del history[:len(history) - MAX_HISTORY]

    if publish:
        # Показываем ответ пузырём над агентом
        await publish({"type": "speech", "agent_id": agent_id, "text": reply[:120]})
        await publish({"type": "chat_reply", "agent_id": agent_id, "text": reply})

    return reply


def clear_history(agent_id: str) -> None:
    _histories.pop(agent_id, None)
