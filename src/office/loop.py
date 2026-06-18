"""
Автономный офисный цикл — мозг системы.
Запускает агентов по очереди, HR решает кого нанять.
"""

import asyncio
import os
from typing import Callable, Awaitable

from src.office import bus, registry
from src.agents import researcher, strategist, hr
from src.agents import agent_factory

LOOP_INTERVAL = int(os.getenv("LOOP_INTERVAL_SECONDS", "300"))  # 5 минут по умолчанию

_last_research: str = ""
_last_strategy: str = ""


async def run() -> None:
    """Бесконечный цикл автономного офиса."""

    publish = bus.publish

    # Регистрируем стартовых сотрудников
    _hire_initial(publish)

    await asyncio.sleep(2)

    cycle = 0
    while True:
        cycle += 1
        await publish({"type": "system", "text": f"=== Цикл #{cycle} начался ==="})

        # 1. Ресёрчер собирает данные
        await publish({"type": "thinking", "agent_id": "researcher_1", "text": "Начинаю исследование рынка..."})
        try:
            research = await asyncio.to_thread(_run_researcher, publish)
            globals()["_last_research"] = research
        except Exception as e:
            await publish({"type": "error", "agent_id": "researcher_1", "text": str(e)[:100]})
            research = _last_research

        # 2. Стратег строит план
        await publish({"type": "thinking", "agent_id": "strategist_1", "text": "Анализирую отчёт, строю план..."})
        try:
            strategy = await asyncio.to_thread(_run_strategist, research, publish)
            globals()["_last_strategy"] = strategy
        except Exception as e:
            await publish({"type": "error", "agent_id": "strategist_1", "text": str(e)[:100]})
            strategy = _last_strategy

        # 3. HR решает кого нанять
        if registry.count() < registry.MAX_DESKS:
            decision = await hr.decide(strategy[:1500], publish)
            if decision.get("hire"):
                role = decision["role"]
                task = decision.get("task", f"Выполни задачи {role}")
                agent_id = f"{role}_{registry.count() + 1}"
                rec = registry.register(agent_id, role, task)
                if rec:
                    await publish({
                        "type": "hired",
                        "agent_id": agent_id,
                        "role": role,
                        "desk": rec.desk,
                        "task": task[:100],
                    })
                    # Запускаем нового агента асинхронно
                    agent_fn = agent_factory.create(role, task, agent_id, publish)
                    asyncio.create_task(_run_hired_agent(agent_id, agent_fn, publish))

        # 4. Запускаем уже нанятых агентов если нужно
        await publish({"type": "system", "text": f"Цикл #{cycle} завершён. Следующий через {LOOP_INTERVAL}с"})
        await asyncio.sleep(LOOP_INTERVAL)


def _hire_initial(publish_sync) -> None:
    """Регистрируем стартовых сотрудников в реестре."""
    if not registry.has_role("researcher"):
        rec = registry.register("researcher_1", "researcher", "Исследование рынка AI-агентств")
        if rec:
            asyncio.get_event_loop().create_task(publish_sync({
                "type": "hired", "agent_id": "researcher_1",
                "role": "researcher", "desk": rec.desk, "task": rec.task,
            }))

    if not registry.has_role("strategist"):
        rec = registry.register("strategist_1", "strategist", "Построение бизнес-стратегии")
        if rec:
            asyncio.get_event_loop().create_task(publish_sync({
                "type": "hired", "agent_id": "strategist_1",
                "role": "strategist", "desk": rec.desk, "task": rec.task,
            }))

    if not registry.has_role("hr"):
        rec = registry.register("hr_1", "hr", "Найм новых агентов")
        if rec:
            asyncio.get_event_loop().create_task(publish_sync({
                "type": "hired", "agent_id": "hr_1",
                "role": "hr", "desk": rec.desk, "task": rec.task,
            }))


def _run_researcher(publish) -> str:
    """Синхронная обёртка для запуска researcher в потоке."""
    import anthropic as _anthropic
    import os

    client = _anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    tools = [{"type": "web_search_20260209", "name": "web_search"}]
    messages = [{"role": "user", "content": researcher.DEFAULT_QUESTION}]

    import asyncio as _asyncio

    loop = _asyncio.new_event_loop()

    def _pub(event):
        asyncio.run_coroutine_threadsafe(publish(event), asyncio.get_event_loop())

    iteration = 0
    while True:
        iteration += 1
        response = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=8000,
            thinking={"type": "adaptive"},
            system=researcher.SYSTEM_PROMPT,
            tools=tools,
            messages=messages,
        )

        text_blocks = [b for b in response.content if b.type == "text"]
        tool_uses = [b for b in response.content if b.type == "tool_use"]

        if text_blocks:
            snippet = text_blocks[0].text[:150].replace("\n", " ")
            asyncio.get_event_loop().call_soon_threadsafe(
                lambda s=snippet: asyncio.ensure_future(publish({"type": "speech", "agent_id": "researcher_1", "text": s}))
            )

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            break

        tool_results = []
        for tu in tool_uses:
            result_blocks = [b for b in response.content if hasattr(b, "tool_use_id") and b.tool_use_id == tu.id]
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": [b.model_dump() for b in result_blocks] if result_blocks else [],
            })
        if tool_results:
            messages.append({"role": "user", "content": tool_results})

    return "\n".join(b.text for b in text_blocks if b.text)


def _run_strategist(research: str, publish) -> str:
    """Синхронная обёртка для запуска strategist в потоке."""
    import anthropic as _anthropic
    import os

    client = _anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    tools = [{"type": "web_search_20260209", "name": "web_search"}]
    user_msg = (
        "Вот исследовательский отчёт. Составь исполнимый план.\n\n"
        f"=== ОТЧЁТ ===\n{research[:3000]}"
    )
    messages = [{"role": "user", "content": user_msg}]

    iteration = 0
    while True:
        iteration += 1
        response = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=8000,
            thinking={"type": "adaptive"},
            system=strategist.SYSTEM_PROMPT,
            tools=tools,
            messages=messages,
        )

        text_blocks = [b for b in response.content if b.type == "text"]
        tool_uses = [b for b in response.content if b.type == "tool_use"]

        if text_blocks:
            snippet = text_blocks[0].text[:150].replace("\n", " ")
            asyncio.get_event_loop().call_soon_threadsafe(
                lambda s=snippet: asyncio.ensure_future(publish({"type": "speech", "agent_id": "strategist_1", "text": s}))
            )

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            break

        tool_results = []
        for tu in tool_uses:
            result_blocks = [b for b in response.content if hasattr(b, "tool_use_id") and b.tool_use_id == tu.id]
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": [b.model_dump() for b in result_blocks] if result_blocks else [],
            })
        if tool_results:
            messages.append({"role": "user", "content": tool_results})

    return "\n".join(b.text for b in text_blocks if b.text)


async def _run_hired_agent(agent_id: str, agent_fn, publish) -> None:
    registry.update_status(agent_id, "thinking")
    try:
        await agent_fn()
        registry.update_status(agent_id, "done")
    except Exception as e:
        await publish({"type": "error", "agent_id": agent_id, "text": str(e)[:100]})
        registry.update_status(agent_id, "idle")
