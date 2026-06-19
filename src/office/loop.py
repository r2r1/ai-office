"""
Автономный офисный цикл — мозг системы с иерархией агентов.

Иерархия:
    Директор (orchestrator) — ставит задачи, ведёт этапы, нанимает
      ├── Ресёрчер   — добывает данные
      ├── Стратег    — строит план
      ├── HR         — исполняет найм
      └── Рабочие    — продажник / разработчик / маркетолог / аналитик

Логика:
  BOOTSTRAP (один раз) — ресёрчер (deep) + стратег определяют нишу и план.
                          Затем директор разбивает путь к цели на этапы.
                          Результат сохраняется в reports/strategy.md.
  ЦИКЛЫ (повторяются)   — директор на каждом ходу решает, кому что поручить,
                          и ведёт прогресс по этапам.

Если strategy.md уже существует — bootstrap пропускается, офис продолжает с того же места.
"""

import asyncio
import os
import time
from pathlib import Path

from src.office import bus, registry, brief, state, milestones
from src.agents import researcher, strategist, orchestrator
from src.agents import agent_factory


LOOP_INTERVAL = int(os.getenv("LOOP_INTERVAL_SECONDS", "10"))
STRATEGY_FILE = Path("reports/strategy.md")

_last_research: str = ""
_last_strategy: str = ""

# id этапа, к которому сейчас привязываются результаты работы
_current_milestone_id: str = ""

# После перезапуска агенты не запускаются сразу — только через 1 полный цикл.
_first_cycle_done = False

# Минимальный промежуток между задачами ОДНОГО агента (антидребезг при рестарте).
# Директор теперь сам учитывает занятость агентов — короткий cooldown нужен только
# чтобы не запустить одного агента дважды за один цикл при гонке.
AGENT_COOLDOWN_SECS = 60  # 1 минута


async def _set_progress_note(note: str, publish) -> None:
    """Публикует обновление прогресс-бара на основе текущих этапов."""
    payload = milestones.progress_payload()
    payload["note"] = note
    await publish({"type": "progress", **payload})


async def run() -> None:
    """Автономный офис: bootstrap, затем циклы под управлением директора."""
    publish = bus.publish

    _hire_initial(publish)
    await asyncio.sleep(2)

    # ---- ЖДЁМ БРИФ КЛИЕНТА ----
    if not brief.is_ready():
        milestones.mark_active("intake")
        await _set_progress_note("Ждём бриф клиента", publish)
        await publish({"type": "system",
                       "text": "Офис ждёт бриф клиента. Заполните форму, чтобы начать."})
        await brief.ready.wait()

    b = brief.get()
    if b.get("summary"):
        milestones.set_status("intake", "done")
        await publish({"type": "system",
                       "text": f"Бриф получен: {b.get('goal', b.get('summary',''))[:80]}"})

    # ---- BOOTSTRAP: ниша, стратегия, этапы ----
    strategy = _load_strategy()
    if strategy:
        globals()["_last_strategy"] = strategy
        milestones.set_status("research", "done")
        milestones.set_status("strategy", "done")
        await publish({"type": "system",
                       "text": "Стратегия уже определена — продолжаю развитие бизнеса"})
        await publish({"type": "task_done", "agent_id": "strategist_1",
                       "summary": "Ниша выбрана ранее. План загружен из strategy.md"})
    else:
        strategy = await _bootstrap(publish)

    # ---- Директор формирует этапы пути (если ещё не сформированы) ----
    if not milestones.has_business_stages():
        goal = brief.get().get("goal", "") or brief.summary()
        stages = await orchestrator.plan_milestones(strategy, goal, publish)
        milestones.set_business_stages(stages)
        await publish({"type": "system",
                       "text": f"Директор разбил путь к цели на {len(stages)} этапов"})
    await _set_progress_note("Этапы определены, ведём бизнес", publish)

    # ---- ЦИКЛЫ РАЗВИТИЯ под управлением директора ----
    cycle = 0
    while True:
        cycle += 1
        await publish({"type": "system", "text": f"=== Рабочий цикл #{cycle} ==="})

        # Первый цикл после рестарта — даём восстановленным агентам передышку
        global _first_cycle_done
        if not _first_cycle_done:
            _first_cycle_done = True
            await publish({"type": "system",
                           "text": "Офис восстановлен. Директор продолжит управление в следующем цикле."})
            await asyncio.sleep(LOOP_INTERVAL)
            continue

        await _orchestrate(strategy, publish)

        await asyncio.sleep(LOOP_INTERVAL)


