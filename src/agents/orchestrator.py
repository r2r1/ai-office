"""
Orchestrator (Директор) — вершина иерархии офиса.

Он НЕ делает работу руками. Его задача — управлять:
  • разбивает путь к цели на этапы (вехи) на основе стратегии;
  • на каждом цикле решает, ЧТО делать дальше и КОМУ поручить;
  • отслеживает прогресс по этапам и пишет сводки;
  • решает, кого нанять, когда не хватает рук.

Иерархия:
    Директор (orchestrator)
      ├── Ресёрчер   — добывает данные
      ├── Стратег    — планирует
      ├── HR         — нанимает
      └── Рабочие    — продажник / разработчик / маркетолог / аналитик

Работает через ядро llm.py, отвечает строгим JSON.
"""

import json
from typing import Optional, Callable, Awaitable

from src.core import llm
from src.office import registry, models as models_module

HIREABLE_ROLES = {"salesman", "developer", "marketer", "analyst"}

_MILESTONES_SYSTEM = """Ты — директор автономного AI-офиса. На основе бизнес-стратегии
раздели путь к цели клиента на 4-6 последовательных этапов (вех). Каждый этап — это
осмысленный рубеж развития бизнеса (например: «Запуск продукта», «Первые клиенты»,
«Стабильные продажи», «Масштабирование»).

Ответь ТОЛЬКО валидным JSON без markdown:
{"stages": [{"id": "launch", "title": "Запуск продукта"}, {"id": "first_clients", "title": "Первые клиенты"}]}

id — короткий латиницей, title — по-русски. 4-6 этапов."""

_DECIDE_SYSTEM = """Ты — директор автономного AI-офиса. Ты управляешь командой агентов и
ведёшь бизнес к цели клиента. Каждый ход ты принимаешь ОДНО решение: поручить конкретную
задачу одному агенту, нанять нового специалиста или подождать.

Принципы:
- Двигай бизнес к текущему этапу. Ставь конкретные, выполнимые задачи с измеримым результатом.
- Не повторяй задачи, которые агент уже сделал.
- Если для этапа не хватает роли — найми (только из доступных).
- Ресёрчеру поручай добычу свежих данных, когда команде не хватает информации.
- Если текущий этап достигнут — пометь его выполненным и опиши, что сделано.

Ответь ТОЛЬКО валидным JSON без markdown:
{
  "thought": "краткая мысль директора (1 предложение, по-русски)",
  "action": "assign" | "hire" | "wait",
  "agent_id": "id агента для action=assign (например salesman_1)",
  "role": "роль для action=hire (одна из доступных)",
  "task": "конкретная задача для агента (для assign или hire)",
  "current_milestone": "id текущего этапа",
  "milestone_done": "id этапа, если он ТОЛЬКО ЧТО завершён, иначе null",
  "milestone_summary": "что достигнуто на завершённом этапе, иначе null"
}"""


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1] if "```" in raw[3:] else raw[3:]
        if raw.startswith("json"):
            raw = raw[4:]
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start:end + 1]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


async def plan_milestones(
    strategy: str,
    goal: str,
    publish: Optional[Callable[[dict], Awaitable[None]]] = None,
) -> list[dict]:
    """Разбивает путь к цели на этапы на основе стратегии."""
    if publish:
        await publish({"type": "thinking", "agent_id": "orchestrator_1",
                       "text": "Разбиваю путь к цели на этапы..."})

    user = f"Цель клиента: {goal}\n\nСтратегия:\n{strategy[:2500]}\n\nРаздели путь на этапы."
    raw = await llm.run_agent(
        system=_MILESTONES_SYSTEM,
        user=user,
        model=models_module.for_agent("orchestrator_1"),
        max_tokens=500,
        use_search=False,
        agent_id="orchestrator_1",
    )
    data = _parse_json(raw)
    stages = data.get("stages", [])
    # подстраховка — дефолтные этапы, если LLM не справился
    if not stages or not isinstance(stages, list):
        stages = [
            {"id": "setup", "title": "Подготовка продукта"},
            {"id": "first_clients", "title": "Первые клиенты"},
            {"id": "sales", "title": "Стабильные продажи"},
            {"id": "scale", "title": "Масштабирование"},
        ]
    return stages[:6]


async def decide(
    goal: str,
    strategy: str,
    milestones: list[dict],
    publish: Optional[Callable[[dict], Awaitable[None]]] = None,
) -> dict:
    """
    Главное решение директора: кому что поручить дальше.
    Возвращает dict с action: assign | hire | wait.
    """
    agents = registry.all_agents()
    existing_roles = {a.role for a in agents}
    available = HIREABLE_ROLES - existing_roles

    # Сводка по команде с последними результатами
    from src.office import state
    roster_lines = []
    for a in agents:
        last = state.result_for(a.agent_id)
        last_short = (last[:120] + "…") if last and len(last) > 120 else (last or "ещё не сдавал")
        roster_lines.append(f"- {a.agent_id} ({a.role}, {a.status}): {last_short}")
    roster = "\n".join(roster_lines) or "команда пустая"

    ms_lines = [f"- [{m['status']}] {m['id']}: {m['title']}" for m in milestones]
    ms_text = "\n".join(ms_lines) or "этапы ещё не заданы"

    if publish:
        await publish({"type": "thinking", "agent_id": "orchestrator_1",
                       "text": "Анализирую команду и решаю, что делать дальше..."})

    user = (
        f"Цель: {goal}\n\n"
        f"Стратегия (кратко):\n{strategy[:1200]}\n\n"
        f"Этапы пути:\n{ms_text}\n\n"
        f"Команда сейчас:\n{roster}\n\n"
        f"Свободные роли для найма: {', '.join(sorted(available)) or 'нет'}\n"
        f"Свободных столов: {registry.MAX_DESKS - registry.count()}\n\n"
        f"Прими ОДНО решение: assign (поручить задачу агенту из команды), "
        f"hire (нанять из доступных ролей) или wait."
    )

    raw = await llm.run_agent(
        system=_DECIDE_SYSTEM,
        user=user,
        model=models_module.for_agent("orchestrator_1"),
        max_tokens=600,
        use_search=False,
        agent_id="orchestrator_1",
    )
    decision = _parse_json(raw)
    if not decision:
        return {"action": "wait", "thought": "Не удалось принять решение, жду следующий цикл"}

    # --- Валидация решения ---
    action = decision.get("action", "wait")

    if action == "hire":
        role = decision.get("role", "")
        if role not in available:
            decision["action"] = "wait"
            decision["thought"] = f"Роль {role} недоступна для найма — жду"
    elif action == "assign":
        aid = decision.get("agent_id", "")
        if registry.get(aid) is None:
            # пробуем сопоставить по роли
            role = decision.get("role", "")
            match = next((a for a in agents if a.role == role), None)
            if match:
                decision["agent_id"] = match.agent_id
            else:
                decision["action"] = "wait"
                decision["thought"] = "Указан несуществующий агент — жду"

    return decision
