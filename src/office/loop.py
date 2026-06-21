"""
Автономный офис — мультиарендный менеджер.

`run()` опрашивает тенантов (workspaces) и для каждого, у кого есть готовый бриф,
запускает СВОЙ офис-цикл (`_run_office`) в отдельной задаче с установленным
контекстом тенанта. Внутри одного тенанта логика прежняя: BOOTSTRAP (ресёрчер →
стратег → архитектор → этапы), затем циклы директора.

Контекст тенанта (`ctx.set_tenant`) ставится в начале офис-задачи и автоматически
наследуется дочерними задачами (`asyncio.create_task` копирует contextvars).
"""

import asyncio
import os
import time

from src.office import bus, registry, brief, state, milestones, org
from src.agents import researcher, strategist, orchestrator, architect, leaders
from src.agents import agent_factory
from src.saas import context as ctx
from src.saas import store as saas_store

LOOP_INTERVAL = int(os.getenv("LOOP_INTERVAL_SECONDS", "10"))
MANAGER_POLL = 5          # как часто менеджер ищет новых тенантов для запуска
AGENT_COOLDOWN_SECS = 60
CEO_REASSESS_EVERY = 3    # CEO пересматривает структуру компании раз в N циклов (экономия токенов)

# Состояние по тенантам
_current_ms: dict[str, str] = {}        # tid -> id текущего этапа
_first_cycle_done: dict[str, bool] = {} # tid -> прошёл ли первый цикл
_office_tasks: dict[str, asyncio.Task] = {}


def _cur_ms() -> str:
    return _current_ms.get(ctx.get_tenant(), "")


def _set_cur_ms(v: str) -> None:
    _current_ms[ctx.get_tenant()] = v


def _strategy_text() -> str:
    f = ctx.tenant_dir() / "strategy.md"
    return f.read_text(encoding="utf-8") if f.exists() else ""


def _save_strategy(strategy: str) -> None:
    (ctx.tenant_dir() / "strategy.md").write_text(strategy, encoding="utf-8")


# ============================================================
# МЕНЕДЖЕР: запускает офис для каждого тенанта с готовым брифом
# ============================================================
async def run() -> None:
    while True:
        try:
            for ws in saas_store.all_workspaces():
                tid = ws["id"]
                task = _office_tasks.get(tid)
                if task and not task.done():
                    continue
                ctx.set_tenant(tid)
                if brief.is_ready():
                    _office_tasks[tid] = asyncio.create_task(_run_office(tid))
        except Exception:
            pass
        await asyncio.sleep(MANAGER_POLL)


async def _run_office(tid: str) -> None:
    """Полный жизненный цикл офиса одного тенанта."""
    ctx.set_tenant(tid)
    publish = bus.publish

    _hire_initial(publish)
    _first_cycle_done[tid] = not bool(state.saved_agents())

    # ---- BOOTSTRAP ----
    strategy = _strategy_text()
    if strategy:
        milestones.set_status("research", "done")
        milestones.set_status("strategy", "done")
    else:
        strategy = await _bootstrap(publish)

    tech_design = architect.load()
    if not tech_design:
        goal = brief.get().get("goal", "") or brief.summary()
        await publish({"type": "system", "text": "Архитектор проектирует техническое решение..."})
        try:
            tech_design = await architect.run_async(strategy, goal, publish)
        except Exception as e:
            await publish({"type": "error", "agent_id": "architect_1", "text": str(e)[:100]})

    if not milestones.has_business_stages():
        goal = brief.get().get("goal", "") or brief.summary()
        stages = await orchestrator.plan_milestones(strategy, goal, publish)
        milestones.set_business_stages(stages)
        await publish({"type": "system", "text": f"Директор разбил путь к цели на {len(stages)} этапов"})

    # ---- ЦИКЛЫ ----
    cycle = 0
    while True:
        cycle += 1
        if milestones.all_business_done():
            await _set_progress_note("🎉 Все этапы пройдены — офис в режиме ожидания", publish)
            await asyncio.sleep(max(LOOP_INTERVAL * 6, 60))
            continue
        if not _first_cycle_done.get(tid):
            _first_cycle_done[tid] = True
            # Рестарт убил задачи агентов, но статус 'thinking' остался в файле —
            # сбрасываем, иначе лидеры считают подчинённых занятыми и не переназначают.
            reset = registry.reset_stuck_statuses()
            if reset:
                await publish({"type": "system",
                               "text": f"Сброшены зависшие статусы: {', '.join(reset)}"})
            await publish({"type": "system",
                           "text": "Офис восстановлен. Директор продолжит управление в следующем цикле."})
            await asyncio.sleep(LOOP_INTERVAL)
            continue
        if not _has_actionable_move():
            await asyncio.sleep(LOOP_INTERVAL)
            continue
        await publish({"type": "system", "text": f"=== Рабочий цикл #{cycle} ==="})
        tech_design = architect.load()
        await _orchestrate(strategy, publish, tech_design=tech_design, cycle=cycle)
        await asyncio.sleep(LOOP_INTERVAL)