async def _orchestrate(strategy: str, publish) -> None:
    """Один ход директора: принять решение и исполнить его."""
    global _current_milestone_id

    goal = brief.get().get("goal", "") or brief.summary()
    ms = milestones.all_stages()

    # Передаём директору, кто сейчас занят / на кулдауне — чтобы он выбирал свободных
    now = time.time()
    agent_availability = {}
    for a in registry.all_agents():
        last = state.last_run_for(a.agent_id)
        cooldown_left = max(0, AGENT_COOLDOWN_SECS - (now - last))
        agent_availability[a.agent_id] = {
            "status": a.status,
            "on_cooldown": cooldown_left > 0,
            "cooldown_secs": int(cooldown_left),
        }

    decision = await orchestrator.decide(goal, strategy, ms, publish, agent_availability)

    thought = decision.get("thought", "")
    if thought:
        await publish({"type": "speech", "agent_id": "orchestrator_1", "text": f"🧭 {thought}"})

    # --- Обновление текущего этапа ---
    cur = decision.get("current_milestone")
    if cur and milestones.get(cur):
        _current_milestone_id = cur
        milestones.mark_active(cur)

    # --- Завершение этапа ---
    done_id = decision.get("milestone_done")
    if done_id and done_id not in (None, "null") and milestones.get(done_id):
        milestones.set_status(done_id, "done")
        summ = decision.get("milestone_summary") or ""
        if summ and summ not in (None, "null"):
            milestones.set_summary(done_id, summ)
        await publish({"type": "system",
                       "text": f"✅ Этап «{milestones.get(done_id)['title']}» завершён"})

    await _set_progress_note(thought or "Директор управляет офисом", publish)

    # --- Исполнение действия ---
    action = decision.get("action", "wait")
    now = time.time()

    if action == "hire":
        role = decision.get("role", "")
        task = decision.get("task", f"Выполни задачи {role}")
        skill = decision.get("skill") or ""
        await _hire_and_run(role, task, publish, skill=skill)

    elif action == "assign":
        agent_id = decision.get("agent_id", "")
        task = decision.get("task", "")
        rec = registry.get(agent_id)
        if rec and task:
            # антидребезг на случай гонки: оркестратор уже должен был выбрать свободного
            if (now - state.last_run_for(agent_id)) < AGENT_COOLDOWN_SECS:
                await publish({"type": "system",
                               "text": f"{agent_id} недавно отработал — директор подождёт"})
                return
            if rec.status == "thinking":
                await publish({"type": "system",
                               "text": f"{agent_id} ещё занят — ждём результат"})
                return
            await _assign(agent_id, rec.role, task, publish)
    else:
        await publish({"type": "system", "text": "Директор: ждём результатов текущих задач"})


async def _assign(agent_id: str, role: str, task: str, publish, skill: str = "") -> None:
    """Поручает задачу конкретному агенту (рабочему, ресёрчеру или стратегу)."""
    await publish({"type": "speech", "agent_id": "orchestrator_1",
                   "text": f"→ Поручаю {agent_id}: {task[:70]}"})

    async def _job():
        registry.update_status(agent_id, "thinking")
        try:
            if role == "researcher":
                result = await researcher.run_async(task, depth="quick", publish=publish,
                                                    agent_id=agent_id)
                state.save_deliverable(agent_id, role, task[:80], result)
            elif role == "strategist":
                result = await strategist.run_async(task, publish=publish, agent_id=agent_id, save=False)
            else:
                fn = agent_factory.create(role, _task_with_context(role, task, skill), agent_id, publish, skill=skill)
                result = await fn()
            registry.update_status(agent_id, "done")
            state.save_last_run(agent_id)
            _attribute_result(agent_id, role, result)
        except Exception as e:
            await publish({"type": "error", "agent_id": agent_id, "text": str(e)[:100]})
            registry.update_status(agent_id, "idle")

    asyncio.create_task(_job())


