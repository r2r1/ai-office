"""
Planning Engine — планирование и маршрутизация как отдельная подсистема (BOS §12).

Расслоение loop.py (Phase 6). Два слоя внутри модуля:

  1) ЧИСТЫЕ детерминированные функции чтения мира (без publish, без побочных
     эффектов) — `fallback_plan`, `has_actionable_move`, `dept_actionable`,
     `free_worker_of_role`, `has_orphan_tasks`. Покрыты unit-тестами без
     поднятия офис-цикла.
  2) МАРШРУТИЗАЦИЯ и CEO-оркестрация — `orchestrate`, `apply_company_decision`,
     `run_leaders`, `hire_leader`, `hire_and_run`, `verify_and_fix_if_needed`.
     Эти функции публикуют события и вызывают `execution.assign`/LLM-агентов —
     поведенчески тестируются только живым прогоном (нет здесь моков LLM).
     Владеют анти-цикл состоянием `_last_leader_sig` (повтор решения лидера) —
     тот же признанный SSOT-долг, что у `execution._thinking_since`
     (engineering-principles.md №2: вынос живости из памяти процесса — после
     пятёрки ядра BOS).

  fallback_plan(goal)               — детерминированный план, когда LLM недоступна
  has_actionable_move()             — есть ли вообще ход у офиса на этом цикле
  dept_actionable(dept_id, now)     — есть ли ход у отдела
  free_worker_of_role(dept, role,…) — свободный работник роли
  has_orphan_tasks()                — есть ли задачи без обслуживающего отдела
  orchestrate(...)                  — CEO-тир + лидер-тир одного цикла
  apply_company_decision(...)       — применить решение CEO об отделах/вехах
  run_leaders(...)                  — маршрутизация задач лидерами отделов
  hire_leader/hire_and_run(...)     — наём лидера / наём + назначение работника
  verify_and_fix_if_needed(...)     — финальная проверка сайта перед завершением
  forget_tenant(tid)                — чистит анти-цикл состояние тенанта
"""

import os
import time

from src.office import (plan, org, registry, state, milestones, critic, brief,
                        initiatives, decisions, board, events as events_mod, execution)
from src.agents import orchestrator, leaders
from src.saas import context as ctx

# Антидребезг живости работника (был в loop.py; сюда переехал вместе с потребителями).
AGENT_COOLDOWN_SECS = int(os.getenv("AGENT_COOLDOWN_SECS", "25"))
CEO_REASSESS_EVERY = 3   # CEO пересматривает структуру компании раз в N циклов (экономия токенов)

# Анти-цикл: подпись последнего решения лидера и счётчик повторов (per tenant+dept).
_last_leader_sig: dict[str, tuple[str, int]] = {}
_LEADER_REPEAT_LIMIT = 3  # столько одинаковых решений подряд → пауза/эскалация

# Анти-шум delegate: подпись доски отдела при ПОСЛЕДНЕМ обновлении цели CEO.
# Прод-кейс: пока единственный исполнитель 40+ циклов занят одной задачей, CEO
# каждый гейт «обновлял цель отдела» (28 раз за прогон) — LLM переформулировала
# ту же мысль, состояние не менялось, лента и токены засорялись.
_last_delegate_sig: dict[str, str] = {}


def forget_tenant(tid: str) -> None:
    """Чистит анти-цикл состояние этого модуля (вызывается loop.forget_tenant)."""
    prefix = f"{tid}:"
    for k in [k for k in _last_leader_sig
              if k.startswith(prefix) or k.startswith(f"board:{tid}:")]:
        _last_leader_sig.pop(k, None)
    for k in [k for k in _last_delegate_sig if k.startswith(prefix)]:
        _last_delegate_sig.pop(k, None)


async def _set_progress_note(note: str, publish) -> None:
    payload = milestones.progress_payload()
    payload["note"] = note
    await publish({"type": "progress", **payload})


