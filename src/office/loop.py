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

from src.office import bus, registry, brief, state, milestones, org, plan, lessons, critic, workspace, sites, control, knowledge, trust, decisions, autonomy, initiatives, board, costs, models as models_module
from src.office import planning_engine, execution
from src.core import llm
from src.agents import researcher, strategist, orchestrator, architect, leaders
from src.agents import agent_factory
from src.saas import context as ctx
from src.saas import store as saas_store

# Анти-цикл: подпись последнего решения лидера и счётчик повторов (per tenant+dept).
_last_leader_sig: dict[str, tuple[str, int]] = {}
_LEADER_REPEAT_LIMIT = 3  # столько одинаковых решений подряд → пауза/эскалация

LOOP_INTERVAL = int(os.getenv("LOOP_INTERVAL_SECONDS", "10"))
MANAGER_POLL = 5          # как часто менеджер ищет новых тенантов для запуска
AGENT_COOLDOWN_SECS = planning_engine.AGENT_COOLDOWN_SECS  # антидребезг живости (Planning Engine)
CEO_REASSESS_EVERY = 3    # CEO пересматривает структуру компании раз в N циклов (экономия токенов)
# Исполнение одной задачи (assign/run_task/watchdog) вынесено в office/execution.py;
# состояние живости и MAX_THINK_SECS/MAX_TASK_ATTEMPTS живут там.
# Потолок одного шага BOOTSTRAP (deep-ресёрч, архитектор): watchdog покрывает только
# циклы, не bootstrap — зависший первый шаг раньше замораживал офис навсегда.
BOOTSTRAP_STEP_TIMEOUT = int(os.getenv("BOOTSTRAP_STEP_TIMEOUT", "900"))

# Состояние по тенантам (шедулер/анонсы; живость исполнения — в execution.py)
_first_cycle_done: dict[str, bool] = {} # tid -> прошёл ли первый цикл
_office_tasks: dict[str, asyncio.Task] = {}


_completion_announced: dict[str, bool] = {}  # tid -> объявлено ли «цель достигнута»


def wake_tenant() -> None:
    """Внешний сигнал (новая директива предпринимателя из чата): снимаем флаг
    «цель достигнута», чтобы офис, ушедший в режим мониторинга, переоценил работу
    и подхватил новые задачи/этапы в ближайшем цикле."""
    _completion_announced.pop(ctx.get_tenant(), None)


def forget_tenant(tid: str) -> None:
    """Полный сброс тенанта (reset «новый клиент»): гасим его офис-задачу и чистим
    per-tenant живость в памяти процесса. Без этого /api/brief/reset стирал файлы,
    но СТАРАЯ задача офиса продолжала крутиться со стейтом в RAM (стратегия, цикл),
    реанимировала данные и жгла токены, а менеджер не запускал офис заново, пока
    задача жива. Уже стартовавшие _job-корутины агентов дорабатывают и гаснут сами
    (их таймауты ≤ CALL_TIMEOUT/ask_user)."""
    task = _office_tasks.pop(tid, None)
    if task and not task.done():
        task.cancel()
    execution.forget_tenant(tid)  # живость исполнения (thinking/agent_task/model_fail/current_ms)
    prefix = f"{tid}:"
    for k in [k for k in _last_leader_sig
              if k.startswith(prefix) or k.startswith(f"board:{tid}:")]:
        _last_leader_sig.pop(k, None)
    for d2 in (_first_cycle_done, _completion_announced):
        d2.pop(tid, None)


def _engagement_complete() -> bool:
    """Все задачи доски выполнены → цель клиента достигнута (надёжнее бизнес-этапов).
    Если появилась новая задача (делегирование/указание) — сбрасываем флаг анонса."""
    if not plan.is_generated():
        return False
    p = plan.progress()
    # done + skipped: пропущенные (роль без отдела) закрывают план, но не считаются
    # «выполненными» — прогресс не врёт, а офис не виснет на неисполнимой задаче.
    complete = p["total"] > 0 and (p["done"] + p.get("skipped", 0)) >= p["total"]
    if not complete:
        _completion_announced.pop(ctx.get_tenant(), None)  # появилась работа — снова активны
    return complete


def _strategy_text() -> str:
    f = ctx.tenant_dir() / "strategy.md"
    return f.read_text(encoding="utf-8") if f.exists() else ""


