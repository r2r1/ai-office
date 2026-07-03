"""
Researcher Agent — универсальный исследователь AI-офиса.

Два режима:
  quick — 2-3 поиска, мало токенов, для текущих задач агентов
  deep  — полное исследование, развёрнутый отчёт, для стратегических решений

Другие агенты вызывают: await researcher.quick("вопрос")
Работает через единое ядро llm.py (OpenAI-совместимый провайдер + DuckDuckGo).
"""

from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Awaitable

from src.core import llm

DEFAULT_QUESTION = (
    "Проанализируй актуальные тренды 2026 года: какой способ заработать "
    "1 миллион рублей с помощью AI-агентов наиболее реалистичен прямо сейчас? "
    "Изучи кейсы, ниши, монетизацию, конкуренцию."
)

# Тексты промптов ресёрчера — policies/researcher_{quick,deep}.md (собираются
# prompt_builder.company_system, логируются в prompts.jsonl).

_MAX_TOKENS = {"quick": 1000, "deep": 4000}
_MAX_ITERS = {"quick": 3, "deep": 7}
_MAX_SEARCHES = {"quick": 2, "deep": 5}


async def run_async(
    question: str = DEFAULT_QUESTION,
    depth: str = "quick",
    publish: Optional[Callable[[dict], Awaitable[None]]] = None,
    agent_id: str = "researcher_1",
    save_report: bool = False,
) -> str:
    from src.office import prompt_builder
    policy_name = "researcher_quick" if depth == "quick" else "researcher_deep"
    system, _pid = prompt_builder.company_system(policy_name, agent_id, "researcher", question)

    if publish:
        await publish({"type": "thinking", "agent_id": agent_id,
                       "text": f"[{depth}] Исследую: {question[:80]}..."})

    from src.office import models as models_module
    result = await llm.run_agent(
        system=system,
        user=question,
        model=models_module.for_agent(agent_id),
        max_tokens=_MAX_TOKENS[depth],
        max_iterations=_MAX_ITERS[depth],
        max_searches=_MAX_SEARCHES[depth],
        use_search=True,
        publish=publish,
        agent_id=agent_id,
    )

    if save_report:
        _save_report(result, depth)
        from src.office import state, workspace as ws_module
        state.save_deliverable(agent_id, "researcher", question[:80], result)
        # Сохраняем в workspace чтобы было видно в «Код» и доступно другим агентам
        ws_module.write_file("docs/research.md", result)

    if publish:
        await publish({"type": "task_done", "agent_id": agent_id, "summary": result[:300]})

    return result


def run(question: str = DEFAULT_QUESTION, depth: str = "deep", reports_dir: str = "reports") -> str:
    """Синхронный запуск для CLI."""
    import asyncio
    return asyncio.run(run_async(question, depth=depth, save_report=True))


async def quick(question: str, publish=None, agent_id="researcher_1") -> str:
    return await run_async(question, depth="quick", publish=publish, agent_id=agent_id)


async def deep(question: str, publish=None, agent_id="researcher_1") -> str:
    return await run_async(question, depth="deep", publish=publish, agent_id=agent_id, save_report=True)


def _save_report(content: str, depth: str) -> Path:
    from src.saas import context as ctx
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    p = ctx.tenant_dir() / f"research_{depth}_{ts}.md"
    p.write_text(content, encoding="utf-8")
    return p