def fallback_plan(goal: str) -> list[dict]:
    """Детерминированный план под типовой результат, когда LLM-генерация плана недоступна.
    Гарантирует, что офис всегда plan-driven (а не уходит в LLM-хаос)."""
    g = (goal or "").lower()
    # ЯВНЫЙ запрос продукта (императив «сделай/нужен X»), а не упоминание X как продукта бизнеса.
    wants_bot = any(p in g for p in ("нужен бот", "нужен телеграм", "сделай бот", "сделать бот",
                                     "хочу бот", "бот для записи", "бот записи", "бот заявок",
                                     "телеграм-бот", "telegram-бот", "запусти бот"))
    wants_site = any(p in g for p in ("нужен сайт", "нужен лендинг", "сделай сайт", "сделай лендинг",
                                      "сделать сайт", "сделать лендинг", "хочу сайт", "хочу лендинг",
                                      "одностраничник", "landing page", "собери лендинг", "собери сайт"))
    if not wants_bot and not wants_site:
        # ПО УМОЛЧАНИЮ не строим вслепую: готовим план запуска + рекомендации и СПРАШИВАЕМ
        # клиента, что делать первым. (Раньше тут всегда был лендинг — главная причина «глупости».)
        return [
            {"id": "t1",
             "title": "На основе исследования и стратегии подготовить КОРОТКИЙ план запуска "
                      "и рекомендации (позиционирование, оффер, первые 2-3 шага). В конце ОБЯЗАТЕЛЬНО "
                      "через ask_user задать клиенту 1-2 вопроса: что строить первым (лендинг / бот / "
                      "MVP / контент-план) и какие ресурсы есть. НЕ строй продукт, пока клиент не выбрал.",
             "role": "marketer", "deps": [],
             "done_criterion": "готов план запуска + клиенту задан вопрос, что делать дальше"},
        ]
    if wants_bot:
        return [
            {"id": "t1", "title": "Подготовить тексты, услуги и приветствие для бота",
             "role": "marketer", "deps": [], "done_criterion": "готовы тексты и список услуг"},
            {"id": "t2", "title": "Настроить и запустить Telegram-бота сбора заявок",
             "role": "integrator", "deps": ["t1"], "done_criterion": "бот запущен через launch_bot"},
        ]
    # сайт/лендинг — основной кейс. ОДНА production-задача (роль developer владеет
    # визуалом И кодом end-to-end) — раньше здесь были designer→developer как два
    # последовательных шага на один и тот же сайт, и developer систематически
    # пересобирал уже готовый сайт заново вместо точечной проверки (реальный кейс:
    # два полных прохода одного скилла на один лендинг за прогон).
    return [
        {"id": "t1", "title": "Подготовить оффер и продающие тексты для всех блоков лендинга",
         "role": "marketer", "deps": [], "done_criterion": "готов копирайт: оффер, выгоды, FAQ, CTA"},
        {"id": "t2", "title": "Собрать конверсионный многостраничный лендинг в site/ с формой заявки, "
                             "проверить формы/CTA перед сдачей",
         "role": "developer", "deps": ["t1"],
         "done_criterion": "site/index.html + страницы опубликованы, форма шлёт на /api/site-lead, "
                           "формы работают и сайт собирает лиды"},
    ]


def dept_actionable(dept_id: str, now: float) -> bool:
    """Есть ли в отделе ход. Когда план сгенерирован — отдел активен ТОЛЬКО если у него
    есть готовая задача (иначе простаивает, цикл не крутится вхолостую)."""
    if plan.is_generated() and not plan.ready_for_department(dept_id):
        return False
    worker_roles = set(org.member_roles(dept_id))  # роли работников (без лидера)
    members = registry.members_of(dept_id)
    for a in members:
        if a.role not in worker_roles:
            continue  # лидер отдела — не работник
        on_cooldown = (now - state.last_run_for(a.agent_id)) < AGENT_COOLDOWN_SECS
        if a.status != "thinking" and not on_cooldown and not a.paused:
            return True
    existing = {a.role for a in members}
    return any(r not in existing for r in worker_roles)


def has_orphan_tasks() -> bool:
    """Есть ли pending-задачи, которые НЕ обслуживает ни один отдел (роль без отдела —
    например analyst/researcher). Такие нельзя выполнить через отделы → офис завис бы."""
    servable = set()
    for did in org.catalog():
        servable |= set(org.member_roles(did))
    for t in plan.all_tasks():
        if t.get("status") in ("pending", "in_progress") and t.get("role") not in servable \
                and not t.get("department"):
            return True
    return False