def _dept_actionable(dept_id: str, now: float) -> bool:
    """Есть ли в отделе ход: свободный работник или не хватает роли отдела."""
    worker_roles = set(org.member_roles(dept_id))  # роли работников (без лидера)
    members = registry.members_of(dept_id)
    for a in members:
        if a.role not in worker_roles:
            continue  # лидер отдела — не работник
        on_cooldown = (now - state.last_run_for(a.agent_id)) < AGENT_COOLDOWN_SECS
        if a.status != "thinking" and not on_cooldown:
            return True
    existing = {a.role for a in members}
    return any(r not in existing for r in worker_roles)


def _has_actionable_move() -> bool:
    # Нет открытых отделов — CEO должен открыть первый: даём циклу ход.
    open_depts = org.open_departments()
    if not open_depts:
        return True
    now = time.time()
    return any(_dept_actionable(did, now) for did in open_depts)


async def _set_progress_note(note: str, publish) -> None:
    payload = milestones.progress_payload()
    payload["note"] = note
    await publish({"type": "progress", **payload})


async def _orchestrate(strategy: str, publish, tech_design: str = "", cycle: int = 0) -> None:
    """
    Двухуровневое управление:
      1) CEO-тир — управляет ОТДЕЛАМИ (открыть/закрыть/цель). Вызывается по необходимости.
      2) Лидер-тир — каждый открытый отдел сам распределяет работу между подчинёнными.
    """
    goal = brief.get().get("goal", "") or brief.summary()
    ms = milestones.all_stages()

    # ---- CEO-тир (гейт по необходимости — экономия токенов) ----
    need_ceo = (not org.open_departments()) or (cycle % CEO_REASSESS_EVERY == 0)
    if need_ceo:
        company = await orchestrator.decide_company(goal, strategy, ms, publish)
        await _apply_company_decision(company, publish)

    # ---- Детерминированный автостарт ----
    # Слабые модели порой возвращают wait и офис висит без единого отдела (как в логе).
    # Если отделы ВООБЩЕ ни разу не открывались — стартуем технический: почти любой продукт
    # начинается с него. Дальше структурой снова управляет CEO.
    ever_opened = any(org.state_of(d) for d in org.catalog())
    if not org.open_departments() and not ever_opened:
        obj = (goal or "Подготовить продукт")[:140]
        org.open_department("tech", reason="автостарт продукта", objective=obj)
        await _hire_leader("tech", obj, publish)
        await publish({"type": "system", "text": "📂 Открыт «Технический отдел» (автостарт)"})

    # ---- Лидер-тир — по каждому открытому отделу с возможным ходом ----
    await _run_leaders(goal, ms, publish)


async def _apply_company_decision(decision: dict, publish) -> None:
    action = decision.get("action", "wait")
    thought = decision.get("thought", "")
    # Не шумим речью CEO, когда он просто ждёт — это плодило спам «CEO не принял решение».
    if thought and action != "wait":
        await publish({"type": "speech", "agent_id": "orchestrator_1", "text": f"🧭 {thought}"})

    # Бизнес-этапи (вехи) ведёт CEO
    cur = decision.get("current_milestone")
    if cur and milestones.get(cur):
        _set_cur_ms(cur)
        milestones.mark_active(cur)
    done_id = decision.get("milestone_done")
    if done_id and done_id not in (None, "null") and milestones.get(done_id):
        milestones.set_status(done_id, "done")
        summ = decision.get("milestone_summary") or ""
        if summ and summ not in (None, "null"):
            milestones.set_summary(done_id, summ)
        await publish({"type": "system", "text": f"✅ Этап «{milestones.get(done_id)['title']}» завершён"})
    await _set_progress_note(thought or "CEO управляет компанией", publish)

    action = decision.get("action", "wait")
    dept = decision.get("department", "")
    if action == "open_department" and dept in org.catalog():
        objective = decision.get("objective") or ""
        org.open_department(dept, reason=thought, objective=objective)
        await _hire_leader(dept, objective, publish)
        await publish({"type": "system", "text": f"📂 CEO открыл «{org.catalog()[dept]['name']}»"})
    elif action == "close_department" and dept in org.catalog():
        org.close_department(dept)
        await publish({"type": "system", "text": f"📁 CEO закрыл «{org.catalog()[dept]['name']}»"})
    elif action == "delegate" and dept in org.catalog():
        org.set_objective(dept, decision.get("objective") or "")
        await publish({"type": "system", "text": f"🎯 CEO обновил цель отдела «{org.catalog()[dept]['name']}»"})