def _goal() -> str:
    """Осмысленная цель компании — источник теперь в брифе (brief.effective_goal)."""
    return brief.effective_goal()


def _save_strategy(strategy: str) -> None:
    (ctx.tenant_dir() / "strategy.md").write_text(strategy, encoding="utf-8")


# ============================================================
# МЕНЕДЖЕР: запускает офис для каждого тенанта с готовым брифом
# ============================================================
async def run() -> None:
    while True:
        try:
            # Тенанты-воркспейсы + «default» (анонимный/демо) — иначе у демо-юзера
            # офис НИКОГДА не запускается и любые задачи/указания из чата не исполняются.
            tids = [ws["id"] for ws in saas_store.all_workspaces()]
            if "default" not in tids:
                tids.append("default")
            for tid in tids:
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

    # «Это рестарт?» смотрим ДО _hire_initial: он сам публикует hired-события, которые
    # попадают в state.saved_agents() — из-за этого СВЕЖИЙ офис всегда выглядел как
    # «восстановленный» и первый цикл уходил на ветку рестарта с сообщением
    # «Офис восстановлен» сразу после онбординга.
    had_saved_agents = bool(state.saved_agents())
    await _hire_initial(publish)
    _first_cycle_done[tid] = not had_saved_agents

    # ---- BOOTSTRAP ----
    strategy = _strategy_text()
    if strategy:
        milestones.set_status("research", "done")
        milestones.set_status("strategy", "done")
    else:
        strategy = await _bootstrap(publish)

    tech_design = architect.load()
    if not tech_design:
        goal = _goal()
        await publish({"type": "system", "text": "Архитектор проектирует техническое решение..."})
        try:
            # Архитектор тоже ищет в вебе (use_search=True) — bootstrap не под watchdog,
            # поэтому шаг ограничен по времени так же, как ресёрчер.
            tech_design = await asyncio.wait_for(architect.run_async(strategy, goal, publish),
                                                 timeout=BOOTSTRAP_STEP_TIMEOUT)
        except Exception as e:
            await publish({"type": "error", "agent_id": "architect_1", "text": str(e)[:100]})

    if not milestones.has_business_stages():
        goal = _goal()
        stages = await orchestrator.plan_milestones(strategy, goal, publish)
        milestones.set_business_stages(stages)
        await publish({"type": "system", "text": f"Директор разбил путь к цели на {len(stages)} этапов"})

    # Граф конкретных задач (роль + зависимости + критерий) — для маршрутизации и параллелизма.
    # КРИТИЧНО: офис должен быть plan-driven ВСЕГДА. Если LLM-генерация плана недоступна
    # (слабая модель, 429-rate-limit, битый JSON) — берём детерминированный фолбэк-план,
    # иначе автономный слой (доска/завершение/маршрутизация) обходится и офис ходит кругами.
    if not plan.is_generated():
        goal = _goal()
        tasks = []
        try:
            tasks = await orchestrator.plan_tasks(strategy, goal, tech_design, publish)
        except Exception as e:
            await publish({"type": "error", "agent_id": "orchestrator_1", "text": str(e)[:100]})
        if not tasks:
            tasks = planning_engine.fallback_plan(goal)
            await publish({"type": "system",
                           "text": "📋 План собран по умолчанию (LLM-генерация недоступна)"})
        plan.set_tasks(tasks)
        await publish({"type": "system",
                       "text": f"📋 Составлен план: {len(plan.all_tasks())} задач"})

    # Project: задачи всегда принадлежат проекту (BOS §1). Для тенантов, начавших
    # до появления сущности, — разовая миграция задач-сирот в активный проект.
    from src.office import projects
    proj = projects.ensure_active()
    adopted = plan.adopt_orphan_tasks(proj["id"])
    if adopted:
        await publish({"type": "system",
                       "text": f"📁 Задачи привязаны к проекту «{proj['title'][:50]}» ({adopted})"})

    # Specification (Acceptance L1): контракт приёмки из брифа + плана — что делаем
    # и когда это успех. Не блокирует старт; владелец может подтвердить через API/UI.
    from src.office import specification
    if not specification.exists():
        spec = specification.ensure()
        if spec.get("functions"):
            await publish({"type": "system",
                           "text": f"📜 Спецификация сформирована: {len(spec['functions'])} "
                                   f"пунктов, {len(spec.get('success_criteria', []))} критериев "
                                   f"успеха — см. «Проект»"})

    # Capability-гейт (Execution Policy, BOS §6): каких способностей не хватает под
    # план — владелец узнаёт о недостающих доступах СРАЗУ, а не когда исполнитель
    # упрётся в середине задачи. Не блокирует: событие CEO + сообщение в ленту.
    from src.office import execution_policy, events as events_mod2
    for miss in execution_policy.missing_for_plan():
        hint = (miss.get("acquire") or {}).get("hint", "")
        label = miss.get("label", miss.get("capability", ""))
        events_mod2.raise_event(
            "problem",
            f"Для способности «{label}» нет доступа ({miss['capability']})",
            detail=f"Нужно: {hint}", from_role="orchestrator")
        await publish({"type": "system",
                       "text": f"🔌 Понадобится способность «{label}»: {hint} — "
                               f"подключите заранее в «Доступы», чтобы команда не ждала"})

    # ---- ЦИКЛЫ ----
    cycle = 0
    while True:
        cycle += 1

        # Проверка паузы — пользователь или quota-стоп
        if control.is_paused():
            await asyncio.sleep(max(LOOP_INTERVAL * 3, 30))
            continue

        # Бюджетный лимит из Конституции: превышен общий лимит расхода → авто-пауза.
        if costs.over_limit():
            control.pause("Достигнут лимит расхода — офис на паузе. Повысьте лимит в «Компания → Лимиты».")
            await publish({"type": "system",
                           "text": "⛔ Достигнут бюджетный лимит — офис поставлен на паузу."})
            await asyncio.sleep(max(LOOP_INTERVAL * 3, 30))
            continue

        # Завершение по ДОСКЕ: все задачи плана сделаны → цель клиента достигнута.
        # Это надёжнее «бизнес-этапов» (которые могут содержать недостижимую фантазию
        # вроде «масштабирование до 1М») и не даёт офису ходить кругами после результата.
        if _engagement_complete():
            if not _completion_announced.get(tid):
                # Финальная верификация: проверяем сайт перед объявлением готовности.
                # Если есть незакрытые критические проблемы — добавляем fix-задачу вместо
                # того чтобы молча считать результат принятым.
                await execution.publish_site_auto(publish)
                fix_added = await _verify_and_fix_if_needed(strategy, publish)
                if fix_added:
                    # Задача добавлена — офис продолжит работу, не засыпаем
                    await asyncio.sleep(LOOP_INTERVAL)
                    continue
                # Gap-driven перепланирование (Phase 4, Bootstrapping→Steady State):
                # план выполнен, но измеримая цель не достигнута → офис САМ создаёт
                # следующую работу под конкретный разрыв, а не только «жду указаний».
                from src.office import gap as gap_mod
                gap_tasks = gap_mod.replan()
                if gap_tasks:
                    for gt in gap_tasks:
                        await publish({"type": "system",
                                       "text": f"🎯 Цель ещё не достигнута — офис ставит задачу "
                                               f"под разрыв: {gt['title'][:70]}"})
                    await asyncio.sleep(LOOP_INTERVAL)
                    continue
                _completion_announced[tid] = True
                # ЧЕСТНО: помечаем выполненным только активный этап, НЕ фейкуем будущие.
                for s in milestones.all_stages():
                    if s.get("status") == "active":
                        milestones.set_status(s["id"], "done")
                # Project закрывается с фиксацией «что оставил после себя» (задачи,
                # сайты, лиды + срез мира) — история компании ведётся по проектам.
                from src.office import projects as projects_mod
                closed = projects_mod.close(note="все задачи плана выполнены")
                if closed:
                    lb = closed.get("left_behind") or {}
                    await publish({"type": "system",
                                   "text": f"📁 Проект «{closed['title'][:50]}» закрыт: "
                                           f"{lb.get('tasks_done', 0)} задач, "
                                           f"лидов: {lb.get('leads_count', 0)}"})
                await _set_progress_note("✅ Запланированная работа выполнена. Жду указаний — что делаем дальше.", publish)
                await publish({"type": "system",
                               "text": "✅ Запланированная работа выполнена. Напишите в чат, что делать "
                                       "дальше — команда продолжит. Построить полноценную компанию за один "
                                       "прогон нельзя, поэтому двигаемся итерациями."})
            await asyncio.sleep(max(LOOP_INTERVAL * 6, 60))
            continue
        # Этапы (вехи) — производный ИНДИКАТОР, а не отдельный критерий готовности.
        # Единственный источник правды о завершении — доска задач (_engagement_complete).
        # Раньше этот блок мог объявить «все этапы пройдены» и усыпить офис, пока в плане
        # оставались невыполненные задачи (эвристика mark_active расходилась с доской, A3).
        # Терминальным этапы считаем ТОЛЬКО когда плана-графа нет (редкий фолбэк).
        if not plan.is_generated() and milestones.all_business_done():
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
            # Задача агента может остаться in_progress в плане НАВСЕГДА, если сам агент
            # уже не 'thinking' (idle/done) — она никогда не вернётся в очередь сама
            # (ready_for_department берёт только status=="pending"). Проверяем по ТЕКУЩЕМУ
            # статусу агента, а не только по `reset` этого конкретного рестарта: если
            # сервер перезапускали дважды, при втором разе агент уже был idle и не попал
            # бы в reset — задача осталась бы сиротой навечно (реальный кейс: t3(designer)
            # застряла in_progress → мьютекс на site/ считал designer/developer вечно
            # «занятыми сайтом» и блокировал ВСЮ дальнейшую работу тех-отдела).
            if plan.is_generated():
                for t in plan.all_tasks():
                    if t.get("status") != "in_progress":
                        continue
                    assignee = t.get("assignee") or ""
                    rec = registry.get(assignee) if assignee else None
                    if not rec or rec.status != "thinking":
                        plan.revert(t["id"])
            await publish({"type": "system",
                           "text": "Офис восстановлен. Директор продолжит управление в следующем цикле."})
            await asyncio.sleep(LOOP_INTERVAL)
            continue
        await execution.heal_stuck_agents(publish)  # самолечение: сбросить зависших
        if not planning_engine.has_actionable_move():
            await asyncio.sleep(LOOP_INTERVAL)
            continue
        await publish({"type": "system", "text": f"=== Рабочий цикл #{cycle} ==="})
        tech_design = architect.load()
        try:
            await _orchestrate(strategy, publish, tech_design=tech_design, cycle=cycle)
        except Exception as e:
            err_str = str(e)
            import traceback
            if llm.is_quota_error(err_str):
                reason = "⛔ Недостаточно баланса у LLM-провайдера. Пополните счёт и нажмите «Возобновить»."
                control.pause(reason)
                await publish({"type": "system", "text": reason})
            else:
                await publish({"type": "error", "agent_id": "orchestrator_1",
                               "text": f"Сбой цикла: {err_str[:150]}"})
                traceback.print_exc()
        await asyncio.sleep(LOOP_INTERVAL)