def has_actionable_move() -> bool:
    """Есть ли вообще ход у офиса на этом цикле (иначе шедулер может подождать)."""
    # Нет открытых отделов — CEO должен открыть первый: даём циклу ход.
    open_depts = org.open_departments()
    if not open_depts:
        return True
    # Есть задача плана в ещё НЕ открытом отделе → нужен ход CEO, чтобы открыть его
    # (иначе дедлок: открытые отделы доделали своё и спят, а новый отдел не открывается).
    if plan.is_generated():
        if any(d not in open_depts for d in plan.departments_needed()):
            return True
        # Есть неустранимые «висячие» задачи (роль без отдела) → нужен ход, чтобы их закрыть.
        if has_orphan_tasks():
            return True
    now = time.time()
    return any(dept_actionable(did, now) for did in open_depts)


def free_worker_of_role(dept_id: str, role: str, now: float, project_id: str = ""):
    """Свободный (idle, не на паузе, не в cooldown) работник нужной роли в отделе.

    `project_id` — параллельные Work: работник, закреплённый ИМЕННО за этим
    проектом (registry.AgentRecord.project_id), в приоритете; если такого
    свободного нет — годится универсальный (project_id="", legacy — нанят до
    появления параллельных проектов или лидер/служебная роль). Работник,
    закреплённый за ДРУГИМ проектом, не подходит — иначе один "developer_p1"
    хватал бы задачи и project'а p2 тоже, съедая чужой слот параллельности."""
    candidates = []
    for a in registry.members_of(dept_id):
        if a.role != role or a.status == "thinking" or a.paused:
            continue
        if a.project_id and project_id and a.project_id != project_id:
            continue  # закреплён за ДРУГИМ проектом — не наш кандидат
        if (now - state.last_run_for(a.agent_id)) < AGENT_COOLDOWN_SECS:
            continue
        candidates.append(a)
    if not candidates:
        return None
    exact = next((a for a in candidates if project_id and a.project_id == project_id), None)
    return exact or next((a for a in candidates if not a.project_id), None) or candidates[0]


def _has_role_for_project(dept_id: str, role: str, project_id: str) -> bool:
    """Уже нанят работник ИМЕННО под (отдел, роль, проект) — неважно, свободен
    он сейчас или занят. Используется перед наймом: если такой уже есть, но
    занят — просто ждём его, а не заводим второго (MAX_PER_ROLE=1, но теперь
    на уровне (роль, проект), а не только (роль, компания))."""
    return any(a.role == role and a.project_id == project_id
               for a in registry.members_of(dept_id))


async def verify_and_fix_if_needed(publish) -> bool:
    """Финальная верификация: если сайт есть и у него критические проблемы —
    добавляем fix-задачу на доску вместо того чтобы объявить работу готовой.
    Возвращает True если задача добавлена (офис продолжит работу)."""
    problems = critic.check_site()
    critical = [p for p in problems if critic.is_critical(p)]
    if not critical:
        return False
    # Дедуп по НЕзакрытым fix-задачам: done не глушит новую попытку (иначе одна
    # выполненная доработка навсегда маскировала бы оставшиеся критические
    # проблемы); blocked глушит (ждём владельца, не плодим дубли). Бесконечный
    # цикл исключён эскалацией приёмки: 3 провала → задача блокируется сама.
    crit_text = "; ".join(critic.text_of(p) for p in critical[:2])
    fix_title = "Исправить критические проблемы сайта: " + crit_text[:120]
    if any("исправить критические" in (t.get("title", "").lower())
           and t.get("status") in ("pending", "in_progress", "blocked")
           for t in plan.all_tasks()):
        return False  # доработка уже в очереди/в работе/у владельца — не дублируем
    await publish({"type": "system",
                   "text": f"🔍 Финальная проверка нашла проблемы: {crit_text[:100]} — "
                           "добавляю задачу на исправление"})
    plan.add_task(fix_title, "developer",
                  "форма шлёт на /api/site-lead, сайт открывается без ошибок",
                  requested_by="orchestrator_1")
    return True


async def hire_leader(dept_id: str, objective: str, publish) -> None:
    role = org.lead_role(dept_id)
    if registry.has_role(role):
        return
    agent_id = f"{role}_1"
    rec = registry.register(agent_id, role, objective[:100],
                            department=dept_id, manager="orchestrator_1")
    if rec:
        await publish({"type": "hired", "agent_id": agent_id, "role": role,
                       "desk": rec.desk, "task": objective[:100]})