async def _hire_leader(dept_id: str, objective: str, publish) -> None:
    role = org.lead_role(dept_id)
    if registry.has_role(role):
        return
    agent_id = f"{role}_1"
    rec = registry.register(agent_id, role, objective[:100],
                            department=dept_id, manager="orchestrator_1")
    if rec:
        await publish({"type": "hired", "agent_id": agent_id, "role": role,
                       "desk": rec.desk, "task": objective[:100]})


async def _run_leaders(goal: str, ms: list, publish) -> None:
    now = time.time()
    for dept_id in org.open_departments():
        lead = org.lead_id(dept_id)
        if not lead or not _dept_actionable(dept_id, now):
            continue

        members = registry.members_of(dept_id)
        availability = {}
        for a in members:
            left = max(0, AGENT_COOLDOWN_SECS - (now - state.last_run_for(a.agent_id)))
            availability[a.agent_id] = {"status": a.status, "on_cooldown": left > 0,
                                        "cooldown_secs": int(left)}

        objective = org.state_of(dept_id).get("objective", "")
        decision = await leaders.decide(dept_id, goal, objective, ms, availability, publish)

        report = decision.get("report", "")
        if report:
            registry.update_status(lead, "idle", report)
        thought = decision.get("thought", "")
        if thought:
            await publish({"type": "speech", "agent_id": lead, "text": f"👔 {thought}"})

        action = decision.get("action", "wait")
        if action == "hire":
            role = decision.get("role", "")
            task = decision.get("task", f"Выполни задачи {role}")
            skill = decision.get("skill") or ""
            await _hire_and_run(role, task, publish, skill=skill, department=dept_id, manager=lead)
        elif action == "assign":
            agent_id = decision.get("agent_id", "")
            task = decision.get("task", "")
            rec = registry.get(agent_id)
            if rec and task:
                if (now - state.last_run_for(agent_id)) < AGENT_COOLDOWN_SECS:
                    continue
                if rec.status == "thinking":
                    continue
                await _assign(agent_id, rec.role, task, publish, department=dept_id, objective=objective)


async def _assign(agent_id: str, role: str, task: str, publish, skill: str = "",
                  department: str = "", objective: str = "") -> None:
    await publish({"type": "speech", "agent_id": "orchestrator_1",
                   "text": f"→ Поручаю {agent_id}: {task[:70]}"})

    async def _job():
        registry.update_status(agent_id, "thinking")
        try:
            if role == "researcher":
                result = await researcher.run_async(task, depth="quick", publish=publish, agent_id=agent_id)
                state.save_deliverable(agent_id, role, task[:80], result)
            elif role == "strategist":
                result = await strategist.run_async(task, publish=publish, agent_id=agent_id, save=False)
            else:
                ctx_task = _task_with_context(role, task, skill, department=department, objective=objective)
                fn = agent_factory.create(role, ctx_task, agent_id, publish, skill=skill)
                result = await fn()
            registry.update_status(agent_id, "done")
            state.save_last_run(agent_id)
            _attribute_result(agent_id, role, result)
        except Exception as e:
            await publish({"type": "error", "agent_id": agent_id, "text": str(e)[:100]})
            registry.update_status(agent_id, "idle")

    asyncio.create_task(_job())


