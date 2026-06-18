"""
Фабрика агентов — создаёт нового агента по роли и задаче.
Все нанятые агенты используют haiku для экономии токенов.

Любой агент может вызвать ресёрчера через researcher.quick() / researcher.deep()
прямо внутри своего цикла работы.
"""

import os
from typing import Callable, Awaitable

import anthropic
from dotenv import load_dotenv
from src.agents import researcher as researcher_agent

load_dotenv()

ROLE_PROMPTS = {
    "salesman": (
        "Ты — агент продаж AI-агентства. Твоя задача: найти потенциальных клиентов, "
        "придумать убедительный оффер и написать холодное сообщение для outreach. "
        "Будь конкретным: названия компаний, каналы (Telegram, LinkedIn, email), "
        "текст сообщения. Используй поиск для актуальных данных."
    ),
    "developer": (
        "Ты — технический агент AI-агентства. Твоя задача: спроектировать или построить "
        "конкретную автоматизацию для клиента. Описывай стек, архитектуру, шаги реализации. "
        "Используй поиск для актуальных инструментов и best practices."
    ),
    "marketer": (
        "Ты — маркетинговый агент AI-агентства. Твоя задача: создать контент-план, "
        "написать посты для Telegram/LinkedIn, придумать стратегию продвижения. "
        "Когда контент-план заканчивается или нужны свежие тренды — запрашивай исследование "
        "через инструмент request_research с кратким вопросом. "
        "Опирайся на реальные тренды."
    ),
    "analyst": (
        "Ты — аналитик AI-агентства. Твоя задача: собрать и проанализировать данные "
        "по рынку, конкурентам или клиентам. Делай выводы с цифрами и источниками. "
        "Используй поиск для получения актуальной информации."
    ),
}


def create(
    role: str,
    task: str,
    agent_id: str,
    publish: Callable[[dict], Awaitable[None]],
):
    """Возвращает async-функцию, запускающую агента."""

    system = ROLE_PROMPTS.get(role, f"Ты — {role} агент AI-агентства. Выполни задачу профессионально.")

    # Инструмент request_research позволяет агенту запросить ресёрчера
    _request_research_tool = {
        "name": "request_research",
        "description": (
            "Запрашивает ресёрчера для поиска информации по заданному вопросу. "
            "Используй когда нужны свежие тренды, данные рынка, идеи для контента. "
            "depth='quick' — 2-3 поиска, быстро и дёшево (по умолчанию). "
            "depth='deep' — полное исследование, только для стратегических решений."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "Вопрос для исследования"},
                "depth":    {"type": "string", "enum": ["quick", "deep"], "default": "quick"},
            },
            "required": ["question"],
        },
    }

    tools = [
        {"type": "web_search_20260209", "name": "web_search"},
        _request_research_tool,
    ]

    async def run() -> str:
        client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

        await publish({"type": "thinking", "agent_id": agent_id,
                       "text": f"Начинаю работу: {task[:80]}..."})

        messages = [{"role": "user", "content": task}]

        while True:
            response = await client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=4000,
                system=system,
                tools=tools,
                messages=messages,
            )

            text_blocks = [b for b in response.content if b.type == "text"]
            tool_uses  = [b for b in response.content if b.type == "tool_use"]

            if text_blocks:
                snippet = text_blocks[0].text[:150].replace("\n", " ")
                await publish({"type": "speech", "agent_id": agent_id, "text": snippet})

            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                break

            tool_results = []
            for tu in tool_uses:
                # Обрабатываем кастомный инструмент request_research
                if tu.name == "request_research":
                    question = tu.input.get("question", "")
                    depth    = tu.input.get("depth", "quick")
                    await publish({"type": "speech", "agent_id": agent_id,
                                   "text": f"📡 Запрашиваю ресёрчера [{depth}]: {question[:60]}"})
                    research_result = await researcher_agent.run_async(
                        question=question,
                        depth=depth,
                        publish=publish,
                        agent_id="researcher_1",
                    )
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": research_result[:3000],
                    })
                else:
                    # web_search — результат уже в response.content
                    result_blocks = [b for b in response.content
                                     if hasattr(b, "tool_use_id") and b.tool_use_id == tu.id]
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": [b.model_dump() for b in result_blocks] if result_blocks else [],
                    })

            if tool_results:
                messages.append({"role": "user", "content": tool_results})

        final = "\n".join(b.text for b in text_blocks if b.text)
        await publish({"type": "task_done", "agent_id": agent_id, "summary": final[:300]})
        return final

    return run