async def hire_and_run(role: str, task: str, publish, skill: str = "",
                       department: str = "", manager: str = "", task_id: str = "",
                       project_id: str = "") -> None:
    """`project_id` — нанимает работника, ЗАКРЕПЛЁННОГО за этим проектом (параллельные
    Work: у каждого активного проекта может быть свой developer/designer/...), а не
    общего на компанию. Идентификатор строится от project_id, а не от порядкового
    номера — иначе при параллельном найме двух воркеров одной роли для разных
    проектов в один цикл возможна гонка за один и тот же agent_id."""
    if project_id:
        agent_id = f"{role}_{project_id}"
    else:
        existing_count = sum(1 for a in registry.all_agents() if a.role == role)
        agent_id = f"{role}_{existing_count + 1}"
    full_task = f"[Скилл: {skill}] {task}" if skill else task
    rec = registry.register(agent_id, role, full_task, department=department, manager=manager,
                            project_id=project_id)
    if rec:
        await publish({"type": "hired", "agent_id": agent_id, "role": role,
                       "desk": rec.desk, "task": full_task[:100], "skill": skill})
        objective = org.state_of(department).get("objective", "") if department else ""
        if task_id and plan.is_generated():
            plan.assign(task_id, agent_id)
        await execution.assign(agent_id, role, task, publish, skill=skill,
                      department=department, objective=objective, task_id=task_id)
    else:
        await publish({"type": "system", "text": f"Не удалось зарегистрировать агента {agent_id}"})