def _task_with_context(role: str, task: str, skill: str = "",
                       department: str = "", objective: str = "") -> str:
    goal = brief.get().get("goal", "") or brief.summary()
    cur = milestones.get(_cur_ms())
    stage = f"Текущий этап: {cur['title']}\n" if cur else ""
    skill_line = f"Твоя специализация: {skill}\n" if skill else ""
    # Контекст отдела: какому лидеру подчинён и какая у отдела цель
    dept_line = ""
    if department and department in org.catalog():
        title = org.lead_title(department)
        dept_line = f"Твой отдел: {org.catalog()[department]['name']} (руководитель — {title}).\n"
        if objective:
            dept_line += f"Цель отдела от CEO: {objective}\n"
    tdd = architect.load()
    tdd_section = f"\n=== ТЕХНИЧЕСКОЕ ЗАДАНИЕ АРХИТЕКТОРА (кратко) ===\n{tdd[:1200]}\n" if tdd else ""
    return (
        f"Цель компании: {goal}\n{stage}{dept_line}{skill_line}"
        f"Твоя задача от руководителя: {task}\n"
        f"{tdd_section}\n"
        f"Выдай конкретный готовый результат. Если нужны свежие данные — web_search "
        f"или request_research. Если нужен доступ к внешнему сервису — get_connection или ask_user с инструкцией."
    )


def _attribute_result(agent_id: str, role: str, result: str) -> None:
    if not result or role in ("orchestrator", "hr"):
        return
    cur = _cur_ms()
    if cur and milestones.get(cur):
        milestones.add_item(cur, result[:200], agent_id, role)


async def _bootstrap(publish) -> str:
    await publish({"type": "system", "text": "=== BOOTSTRAP: исследуем нишу клиента ==="})
    milestones.mark_active("research")
    await _set_progress_note("Исследуем рынок и тренды", publish)

    question = brief.research_question() or researcher.DEFAULT_QUESTION
    try:
        research = await researcher.deep(question, publish=publish)
    except Exception as e:
        await publish({"type": "error", "agent_id": "researcher_1", "text": str(e)[:100]})
        research = ""
    milestones.set_status("research", "done")
    milestones.set_summary("research", (research or "")[:400])

    milestones.mark_active("strategy")
    await _set_progress_note("Строим бизнес-стратегию", publish)
    strat_input = research
    if brief.summary():
        strat_input = f"БРИФ КЛИЕНТА:\n{brief.summary()}\n\nИССЛЕДОВАНИЕ РЫНКА:\n{research}"
    try:
        strategy = await strategist.run_async(strat_input, publish=publish)
        _save_strategy(strategy)
    except Exception as e:
        await publish({"type": "error", "agent_id": "strategist_1", "text": str(e)[:100]})
        strategy = ""
    milestones.set_status("strategy", "done")
    milestones.set_summary("strategy", (strategy or "")[:400])
    return strategy


async def _hire_and_run(role: str, task: str, publish, skill: str = "",
                        department: str = "", manager: str = "") -> None:
    existing_count = sum(1 for a in registry.all_agents() if a.role == role)
    agent_id = f"{role}_{existing_count + 1}"
    full_task = f"[Скилл: {skill}] {task}" if skill else task
    rec = registry.register(agent_id, role, full_task, department=department, manager=manager)
    if rec:
        await publish({"type": "hired", "agent_id": agent_id, "role": role,
                       "desk": rec.desk, "task": full_task[:100], "skill": skill})
        objective = org.state_of(department).get("objective", "") if department else ""
        await _assign(agent_id, role, task, publish, skill=skill,
                      department=department, objective=objective)
    else:
        await publish({"type": "system", "text": f"Не удалось зарегистрировать агента {agent_id}"})


def _hire_initial(publish_sync) -> None:
    # CEO + штаб стратегии. Лидеры отделов и работники нанимаются по необходимости
    # (CEO открывает отдел → нанимается лидер → лидер нанимает работников).
    starters = [
        ("orchestrator_1", "orchestrator", "Управление компанией и отделами"),
        ("researcher_1", "researcher", "Исследование рынка и трендов"),
        ("strategist_1", "strategist", "Построение бизнес-стратегии"),
        ("architect_1", "architect", "Техническое проектирование решения"),
    ]
    for aid, role, task in starters:
        if not registry.has_role(role):
            rec = registry.register(aid, role, task)
            if rec:
                asyncio.get_event_loop().create_task(publish_sync({
                    "type": "hired", "agent_id": aid, "role": role, "desk": rec.desk, "task": rec.task,
                }))
