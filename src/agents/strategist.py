"""
Strategist Agent — превращает отчёт ресёрчера в исполнимый план.
Работает через единое ядро llm.py.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Awaitable

from src.core import llm

# Текст промпта стратега — policies/strategist.md (собирается prompt_builder.
# company_system со слотом Brief: раньше system упоминал «цель клиента», но goal
# в user НЕ передавался — Brief-слот его теперь и приносит).


async def run_async(
    research_report: str,
    publish: Optional[Callable[[dict], Awaitable[None]]] = None,
    agent_id: str = "strategist_1",
    save: bool = True,
) -> str:
    user = (
        "Вот исследовательский отчёт. Составь исполнимый план.\n\n"
        f"=== ОТЧЁТ ===\n{research_report[:3000]}"
    )

    if publish:
        await publish({"type": "thinking", "agent_id": agent_id,
                       "text": "Анализирую отчёт, строю план..."})

    from src.office import models as models_module
    from src.office import prompt_builder
    system, _pid = prompt_builder.company_system("strategist", agent_id, "strategist", user)
    result = await llm.run_agent(
        system=system,
        user=user,
        model=models_module.for_agent(agent_id),
        max_tokens=3000,
        max_iterations=2,
        use_search=False,
        publish=publish,
        agent_id=agent_id,
    )

    if save:
        _save_plan(result)

    from src.office import state, workspace as ws_module
    state.save_deliverable(agent_id, "strategist", "Бизнес-план офиса", result)
    ws_module.write_file("docs/strategy.md", result)

    if publish:
        await publish({"type": "task_done", "agent_id": agent_id, "summary": result[:300]})

    return result


def run(research_report: str, reports_dir: str = "reports") -> str:
    """Синхронный запуск для CLI."""
    import asyncio
    return asyncio.run(run_async(research_report))


def _save_plan(content: str) -> Path:
    from src.saas import context as ctx
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    p = ctx.tenant_dir() / f"plan_{ts}.md"
    p.write_text(content, encoding="utf-8")
    return p