async def run_leaders(goal: str, ms: list, publish) -> None:
    now = time.time()
    for dept_id in org.open_departments():
        lead = org.lead_id(dept_id)
        if not lead or not dept_actionable(dept_id, now):
            continue

        objective = org.state_of(dept_id).get("objective", "")
        ready = plan.ready_for_department(dept_id) if plan.is_generated() else []

        # Лидер ОТСЛЕЖИВАЕТ доску своего отдела (видимо в ленте и в задаче лидера).
        if plan.is_generated():
            summary = plan.board_summary(dept_id)
            sig_key = f"board:{ctx.get_tenant()}:{dept_id}"
            if _last_leader_sig.get(sig_key, ("", 0))[0] != summary:
                _last_leader_sig[sig_key] = (summary, 0)
                await publish({"type": "speech", "agent_id": lead,
                               "text": f"📋 Доска отдела: {summary}"})

        # ---- ДЕТЕРМИНИРОВАННЫЙ ПУТЬ (без LLM) — главный ускоритель ----
        # План даёт конкретные задачи отдела — маршрутизируем сами, не дёргая модель
        # лидера каждый цикл (в логе CTO сделал 119 пустых вызовов «жду»).
        if ready:
            member_roles = org.member_roles(dept_id)
            handled = False
            # Мьютекс артефакта: пока одна сайт-задача в работе, вторую НЕ назначаем —
            # параллельные designer/developer переписывали site/index.html целиком и
            # затирали друг друга («последний победил», 3D-версия исчезала).
            site_busy = plan.site_task_in_progress()
            if site_busy:
                ready = [t for t in ready if not plan.touches_site(t)]
            # 1) Назначаем КАЖДУЮ готовую задачу, под которую есть свободный работник —
            # не только первую. Параллельные Work (project_limits): если у отдела
            # ready-задачи от двух разных активных проектов, оба должны сдвинуться
            # в этом же цикле, а не по очереди через цикл. registry.update_status
            # внутри execution.assign синхронна (пишет файл сразу), поэтому уже
            # занятый в этой же итерации работник не будет назначен дважды.
            unassigned = []
            for t in ready:
                proj_id = t.get("project", "")
                free = free_worker_of_role(dept_id, t.get("role", ""), now, project_id=proj_id)
                if not free:
                    unassigned.append(t)
                    continue
                task_txt = t.get("title", "")
                if t.get("done_criterion"):
                    task_txt += f"\n✅ ЗАДАЧА ВЫПОЛНЕНА, КОГДА: {t['done_criterion']}"
                if t.get("last_feedback"):
                    # Повторная попытка после провала приёмки: исполнитель видит,
                    # ЧТО именно не прошло, а не решает задачу вслепую заново.
                    task_txt += f"\n{t['last_feedback']}"
                plan.assign(t["id"], free.agent_id)  # доска: взято в работу
                await execution.assign(free.agent_id, free.role, task_txt, publish,
                              department=dept_id, objective=objective, task_id=t["id"])
            if len(unassigned) < len(ready):
                continue  # хотя бы одну задачу в этом цикле сдвинули
            # 2) Ни для одной готовой задачи нет свободного работника — нанимаем
            # недостающую роль, но только под ПРОЕКТ, у которого её ЕЩЁ ВООБЩЕ нет
            # (не плодим второго work'ера на тот же (роль, проект), если первый
            # просто занят — тогда просто ждём его). Один найм за цикл — не
            # наспамить сразу несколькими агентами разом.
            for t in unassigned:
                role = t.get("role", "")
                proj_id = t.get("project", "")
                if role not in member_roles or _has_role_for_project(dept_id, role, proj_id):
                    continue
                crit = f"\n✅ ЗАДАЧА ВЫПОЛНЕНА, КОГДА: {t['done_criterion']}" if t.get("done_criterion") else ""
                await hire_and_run(role, t.get("title", f"Задачи {role}") + crit,
                                    publish, department=dept_id, manager=lead, task_id=t["id"],
                                    project_id=proj_id)
                break
            # 3) Все нужные роли под все проекты уже наняты, но заняты —
            # детерминированный wait без LLM.
            continue

        # План — ЕДИНСТВЕННЫЙ источник работы. Если он сгенерирован, но готовых задач для
        # отдела нет (всё сделано или ждут зависимостей) — отдел ПРОСТАИВАЕТ. Лидер НЕ
        # выдумывает работу через LLM (раньше отсюда шли 128 пустых вызовов CTO и хаос:
        # «придумай outreach», «собери 50 лидов» — недостижимые задачи по кругу).
        if plan.is_generated():
            continue

        # ---- LLM-ПУТЬ — ТОЛЬКО пока план ещё не сгенерирован (ранний bootstrap) ----
        members = registry.members_of(dept_id)
        availability = {}
        for a in members:
            left = max(0, AGENT_COOLDOWN_SECS - (now - state.last_run_for(a.agent_id)))
            availability[a.agent_id] = {"status": a.status, "on_cooldown": left > 0,
                                        "cooldown_secs": int(left)}

        decision = await leaders.decide(dept_id, goal, objective, ms, availability, publish,
                                        suggested_task=None)

        # Анти-цикл: если лидер N раз подряд принимает то же решение — пауза + эскалация к CEO.
        sig = f"{decision.get('action')}|{decision.get('agent_id','')}|{decision.get('role','')}"
        key = f"{ctx.get_tenant()}:{dept_id}"
        prev_sig, cnt = _last_leader_sig.get(key, ("", 0))
        cnt = cnt + 1 if sig == prev_sig else 1
        _last_leader_sig[key] = (sig, cnt)
        if cnt >= _LEADER_REPEAT_LIMIT and decision.get("action") != "assign":
            await publish({"type": "system",
                           "text": f"⚠ {lead}: решение повторяется {cnt}× — эскалация к CEO"})
            _last_leader_sig[key] = (sig, 0)
            continue  # пропускаем ход; CEO пересмотрит на следующем гейте

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
            await hire_and_run(role, task, publish, skill=skill, department=dept_id, manager=lead)
        elif action == "assign":
            agent_id = decision.get("agent_id", "")
            task = decision.get("task", "")
            rec = registry.get(agent_id)
            if rec and task:
                if (now - state.last_run_for(agent_id)) < AGENT_COOLDOWN_SECS:
                    continue
                if rec.status == "thinking":
                    continue
                await execution.assign(agent_id, rec.role, task, publish, department=dept_id, objective=objective)