def _task_with_context(role: str, task: str, skill: str = "") -> str:
    """Обогащает задачу контекстом цели и текущего этапа."""
    goal = brief.get().get("goal", "") or brief.summary()
    cur = milestones.get(_current_milestone_id)
    stage = f"Текущий этап: {cur['title']}\n" if cur else ""
    skill_line = f"Твоя специализация: {skill}\n" if skill else ""
    return (
        f"Цель офиса: {goal}\n{stage}{skill_line}"
        f"Твоя задача от директора: {task}\n\n"
        f"Выдай конкретный готовый результат. Если нужны свежие данные — web_search "
        f"или request_research. Если нужен доступ к внешнему сервису — get_connection или ask_user с инструкцией."
    )


def _attribute_result(agent_id: str, role: str, result: str) -> None:
    """Привязывает результат работы к текущему этапу для сводки."""
    if not result or role in ("orchestrator", "hr"):
        return
    if _current_milestone_id and milestones.get(_current_milestone_id):
        milestones.add_item(_current_milestone_id, result[:200], agent_id, role)


async def _bootstrap(publish) -> str:
    """Разовое определение ниши: ресёрчер (deep) + стратег."""
    await publish({"type": "system", "text": "=== BOOTSTRAP: исследуем нишу клиента ==="})
    milestones.mark_active("research")
    await _set_progress_note("Исследуем рынок и тренды", publish)

    question = brief.research_question() or researcher.DEFAULT_QUESTION
    try:
        research = await researcher.deep(question, publish=publish)
        globals()["_last_research"] = research
    except Exception as e:
        await publish({"type": "error", "agent_id": "researcher_1", "text": str(e)[:100]})
        research = _last_research
    milestones.set_status("research", "done")
    milestones.set_summary("research", (research or "")[:400])

    milestones.mark_active("strategy")
    await _set_progress_note("Строим бизнес-стратегию", publish)
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
    milestones.set_status("strategy", "done")
    milestones.set_summary("strategy", (strategy or "")[:400])

    await publish({"type": "system",
                   "text": "Ниша определена ✓ Больше не переисследуем — развиваем бизнес"})
    return strategy


async def _hire_and_run(role: str, task: str, publish, skill: str = "") -> None:
    # Формируем уникальный agent_id (роль может встречаться несколько раз)
    existing_count = sum(1 for a in registry.all_agents() if a.role == role)
    agent_id = f"{role}_{existing_count + 1}"
    full_task = f"[Скилл: {skill}] {task}" if skill else task
    rec = registry.register(agent_id, role, full_task)
    if rec:
        await publish({
            "type": "hired", "agent_id": agent_id, "role": role,
            "desk": rec.desk, "task": full_task[:100], "skill": skill,
        })
        await _assign(agent_id, role, task, publish, skill=skill)
    else:
        await publish({"type": "system", "text": f"Не удалось зарегистрировать агента {agent_id}"})


def _load_strategy() -> str:
    if STRATEGY_FILE.exists():
        return STRATEGY_FILE.read_text(encoding="utf-8")
    return ""


def _save_strategy(strategy: str) -> None:
    STRATEGY_FILE.parent.mkdir(parents=True, exist_ok=True)
    STRATEGY_FILE.write_text(strategy, encoding="utf-8")


def _hire_initial(publish_sync) -> None:
    """Регистрируем руководящий состав офиса."""
    starters = [
        ("orchestrator_1", "orchestrator", "Управление офисом и постановка задач"),
        ("researcher_1", "researcher", "Исследование рынка и трендов"),
        ("strategist_1", "strategist", "Построение бизнес-стратегии"),
        ("hr_1", "hr", "Найм новых агентов"),
    ]
    for aid, role, task in starters:
        if not registry.has_role(role):
            rec = registry.register(aid, role, task)
            if rec:
                asyncio.get_event_loop().create_task(publish_sync({
                    "type": "hired", "agent_id": aid,
                    "role": role, "desk": rec.desk, "task": rec.task,
                }))