async def _verify_and_fix_if_needed(strategy: str, publish) -> bool:
    """Финальная верификация: если сайт есть и у него критические проблемы —
    добавляем fix-задачу на доску вместо того чтобы объявить работу готовой.
    Возвращает True если задача добавлена (офис продолжит работу)."""
    problems = critic.check_site()
    # Критические (не косметические) проблемы — единый критерий с приёмкой задачи.
    critical = [p for p in problems if critic.is_critical(p)]
    if not critical:
        return False
    # Дедуп по НЕзакрытым fix-задачам. Раньше считались и done-задачи: после ОДНОЙ
    # выполненной доработки новая fix-задача не создавалась никогда, и офис объявлял
    # «работа выполнена» с оставшимися критическими проблемами. Теперь done не глушит
    # новую попытку; blocked глушит (ждём владельца, не плодим дубли) — бесконечный
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
    goal = _goal()
    ms = milestones.all_stages()

    # ---- Висячие задачи: роль без отдела (analyst/researcher/неизвестная) не обслуживается
    # отделами → авто-закрываем, чтобы офис не завис на недостижимой задаче и мог завершиться.
    if plan.is_generated() and planning_engine.has_orphan_tasks():
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
        await _apply_company_decision(company, publish)

    # ---- Блок 4: Инициативы из opportunity-событий ----
    # CEO превращает наблюдённые возможности отделов в конкретные предложения
    # с ROI-оценкой. Пользователь видит карточку и принимает или отклоняет.
    try:
        from src.office import events as events_mod
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
                await publish({"type": "initiative", "id": iid, "title": ini["title"],
                               "expected_outcome": ini.get("expected_outcome", "")})
                await publish({"type": "speech", "agent_id": "orchestrator_1",
                               "text": f"💡 Новая инициатива: {ini['title']} → {ini.get('expected_outcome','')[:60]}"})
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
        await _hire_leader("tech", obj, publish)
        await publish({"type": "system", "text": "📂 Открыт «Технический отдел» (автостарт)"})

    # ---- Параллелизм: открываем ВСЕ отделы, которых требует план задач ----
    # (независимые ветки плана исполняются параллельно — как в реальной компании).
    for dept_id in plan.departments_needed():
        if dept_id not in org.open_departments():
            obj = (goal or "")[:140]
            org.open_department(dept_id, reason="нужен по плану задач", objective=obj)
            await _hire_leader(dept_id, obj, publish)
            await publish({"type": "system",
                           "text": f"📂 Открыт «{org.catalog()[dept_id]['name']}» (по плану задач)"})

    # ---- Лидер-тир — по каждому открытому отделу с возможным ходом ----
    await _run_leaders(goal, ms, publish)