async def orchestrate(strategy: str, publish, tech_design: str = "", cycle: int = 0) -> None:
    """
    Двухуровневое управление:
      1) CEO-тир — управляет ОТДЕЛАМИ (открыть/закрыть/цель). Вызывается по необходимости.
      2) Лидер-тир — каждый открытый отдел сам распределяет работу между подчинёнными.
    """
    goal = brief.effective_goal()
    ms = milestones.all_stages()

    # ---- Висячие задачи: роль без отдела (analyst/researcher/неизвестная) не обслуживается
    # отделами → авто-закрываем, чтобы офис не завис на недостижимой задаче и мог завершиться.
    if plan.is_generated() and has_orphan_tasks():
        servable = set()
        for did in org.catalog():
            servable |= set(org.member_roles(did))
        for t in plan.all_tasks():
            if t.get("status") in ("pending", "in_progress") and not t.get("department") \
                    and t.get("role") not in servable:
                # skipped, НЕ done: задача не выполнялась — done-прогресс не завышаем
                # (раньше complete() зачитывал её как сделанную работу).
                plan.mark(t["id"], "skipped")
                await publish({"type": "system",
                               "text": f"⏭ Задача {t['id']} ({t.get('role','?')}) снята — "
                                       f"роль не входит в отделы, сдачу не блокирует"})

    # ---- CEO-тир (гейт по необходимости — экономия токенов) ----
    need_ceo = (not org.open_departments()) or (cycle % CEO_REASSESS_EVERY == 0)
    if need_ceo:
        company = await orchestrator.decide_company(goal, strategy, ms, publish)
        await apply_company_decision(company, publish)

    # ---- Блок 4: Инициативы из opportunity-событий ----
    # CEO превращает наблюдённые возможности отделов в конкретные предложения
    # с ROI-оценкой. Пользователь видит карточку и принимает или отклоняет.
    try:
        opp_events = [e for e in events_mod.pending() if e.get("kind") == "opportunity"]
        for ev in opp_events[:2]:  # макс 2 инициативы за цикл
            summary = ev.get("summary", "")
            if not summary or initiatives.has_pending_similar(summary):
                events_mod.mark_processed([ev["id"]])
                continue
            ini = await orchestrator.generate_initiative(goal, strategy, summary, publish)
            if ini and ini.get("title"):
                iid = initiatives.add(
                    title=ini["title"],
                    rationale=ini.get("rationale", summary),
                    expected_outcome=ini.get("expected_outcome", ""),
                    estimated_effort=ini.get("estimated_effort", "1-2 цикла"),
                    tasks=ini.get("tasks", []),
                    source="event",
                )
                await publish({"type": "speech", "agent_id": "orchestrator_1",
                               "text": f"💡 Возможная инициатива: {ini['title']} — запускаю анализ, прежде чем спросить"})
                # Глубокое исследование ДО показа решения пользователю (не
                # заголовок «на глазок» — предприниматель решает по анализу).
                from src.office import initiative_research
                await initiative_research.run(iid, ini["title"], ini.get("rationale", summary), publish)
            events_mod.mark_processed([ev["id"]])
    except Exception as e:
        await publish({"type": "error", "agent_id": "orchestrator_1",
                       "text": f"Инициатива не сгенерирована: {str(e)[:100]}"})

    # ---- Детерминированный автостарт ----
    # Слабые модели порой возвращают wait и офис висит без единого отдела (как в логе).
    # Если отделы ВООБЩЕ ни разу не открывались — стартуем технический: почти любой продукт
    # начинается с него. Дальше структурой снова управляет CEO.
    ever_opened = any(org.state_of(d) for d in org.catalog())
    if not org.open_departments() and not ever_opened:
        obj = (goal or "Подготовить продукт")[:140]
        org.open_department("tech", reason="автостарт продукта", objective=obj)
        await hire_leader("tech", obj, publish)
        await publish({"type": "system", "text": "📂 Открыт «Технический отдел» (автостарт)"})

    # ---- Параллелизм: открываем ВСЕ отделы, которых требует план задач ----
    # (независимые ветки плана исполняются параллельно — как в реальной компании).
    for dept_id in plan.departments_needed():
        if dept_id not in org.open_departments():
            obj = (goal or "")[:140]
            org.open_department(dept_id, reason="нужен по плану задач", objective=obj)
            await hire_leader(dept_id, obj, publish)
            await publish({"type": "system",
                           "text": f"📂 Открыт «{org.catalog()[dept_id]['name']}» (по плану задач)"})

    # ---- Лидер-тир — по каждому открытому отделу с возможным ходом ----
    await run_leaders(goal, ms, publish)


