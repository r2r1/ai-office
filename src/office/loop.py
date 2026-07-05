"""
Автономный офис — мультиарендный менеджер и главный шедулер.

`run()` опрашивает тенантов (workspaces) и для каждого, у кого есть готовый бриф,
запускает СВОЙ офис-цикл (`_run_office`) в отдельной задаче с установленным
контекстом тенанта. Внутри одного тенанта логика прежняя: BOOTSTRAP (ресёрчер →
стратег → архитектор → этапы), затем циклы директора.

Контекст тенанта (`ctx.set_tenant`) ставится в начале офис-задачи и автоматически
наследуется дочерними задачами (`asyncio.create_task` копирует contextvars).

Расслоение (Phase 6, docs/дорожная_карта.md): loop.py — тонкий шедулер, остальное
вынесено в отдельные подсистемы BOS §12:
  - `office/bootstrap.py`     — единоразовый запуск тенанта (наём CEO/штаба, ресёрч→стратегия)
  - `office/planning_engine.py` — планирование, маршрутизация, CEO-оркестрация
  - `office/execution.py`     — жизненный цикл исполнения одной задачи (watchdog, приёмка)
loop импортирует все три (одностороннее направление) — никто из них не импортирует loop.
"""

import asyncio
import os
import time

from src.office import bus, registry, brief, state, milestones, plan, control, costs
from src.office import planning_engine, execution, bootstrap
from src.core import llm
from src.agents import orchestrator, architect
from src.saas import context as ctx
from src.saas import store as saas_store

LOOP_INTERVAL = int(os.getenv("LOOP_INTERVAL_SECONDS", "10"))
MANAGER_POLL = 5          # как часто менеджер ищет новых тенантов для запуска
# Как часто повторять «жду разблокировки X», пока офис простаивает из-за блокера —
# не на каждом цикле (10с), иначе спам; не никогда (было реальным багом: офис молча
# замирал навсегда, пока владелец не додумывался открыть «Проект → Задачи» сам).
BLOCKED_HEARTBEAT_SECS = int(os.getenv("BLOCKED_HEARTBEAT_SECS", "600"))
# Маршрутизация/CEO-оркестрация — в planning_engine.py; исполнение задачи (watchdog,
# состояние живости, MAX_THINK_SECS/MAX_TASK_ATTEMPTS) — в execution.py; bootstrap
# (ресёрч→стратегия, BOOTSTRAP_STEP_TIMEOUT) — в bootstrap.py.

