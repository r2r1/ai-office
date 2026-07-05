"""
Глубокое исследование инициативы — BOS §5: инициатива не показывается
пользователю на решение (accept/reject) сразу после появления идеи, сначала
офис сам её анализирует (рынок/риски/выполнимость), как договорились —
«детальный анализ» до решения, не заголовок на глазок.

Общий путь для обоих источников инициативы:
- CEO-инициатива из opportunity-события (planning_engine.py, синхронно в цикле);
- предложенная самим предпринимателем (server.py propose_initiative, в фоне,
  чтобы не блокировать HTTP-ответ).
"""

from typing import Awaitable, Callable, Optional


async def run(iid: str, title: str, rationale: str,
               publish: Optional[Callable[[dict], Awaitable[None]]] = None) -> None:
    from src.office import initiatives, brief, bootstrap
    from src.agents import researcher, orchestrator

    question = (
        f"Инициатива: «{title}». Обоснование: {rationale[:500]}\n\n"
        "Проведи анализ ПЕРЕД тем, как предприниматель примет решение: "
        "выполнимо ли это в разумные сроки, какие риски и подводные камни, "
        "что реально нужно сделать по шагам, стоит ли овчинка выделки. "
        "Дай короткий, конкретный вывод — не общие слова."
    )
    try:
        research = await researcher.run_async(question, depth="quick", publish=publish, agent_id="researcher_1")
    except Exception as e:
        research = f"Не удалось провести автоматический анализ ({str(e)[:150]}) — решай по имеющемуся обоснованию."

    # Инициатива, предложенная САМИМ предпринимателем, приходит без готовых
    # задач (в отличие от CEO-инициативы из opportunity — там generate_initiative
    # уже вызван раньше). Без этого accept создал бы проект с нулём задач —
    # молчаливо ничего не делающий "Work". Достраиваем задачи здесь же.
    existing = initiatives.get(iid)
    tasks = (existing or {}).get("tasks") if existing else None
    if not tasks:
        try:
            goal = brief.effective_goal()
            strategy = bootstrap.strategy_text() or ""
            plan = await orchestrator.generate_initiative(goal, strategy, f"{title}: {rationale}", publish)
            tasks = plan.get("tasks") if isinstance(plan, dict) else None
        except Exception:
            tasks = None

    initiatives.set_research(iid, research, tasks=tasks)
    if publish:
        await publish({"type": "initiative", "id": iid, "title": title, "status": "pending"})
        await publish({"type": "speech", "agent_id": "researcher_1",
                       "text": f"📊 Анализ инициативы «{title}» готов — можно решать"})