async def apply_company_decision(decision: dict, publish) -> None:
    action = decision.get("action", "wait")
    thought = decision.get("thought", "")
    # Не шумим речью CEO, когда он просто ждёт — это плодило спам «CEO не принял решение».
    if thought and action != "wait":
        await publish({"type": "speech", "agent_id": "orchestrator_1", "text": f"🧭 {thought}"})

    # Блок 3: Логируем структурированное решение CEO (для UI «Почему?»)
    did = ""
    if action != "wait":
        did = decisions.record(
            action=action,
            target=decision.get("department", decision.get("objective", ""))[:80],
            thought=thought,
            alternatives=decision.get("alternatives") or [],
            confidence=decision.get("confidence", 60),
            risks=decision.get("risks") or [],
            expected_effect=decision.get("expected_effect", ""),
            data_used=decision.get("data_used") or ["strategy", "milestones"],
            made_by="orchestrator_1",
            # prompt_id проставит Phase 1, когда CEO-промпт пойдёт через Prompt Builder
            # (сейчас decide_company не логирует свой промпт) — цепочка станет полной.
            prompt_id=decision.get("_prompt_id", ""),
        )
        await publish({"type": "decision_record", "decision_id": did, "action": action,
                       "thought": thought, "confidence": decision.get("confidence", 60)})

    # Блок 6: Совет директоров при антицикле (3+ wait подряд или блокеры)
    if action == "wait":
        board.record_wait()
        if board.needs_session():
            conflict = f"CEO заблокирован: {thought or 'нет прогресса'}"
            await board.run_session(conflict, publish)
    else:
        board.reset_wait_streak()

    # Бизнес-этапи (вехи) ведёт CEO
    cur = decision.get("current_milestone")
    if cur and milestones.get(cur):
        execution.set_cur_ms(cur)
        milestones.mark_active(cur)
    done_id = decision.get("milestone_done")
    if done_id and done_id not in (None, "null"):
        ms = milestones.get(done_id)
        # CEO принимает решение о статусе каждый цикл заново и может повторно
        # прислать milestone_done для этапа, уже закрытого на прошлом цикле — без
        # проверки текущего статуса это публиковало «Этап завершён» в ленту заново
        # при каждом цикле (реальный кейс: один и тот же этап объявлялся 6 раз подряд).
        if ms and ms.get("status") != "done":
            milestones.set_status(done_id, "done")
            summ = decision.get("milestone_summary") or ""
            if summ and summ not in (None, "null"):
                milestones.set_summary(done_id, summ)
            await publish({"type": "system", "text": f"✅ Этап «{ms['title']}» завершён"})
    await _set_progress_note(thought or "CEO управляет компанией", publish)

    action = decision.get("action", "wait")
    dept = decision.get("department", "")
    if action == "open_department" and dept in org.catalog():
        objective = decision.get("objective") or ""
        org.open_department(dept, reason=thought, objective=objective)
        await hire_leader(dept, objective, publish)
        await publish({"type": "system", "text": f"📂 CEO открыл «{org.catalog()[dept]['name']}»"})
    elif action == "close_department" and dept in org.catalog():
        org.close_department(dept)
        await publish({"type": "system", "text": f"📁 CEO закрыл «{org.catalog()[dept]['name']}»"})
    elif action == "delegate" and dept in org.catalog():
        # Обновление цели имеет смысл, только если состояние отдела ИЗМЕНИЛОСЬ с
        # прошлого delegate (задача закрылась/провалилась/добавилась). Иначе это
        # переформулировка того же — шум в ленте и потраченный вызов (см. _last_delegate_sig).
        board_sig = plan.board_summary(dept) if plan.is_generated() else ""
        sig_key = f"{ctx.get_tenant()}:delegate:{dept}"
        if board_sig and _last_delegate_sig.get(sig_key) == board_sig:
            pass  # доска не изменилась — «новая цель» ничего не меняет, молча пропускаем
        else:
            _last_delegate_sig[sig_key] = board_sig
            org.set_objective(dept, decision.get("objective") or "")
            await publish({"type": "system", "text": f"🎯 CEO обновил цель отдела «{org.catalog()[dept]['name']}»"})

    # Observability: фиксируем срез мира ПОСЛЕ применения решения и привязываем к нему.
    # world.diff(этот срез, предыдущий) = «что решение изменило в мире» — по нему
    # Observability строит цепочку промпт → решение → diff (Phase 0.5, DoD).
    if did:
        try:
            from src.office import world
            snap = world.save_snapshot(reason=f"decision:{did}")
            decisions.set_snapshot(did, snap.get("snapshot_id", ""))
        except Exception:
            pass  # журнал наблюдаемости не должен ронять цикл
