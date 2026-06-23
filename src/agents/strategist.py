"""
Strategist Agent — превращает отчёт ресёрчера в исполнимый план.
Работает через единое ядро llm.py.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Awaitable

from src.core import llm

SYSTEM_PROMPT = """Ты — главный стратег AI-офиса. На вход — исследовательский отчёт и
КОНКРЕТНАЯ ЦЕЛЬ КЛИЕНТА (что он попросил сделать).

🎯 ГЛАВНОЕ: план должен вести к ВЫПОЛНЕНИЮ ЗАПРОСА КЛИЕНТА и доведению результата до
рабочего состояния — и НЕ БОЛЬШЕ. Если клиент просит «лендинг, который приводит звонки»,
то цель = собрать рабочий конверсионный лендинг с формой/звонком и убедиться, что он
работает. НЕ превращай конкретный заказ в выдуманный бизнес: не придумывай «продажу
лендингов другим компаниям», «сбор 50 B2B-лидов», «масштабирование до 1 млн» — это НЕ
просили. Такие фантазии загоняют офис в бесконечные недостижимые задачи.

Если клиент явно хочет роста/выручки — добавь это ОТДЕЛЬНЫМ блоком «Дальнейший рост
(опционально)» В КОНЦЕ, не подменяя основную задачу.

Опирайся на переданный отчёт — повторно искать в интернете не нужно.

Сроки: автономный AI-офис работает 24/7. Оценивай в часах/днях; поясняй, что скорость
ограничивают внешние факторы (ответы клиента, модерация), а не работа агентов.

Формат плана:
1. Цель клиента (своими словами) и что значит «выполнено» (проверяемый критерий)
2. Декомпозиция на задачи — формат: [РОЛЬ] задача → результат (только то, что нужно для цели)
3. Этапы до готового результата с KPI каждого (в часах/днях)
4. Метрики успеха и как проверить, что цель достигнута
5. Риски и план Б
6. (опционально) Дальнейший рост — если клиент об этом просил

Пиши по-русски, конкретно. Не раздувай объём ради объёма."""


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
    result = await llm.run_agent(
        system=SYSTEM_PROMPT,
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

    from src.office import state
    state.save_deliverable(agent_id, "strategist", "Бизнес-план офиса", result)

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