# Состояние шедулера по тенантам (кто запущен/объявлено ли завершение — не смешивать
# с состоянием живости исполнения (execution.py) и анти-циклом маршрутизации (planning_engine.py)).
_first_cycle_done: dict[str, bool] = {} # tid -> прошёл ли первый цикл
_office_tasks: dict[str, asyncio.Task] = {}
_completion_announced: dict[str, bool] = {}  # tid -> объявлено ли «цель достигнута»
_last_blocked_heartbeat: dict[str, float] = {}  # tid -> ts последнего напоминания о блокере
_net_fail_streak: dict[str, int] = {}   # tid -> подряд идущих сетевых сбоев цикла
# Сколько сетевых сбоев подряд терпим до авто-паузы: одиночный таймаут — норма
# (ретрай цикла), но серия означает лежащий прокси/сеть — без паузы офис спамил
# одинаковыми трейсбеками каждые 10с часами (реальный прогон: ConnectTimeout
# на локальный прокси 127.0.0.1:10809, десятки идентичных стектрейсов).
NET_FAIL_PAUSE_AFTER = int(os.getenv("NET_FAIL_PAUSE_AFTER", "3"))


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
    задача жива. Уже стартовавшие корутины исполнения дорабатывают и гаснут сами
    (их таймауты ≤ CALL_TIMEOUT/ask_user)."""
    task = _office_tasks.pop(tid, None)
    if task and not task.done():
        task.cancel()
    execution.forget_tenant(tid)       # живость исполнения (thinking/agent_task/model_fail/current_ms)
    planning_engine.forget_tenant(tid)  # анти-цикл маршрутизации (_last_leader_sig)
    for d2 in (_first_cycle_done, _completion_announced, _last_blocked_heartbeat):
        d2.pop(tid, None)


async def _heartbeat_if_blocked(publish) -> None:
    """Пока has_actionable_move()==False (офису реально нечего делать) и есть
    заблокированные задачи — периодически напоминаем владельцу, а не молчим
    навсегда (реальный прод-инцидент: офис остановился без единого сообщения,
    владелец решил, что всё зависло, хотя система корректно ждала его решения
    по BOS §10 — просто никак об этом не сообщала после первого уведомления).
    Не зовёт LLM — чистое чтение доски + троттлинг по времени, $0."""
    if not plan.is_generated():
        return
    blocked = plan.blocked_tasks()
    if not blocked:
        return
    tid = ctx.get_tenant()
    now = time.time()
    last = _last_blocked_heartbeat.get(tid, 0.0)
    if now - last < BLOCKED_HEARTBEAT_SECS:
        return
    _last_blocked_heartbeat[tid] = now
    titles = "; ".join(f"«{t.get('title','')[:60]}»" for t in blocked[:3])
    more = f" и ещё {len(blocked) - 3}" if len(blocked) > 3 else ""
    await publish({"type": "system",
                   "text": f"⏸ Офис ждёт вашего решения по {len(blocked)} заблокированной(ым) "
                           f"задаче(ам){more}: {titles}. Другой работы сейчас нет — "
                           f"разблокируйте во вкладке «Проект → Задачи», чтобы продолжить."})


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


async def _set_progress_note(note: str, publish) -> None:
    payload = milestones.progress_payload()
    payload["note"] = note
    await publish({"type": "progress", **payload})


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

    # «Это рестарт?» смотрим ДО bootstrap.hire_initial: он сам публикует hired-события,
    # которые попадают в state.saved_agents() — из-за этого СВЕЖИЙ офис всегда выглядел
    # как «восстановленный» и первый цикл уходил на ветку рестарта с сообщением
    # «Офис восстановлен» сразу после онбординга.
    had_saved_agents = bool(state.saved_agents())
    await bootstrap.hire_initial(publish)
    _first_cycle_done[tid] = not had_saved_agents

    # ---- BOOTSTRAP ----
    strategy = bootstrap.strategy_text()
    if strategy:
        milestones.set_status("research", "done")
        milestones.set_status("strategy", "done")
    else:
        strategy = await bootstrap.run(publish)

    tech_design = architect.load()
    if not tech_design:
        goal = brief.effective_goal()
        await publish({"type": "system", "text": "Архитектор проектирует техническое решение..."})
        try:
            # Архитектор тоже ищет в вебе (use_search=True) — bootstrap не под watchdog,
            # поэтому шаг ограничен по времени так же, как ресёрчер.
            tech_design = await asyncio.wait_for(architect.run_async(strategy, goal, publish),
                                                 timeout=bootstrap.BOOTSTRAP_STEP_TIMEOUT)
        except Exception as e:
            await publish({"type": "error", "agent_id": "architect_1", "text": str(e)[:100]})

    if not milestones.has_business_stages():
        goal = brief.effective_goal()
        stages = await orchestrator.plan_milestones(strategy, goal, publish)
        milestones.set_business_stages(stages)
        await publish({"type": "system", "text": f"Директор разбил путь к цели на {len(stages)} этапов"})

    # Граф конкретных задач (роль + зависимости + критерий) — для маршрутизации и параллелизма.
    # КРИТИЧНО: офис должен быть plan-driven ВСЕГДА. Если LLM-генерация плана недоступна
    # (слабая модель, 429-rate-limit, битый JSON) — берём детерминированный фолбэк-план,
    # иначе автономный слой (доска/завершение/маршрутизация) обходится и офис ходит кругами.
    if not plan.is_generated():
        goal = brief.effective_goal()
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

        # Недожатые лиды (мини-CRM, product-vision.md §3): дешёвая детерминированная
        # проверка без LLM — событие поднимается один раз на пачку, не спамит.
        from src.office import leads as leads_mod
        n_stale = leads_mod.check_stale_events()
        if n_stale:
            await publish({"type": "system",
                           "text": f"🟡 {n_stale} лид(ов) без ответа 72+ часов — см. «Лиды»"})

        # Повторяющиеся процессы (BOS §5: Process — необязательно поток Instance
        # вроде продаж, может быть циклическое действие: «контент-завод»,
        # «ежедневная аналитика рынка»). Работает НЕЗАВИСИМО от того, завершён
        # ли план проекта — Process не подчиняется завершению Project. Дедуп —
        # тот же приём, что gap.replan(): новая задача только когда предыдущая
        # закрыта, иначе один процесс спамил бы задачу каждый цикл.
        from src.office import processes as processes_mod
        proc_tasks = processes_mod.tick()
        for pt in proc_tasks:
            await publish({"type": "system", "text": f"🔄 Процесс поставил задачу: {pt['title'][:70]}"})

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
                fix_added = await planning_engine.verify_and_fix_if_needed(publish)
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
                # Здесь план ГЕНУИННО завершён (_engagement_complete уже true) — в
                # отличие от промежуточных циклов, где фейковое авто-завершение будущих
                # этапов маскирует несделанную работу (тест A3), здесь домысливать
                # нечего: все задачи доски реально сделаны, а бизнес-этапы (LLM-generated,
                # milestone_done CEO ведёт по своей дискреции и часто не успевает пройти
                # их все явно — реальный кейс: designer/developer закрыли t3/t4, но
                # этапы "Дизайн и визуалы"/"Разработка" остались pending навсегда) обязаны
                # отражать это состояние, а не застревать как незавершённые в UI.
                for s in milestones.all_stages():
                    if s.get("status") != "done":
                        milestones.set_status(s["id"], "done")
                # BOS §5: ДО закрытия проекта — CEO решает сам, разовый ли это
                # результат или на самом деле непрерывный цикл (Process). Смотрим
                # ПОКА проект ещё активен (задачи ещё принадлежат ему, до close()).
                from src.office import processes as processes_mod
                from src.office import projects as projects_mod_peek
                active_proj = projects_mod_peek.active()
                if active_proj:
                    tasks_summary = "\n".join(f"- {t['title']} ({t.get('role','')})"
                                               for t in plan.for_project(active_proj["id"])[:15])
                    try:
                        cls = await orchestrator.classify_recurring(
                            active_proj["title"], active_proj.get("goal", ""), tasks_summary)
                    except Exception:
                        cls = {}
                    if cls.get("recurring") and cls.get("title") and cls.get("instruction"):
                        proc = processes_mod.create(
                            cls["title"], cls.get("role", "marketer"), cls["instruction"])
                        await publish({"type": "system",
                                       "text": f"🔄 Офис решил: «{active_proj['title'][:40]}» — это непрерывный "
                                               f"цикл, запускаю процесс «{proc['title']}»"})

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
            await _heartbeat_if_blocked(publish)
            await asyncio.sleep(LOOP_INTERVAL)
            continue
        await publish({"type": "system", "text": f"=== Рабочий цикл #{cycle} ==="})
        tech_design = architect.load()
        try:
            await planning_engine.orchestrate(strategy, publish, tech_design=tech_design, cycle=cycle)
        except Exception as e:
            err_str = str(e).strip() or type(e).__name__
            import traceback
            if llm.is_quota_error(err_str):
                reason = "⛔ Недостаточно баланса у LLM-провайдера. Пополните счёт и нажмите «Возобновить»."
                control.pause(reason)
                await publish({"type": "system", "text": reason})
            elif llm.is_network_error(err_str):
                # Серия сетевых сбоев подряд = сеть/прокси до провайдера лежит.
                # Пауза с понятной причиной вместо бесконечного спама трейсбеков.
                n = _net_fail_streak.get(tid, 0) + 1
                _net_fail_streak[tid] = n
                if n >= NET_FAIL_PAUSE_AFTER:
                    reason = ("⛔ Нет связи с LLM-провайдером (таймауты подряд). Проверьте "
                              "интернет/прокси и нажмите «Возобновить».")
                    control.pause(reason)
                    await publish({"type": "system", "text": reason})
                    _net_fail_streak.pop(tid, None)
                else:
                    await publish({"type": "error", "agent_id": "orchestrator_1",
                                   "text": f"Сетевой сбой ({n}/{NET_FAIL_PAUSE_AFTER}): {err_str[:100]}"})
            else:
                await publish({"type": "error", "agent_id": "orchestrator_1",
                               "text": f"Сбой цикла: {err_str[:150]}"})
                traceback.print_exc()
        else:
            _net_fail_streak.pop(tid, None)  # успешный цикл сбрасывает серию
        await asyncio.sleep(LOOP_INTERVAL)
