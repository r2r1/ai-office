"""
Strategist Agent — превращает отчёт ресёрчера в исполнимый план.
Работает через единое ядро llm.py.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Awaitable

from src.core import llm

SYSTEM_PROMPT = """Ты — главный стратег AI-офиса. На вход ты получаешь исследовательский
отчёт от агента-ресёрчера с рекомендованной бизнес-моделью для заработка 1 млн рублей.

Твоя задача — превратить рекомендацию в конкретный исполнимый план, по которому
другие агенты офиса (продажник, разработчик, контент-менеджер) смогут работать.

Используй web_search, чтобы уточнить детали: реальные цены, инструменты, площадки.

Формат итогового плана:
1. Выбранная модель и цель (1М руб.)
2. Юнит-экономика — клиентов/продаж × средний чек = 1М руб.
3. Декомпозиция на задачи — формат: [АГЕНТ] задача → результат
4. Дорожная карта 90 дней по неделям с KPI
5. Необходимые ресурсы
6. Метрики успеха и точки контроля
7. Риски и план Б

Пиши по-русски. Конкретно: цифры, сроки, чек-листы."""


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

    result = await llm.run_agent(
        system=SYSTEM_PROMPT,
        user=user,
        max_tokens=6000,
        max_iterations=10,
        use_search=True,
        publish=publish,
        agent_id=agent_id,
    )

    if save:
        _save_plan(result)

    if publish:
        await publish({"type": "task_done", "agent_id": agent_id, "summary": result[:300]})

    return result


def run(research_report: str, reports_dir: str = "reports") -> str:
    """Синхронный запуск для CLI."""
    import asyncio
    return asyncio.run(run_async(research_report))


def _save_plan(content: str) -> Path:
    path = Path("reports")
    path.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    p = path / f"plan_{ts}.md"
    p.write_text(content, encoding="utf-8")
    return p
