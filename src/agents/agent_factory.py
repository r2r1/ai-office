"""
Фабрика агентов — создаёт нового агента по роли и задаче.
Работает через единое ядро llm.py.

Любой агент может запросить ресёрчера через инструмент request_research.
"""

from typing import Callable, Awaitable

from src.core import llm
from src.agents import researcher as researcher_agent

ROLE_PROMPTS = {
    "salesman": (
        "Ты — агент продаж AI-агентства. Найди потенциальных клиентов, придумай "
        "оффер и напиши холодное сообщение. Конкретно: компании, каналы, текст. "
        "Используй web_search для актуальных данных."
    ),
    "developer": (
        "Ты — технический агент AI-агентства. Спроектируй автоматизацию для клиента: "
        "стек, архитектура, шаги. Используй web_search для актуальных инструментов."
    ),
    "marketer": (
        "Ты — маркетинговый агент AI-агентства. Создай контент-план и посты для "
        "Telegram/LinkedIn. Когда контент-план заканчивается или нужны свежие тренды — "
        "вызывай request_research с кратким вопросом. Опирайся на реальные тренды."
    ),
    "analyst": (
        "Ты — аналитик AI-агентства. Собери и проанализируй данные по рынку, "
        "конкурентам или клиентам. Выводы с цифрами. Используй web_search."
    ),
}

# Инструмент: запросить ресёрчера
_REQUEST_RESEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "request_research",
        "description": (
            "Запрашивает ресёрчера для поиска информации. Используй для свежих трендов, "
            "данных рынка, идей контента. depth='quick' — быстро и дёшево (по умолчанию), "
            "depth='deep' — полное исследование."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "Вопрос для исследования"},
                "depth": {"type": "string", "enum": ["quick", "deep"]},
            },
            "required": ["question"],
        },
    },
}


def create(role: str, task: str, agent_id: str, publish: Callable[[dict], Awaitable[None]]):
    """Возвращает async-функцию, запускающую агента."""
    system = ROLE_PROMPTS.get(role, f"Ты — {role} агент AI-агентства. Выполни задачу профессионально.")

    async def _handle_request_research(args: dict) -> str:
        question = args.get("question", "")
        depth = args.get("depth", "quick")
        await publish({"type": "speech", "agent_id": agent_id,
                       "text": f"📡 Запрашиваю ресёрчера [{depth}]: {question[:60]}"})
        return await researcher_agent.run_async(
            question=question, depth=depth, publish=publish, agent_id="researcher_1",
        )

    async def run() -> str:
        await publish({"type": "thinking", "agent_id": agent_id,
                       "text": f"Начинаю работу: {task[:80]}..."})

        result = await llm.run_agent(
            system=system,
            user=task,
            max_tokens=3000,
            max_iterations=8,
            use_search=True,
            publish=publish,
            agent_id=agent_id,
            extra_tools=[_REQUEST_RESEARCH_TOOL],
            tool_handlers={"request_research": _handle_request_research},
        )

        await publish({"type": "task_done", "agent_id": agent_id, "summary": result[:300]})
        return result

    return run
