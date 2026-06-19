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

from src.office import bus, registry, brief, state
from src.agents import researcher, strategist, hr
from src.agents import agent_factory

LOOP_INTERVAL = int(os.getenv("LOOP_INTERVAL_SECONDS", "10"))  
STRATEGY_FILE = Path("reports/strategy.md")

_last_research: str = ""
_last_strategy: str = ""


async def run() -> None:
    """Автономный офис: разовый bootstrap, затем циклы развития бизнеса."""

    publish = bus.publish

    _hire_initial(publish)
    await asyncio.sleep(2)

    # ---- ЖДЁМ БРИФ КЛИЕНТА ----
    if not brief.is_ready():
        await publish({"type": "system",
                       "text": "Офис ждёт бриф клиента. Заполните форму, чтобы начать."})
        await brief.ready.wait()

    b = brief.get()
    if b.get("summary"):
        await publish({"type": "system",
                       "text": f"Бриф получен: {b.get('goal', b.get('summary',''))[:80]}"})

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

    # ---- ЦИКЛЫ РАЗВИТИЯ: ниша зафиксирована, офис непрерывно работает ----
    cycle = 0
    while True:
        cycle += 1
        await publish({"type": "system", "text": f"=== Рабочий цикл #{cycle} ==="})

        # 1) HR добирает недостающие роли (если есть свободные столы и пустые роли)
        hired = False
        if registry.count() < registry.MAX_DESKS:
            decision = await hr.decide(strategy[:1500], publish)
            if decision.get("hire"):
                await _hire_and_run(decision, publish)
                hired = True

        # 2) Команда укомплектована → двигаем работу дальше:
        #    даём свободному агенту НОВЫЙ конкретный шаг к цели (round-robin)
        if not hired:
            advanced = await _advance_work(strategy, publish)
            if not advanced:
                await publish({"type": "system",
                               "text": "Агенты заняты текущими задачами — ждём результатов"})

        await publish({"type": "system",
                       "text": f"Цикл #{cycle} завершён. Следующий через {LOOP_INTERVAL}с"})
        await asyncio.sleep(LOOP_INTERVAL)


async def _bootstrap(publish) -> str:
    """Разовое определение ниши: ресёрчер (deep) + стратег."""
    await publish({"type": "system", "text": "=== BOOTSTRAP: исследуем нишу клиента ==="})

    question = brief.research_question() or researcher.DEFAULT_QUESTION
    try:
        research = await researcher.deep(question, publish=publish)
        globals()["_last_research"] = research
    except Exception as e:
        await publish({"type": "error", "agent_id": "researcher_1", "text": str(e)[:100]})
        research = _last_research

    # Стратег получает и бриф клиента, и исследование
    strat_input = research
    if brief.summary():
        strat_input = f"БРИФ КЛИЕНТА:\n{brief.summary()}\n\nИССЛЕДОВАНИЕ РЫНКА:\n{research}"
    try:
        strategy = await strategist.run_async(strat_input, publish=publish)
        globals()["_last_strategy"] = strategy
        _save_strategy(strategy)
    except Exception as e:
        await publish({"type": "error", "agent_id": "strategist_1", "text": str(e)[:100]})
        strategy = _last_strategy

    await publish({"type": "system",
                   "text": "Ниша определена ✓ Больше не переисследуем — развиваем бизнес"})
    return strategy


async def _hire_and_run(decision: dict, publish) -> None:
    if decision.get("hire") and registry.has_role(decision.get("role", "")):
        await publish({"type": "system", "text": f"Роль {decision['role']} уже есть — пропускаю найм"})
        return
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


_WORKER_SKIP = {"researcher", "strategist", "hr"}
_rr_index = 0


async def _advance_work(strategy: str, publish) -> bool:
    """Даёт одному свободному рабочему агенту НОВЫЙ конкретный шаг к цели.

    Round-robin: за цикл двигаем одного агента, чтобы офис непрерывно
    производил результаты, но не сжигал токены на всех сразу.
    Возвращает True, если кого-то запустили.
    """
    global _rr_index

    workers = [a for a in registry.all_agents()
               if a.role not in _WORKER_SKIP and a.status in ("done", "idle")]
    if not workers:
        return False

    # round-robin выбор следующего свободного агента
    workers.sort(key=lambda a: a.agent_id)
    agent = workers[_rr_index % len(workers)]
    _rr_index += 1

    goal = brief.get().get("goal", "") or brief.summary()
    prev = state.result_for(agent.agent_id)
    next_task = (
        f"Цель офиса: {goal}\n"
        f"Стратегия (кратко): {strategy[:700]}\n"
        f"Твоя роль: {agent.role}. Исходная задача: {agent.task}\n"
        f"Что ты уже сделал в прошлый раз: {prev[:500] or 'ещё не было результата'}\n\n"
        f"Сделай СЛЕДУЮЩИЙ конкретный шаг и выдай НОВЫЙ готовый результат "
        f"(не повторяй прошлое), который реально двигает офис к цели. "
        f"Если нужна свежая информация — используй web_search или request_research. "
        f"Если не хватает данных от клиента (доступы, ключи, решения) — спроси через ask_user. "
        f"Можешь делегировать коллеге через send_message."
    )

    await publish({"type": "system",
                   "text": f"{agent.role} продолжает работу — следующий шаг к цели"})
    agent_fn = agent_factory.create(agent.role, next_task, agent.agent_id, publish)
    asyncio.create_task(_run_hired_agent(agent.agent_id, agent_fn, publish))
    return True


async def _run_hired_agent(agent_id: str, agent_fn, publish) -> None:
    registry.update_status(agent_id, "thinking")
    try:
        await agent_fn()
        registry.update_status(agent_id, "done")
    except Exception as e:
        await publish({"type": "error", "agent_id": agent_id, "text": str(e)[:100]})
        registry.update_status(agent_id, "idle")
