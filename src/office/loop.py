"""
Автономный офисный цикл — мозг системы.

Логика:
  BOOTSTRAP (один раз) — ресёрчер (deep) + стратег определяют нишу и план.
                          Результат сохраняется в reports/strategy.md.
  ЦИКЛЫ (повторяются)   — ниша УЖЕ выбрана. Офис развивает бизнес:
                          HR нанимает недостающих специалистов, агенты работают,
                          ресёрчер вызывается только on-demand (quick) для трендов.

Если strategy.md уже существует — bootstrap пропускается, офис продолжает с того же места.
"""

import asyncio
import os
from pathlib import Path

from src.office import bus, registry
from src.agents import researcher, strategist, hr
from src.agents import agent_factory

LOOP_INTERVAL = int(os.getenv("LOOP_INTERVAL_SECONDS", "300"))  # 5 минут по умолчанию
STRATEGY_FILE = Path("reports/strategy.md")

_last_research: str = ""
_last_strategy: str = ""


async def run() -> None:
    """Автономный офис: разовый bootstrap, затем циклы развития бизнеса."""

    publish = bus.publish

    _hire_initial(publish)
    await asyncio.sleep(2)

    # ---- BOOTSTRAP: определяем нишу и стратегию ОДИН РАЗ ----
    strategy = _load_strategy()
    if strategy:
        globals()["_last_strategy"] = strategy
        await publish({"type": "system",
                       "text": "Стратегия уже определена — продолжаю развитие бизнеса"})
        await publish({"type": "task_done", "agent_id": "strategist_1",
                       "summary": "Ниша выбрана ранее. План загружен из strategy.md"})
    else:
        strategy = await _bootstrap(publish)

    # ---- ЦИКЛЫ РАЗВИТИЯ: ниша зафиксирована, офис работает ----
    cycle = 0
    while True:
        cycle += 1
        await publish({"type": "system", "text": f"=== Рабочий цикл #{cycle} ==="})

        # HR смотрит на команду и нанимает недостающего специалиста
        if registry.count() < registry.MAX_DESKS:
            decision = await hr.decide(strategy[:1500], publish)
            if decision.get("hire"):
                await _hire_and_run(decision, publish)
            else:
                await publish({"type": "system",
                               "text": "Команда укомплектована — агенты работают над задачами"})
        else:
            await publish({"type": "system", "text": "Все столы заняты — офис на полной мощности"})

        await publish({"type": "system",
                       "text": f"Цикл #{cycle} завершён. Следующий через {LOOP_INTERVAL}с"})
        await asyncio.sleep(LOOP_INTERVAL)


async def _bootstrap(publish) -> str:
    """Разовое определение ниши: ресёрчер (deep) + стратег."""
    await publish({"type": "system", "text": "=== BOOTSTRAP: определяем нишу (разово) ==="})

    await publish({"type": "thinking", "agent_id": "researcher_1",
                   "text": "Глубокое исследование рынка для выбора ниши..."})
    try:
        research = await asyncio.to_thread(_run_researcher, publish)
        globals()["_last_research"] = research
    except Exception as e:
        await publish({"type": "error", "agent_id": "researcher_1", "text": str(e)[:100]})
        research = _last_research

    await publish({"type": "thinking", "agent_id": "strategist_1",
                   "text": "Строю стратегию на основе исследования..."})
    try:
        strategy = await asyncio.to_thread(_run_strategist, research, publish)
        globals()["_last_strategy"] = strategy
        _save_strategy(strategy)
    except Exception as e:
        await publish({"type": "error", "agent_id": "strategist_1", "text": str(e)[:100]})
        strategy = _last_strategy

    await publish({"type": "system",
                   "text": "Ниша определена ✓ Больше не переисследуем — развиваем бизнес"})
    return strategy


async def _hire_and_run(decision: dict, publish) -> None:
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
        agent_fn = agent_factory.create(role, task, agent_id, publish)
        asyncio.create_task(_run_hired_agent(agent_id, agent_fn, publish))


def _load_strategy() -> str:
    if STRATEGY_FILE.exists():
        return STRATEGY_FILE.read_text(encoding="utf-8")
    return ""


def _save_strategy(strategy: str) -> None:
    STRATEGY_FILE.parent.mkdir(parents=True, exist_ok=True)
    STRATEGY_FILE.write_text(strategy, encoding="utf-8")


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
