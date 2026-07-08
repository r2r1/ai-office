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

import re
from typing import Awaitable, Callable, Optional

# Детерминированный разбор явного маркера в конце текста исследования — тот же
# приём, что "ЗАЯВКА_ПРИНЯТА:" в bot_engine.py: не доверяем LLM целиком, парсим
# ОДНУ структурированную строку, которую попросили написать. Без явного маркера
# (LLM не подчинился формату, или анализ не удался) — "unclear", не "go" по
# умолчанию: неясный ответ не должен молча читаться как разрешение.
_VERDICT_RE = re.compile(r"ВЕРДИКТ:\s*(go|no-go|unclear)", re.IGNORECASE)


def _parse_verdict(research: str) -> str:
    m = _VERDICT_RE.search(research or "")
    if not m:
        return "unclear"
    return m.group(1).lower()


async def run(iid: str, title: str, rationale: str,
               publish: Optional[Callable[[dict], Awaitable[None]]] = None) -> None:
    from src.office import initiatives, brief, bootstrap
    from src.agents import researcher, orchestrator

    question = (
        f"Инициатива: «{title}». Обоснование: {rationale[:500]}\n\n"
        "Проведи анализ ПЕРЕД тем, как предприниматель примет решение: "
        "выполнимо ли это в разумные сроки, какие риски и подводные камни, "
        "что реально нужно сделать по шагам, стоит ли овчинка выделки. "
        "Дай короткий, конкретный вывод — не общие слова.\n\n"
        "Последней строкой ОБЯЗАТЕЛЬНО напиши ровно одно из: "
        "\"ВЕРДИКТ: go\" (стоит делать), \"ВЕРДИКТ: no-go\" (не стоит делать), "
        "\"ВЕРДИКТ: unclear\" (нужно больше данных, чтобы решить)."
    )
    try:
        research = await researcher.run_async(question, depth="quick", publish=publish, agent_id="researcher_1")
    except Exception as e:
        research = f"Не удалось провести автоматический анализ ({str(e)[:150]}) — решай по имеющемуся обоснованию."
    recommendation = _parse_verdict(research)

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

    initiatives.set_research(iid, research, tasks=tasks, recommendation=recommendation)
    if publish:
        await publish({"type": "initiative", "id": iid, "title": title, "status": "pending",
                       "recommendation": recommendation})
        verdict_line = {"go": "рекомендую делать", "no-go": "⚠️ рекомендую НЕ делать",
                        "unclear": "нужно больше данных"}[recommendation]
        await publish({"type": "speech", "agent_id": "researcher_1",
                       "text": f"📊 Анализ инициативы «{title}» готов ({verdict_line}) — можно решать"})
