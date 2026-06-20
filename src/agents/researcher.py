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

_SYSTEM_QUICK = """Ты — исследователь AI-офиса. Отвечай строго на основе данных из поиска.
Сделай 1-2 целенаправленных запроса через web_search и сразу дай краткий конкретный ответ.
Максимум 300 слов. Только факты и цифры — без воды. Не повторяй похожие запросы."""

_SYSTEM_DEEP = """Ты — ведущий исследователь AI-офиса. Принимай решения строго на основе данных.

Процесс:
1. Сделай 3-5 целенаправленных запросов через web_search (не больше — не дублируй запросы).
2. Охвати: тренды, кейсы, цифры, российский и мировой рынки.
3. Синтезируй в структурированный отчёт.

Формат отчёта:
- Executive Summary (2-3 предложения)
- Топ-3 варианта с оценкой потенциала
- Рекомендованная стратегия (сроки оценивай для AI-офиса 24/7: часы/дни, а не месяцы)
- Источники

Пиши по-русски. Конкретные цифры, сроки, примеры."""

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
    system = _SYSTEM_QUICK if depth == "quick" else _SYSTEM_DEEP

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
        from src.office import state
        state.save_deliverable(agent_id, "researcher", question[:80], result)

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