async def _apply_company_decision(decision: dict, publish) -> None:
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
        if not lead or not planning_engine.dept_actionable(dept_id, now):
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
            # 1) Назначаем первую готовую задачу, под которую есть свободный работник.
            for t in ready:
                free = planning_engine.free_worker_of_role(dept_id, t.get("role", ""), now)
                if free:
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
                    handled = True
                    break
            if handled:
                continue
            # 2) Никто не свободен — нанимаем недостающую роль под готовую задачу.
            present = {a.role for a in registry.members_of(dept_id)}
            for t in ready:
                role = t.get("role", "")
                if role in member_roles and role not in present:
                    crit = f"\n✅ ЗАДАЧА ВЫПОЛНЕНА, КОГДА: {t['done_criterion']}" if t.get("done_criterion") else ""
                    await _hire_and_run(role, t.get("title", f"Задачи {role}") + crit,
                                        publish, department=dept_id, manager=lead, task_id=t["id"])
                    handled = True
                    break
            # 3) Все нужные роли есть, но заняты — детерминированный wait без LLM.
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
                await execution.assign(agent_id, rec.role, task, publish, department=dept_id, objective=objective)












async def _bootstrap(publish) -> str:
    # «Понимание компании» теперь влияет на поведение, а не только на индикатор (B4):
    # при очень низком score офис честно предупреждает, что работает с неполным брифом,
    # и приглашает клиента добавить контекст (не блокирует — просто снижает риск мимо цели).
    try:
        from src.office import understanding
        score = understanding.payload().get("score", 100)
        if score < 30:
            await publish({"type": "system",
                           "text": f"ℹ️ Понимание бизнеса пока низкое ({score}/100) — офис стартует "
                                   f"с неполным брифом. Опишите бизнес и цель в чате CEO, чтобы "
                                   f"результат точнее попал в задачу."})
    except Exception:
        pass
    await publish({"type": "system", "text": "=== BOOTSTRAP: исследуем нишу клиента ==="})
    milestones.mark_active("research")
    await _set_progress_note("Исследуем рынок и тренды", publish)

    question = brief.research_question() or researcher.DEFAULT_QUESTION
    try:
        research = await asyncio.wait_for(researcher.deep(question, publish=publish),
                                          timeout=BOOTSTRAP_STEP_TIMEOUT)
    except asyncio.TimeoutError:
        await publish({"type": "system", "agent_id": "researcher_1",
                       "text": f"⏱ Исследование не уложилось в {BOOTSTRAP_STEP_TIMEOUT // 60} мин — "
                               f"продолжаю по брифу без глубокого ресёрча"})
        research = ""
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
                        department: str = "", manager: str = "", task_id: str = "") -> None:
    existing_count = sum(1 for a in registry.all_agents() if a.role == role)
    agent_id = f"{role}_{existing_count + 1}"
    full_task = f"[Скилл: {skill}] {task}" if skill else task
    rec = registry.register(agent_id, role, full_task, department=department, manager=manager)
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


async def _hire_initial(publish) -> None:
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
                await publish({
                    "type": "hired", "agent_id": aid, "role": role, "desk": rec.desk, "task": rec.task,
                })
