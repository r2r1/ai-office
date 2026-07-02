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
from src.agents import researcher, strategist, orchestrator, architect, leaders
from src.agents import agent_factory
from src.saas import context as ctx
from src.saas import store as saas_store

# Анти-цикл: подпись последнего решения лидера и счётчик повторов (per tenant+dept).
_last_leader_sig: dict[str, tuple[str, int]] = {}
_LEADER_REPEAT_LIMIT = 3  # столько одинаковых решений подряд → пауза/эскалация

LOOP_INTERVAL = int(os.getenv("LOOP_INTERVAL_SECONDS", "10"))
MANAGER_POLL = 5          # как часто менеджер ищет новых тенантов для запуска
AGENT_COOLDOWN_SECS = int(os.getenv("AGENT_COOLDOWN_SECS", "25"))  # антидребезг (живость)
CEO_REASSESS_EVERY = 3    # CEO пересматривает структуру компании раз в N циклов (экономия токенов)
MAX_THINK_SECS = int(os.getenv("AGENT_MAX_THINK_SECS", "240"))  # дольше → считаем зависшим

# Состояние по тенантам
_current_ms: dict[str, str] = {}        # tid -> id текущего этапа
_first_cycle_done: dict[str, bool] = {} # tid -> прошёл ли первый цикл
_office_tasks: dict[str, asyncio.Task] = {}
# ⚠️ Ключ этих словарей — «tenant:agent_id», НЕ голый agent_id: agent_id одинаковы у
# всех тенантов («developer_1»), и без префикса тенанта параллельные офисы затирали бы
# состояние друг друга (watchdog/задача/счётчик модели). См. _tk() и _heal_stuck_agents.
_thinking_since: dict[str, float] = {}  # tenant:agent_id -> когда начал «думать» (watchdog)
_agent_task: dict[str, str] = {}        # tenant:agent_id -> id задачи плана, которую он делает
_model_fail_count: dict[str, int] = {}  # tenant:agent_id -> подряд ошибок "модель недоступна"


def _tk(agent_id: str) -> str:
    """Ключ per-tenant для словарей живости: изолирует одноимённых агентов разных тенантов."""
    return f"{ctx.get_tenant()}:{agent_id}"
_completion_announced: dict[str, bool] = {}  # tid -> объявлено ли «цель достигнута»


def wake_tenant() -> None:
    """Внешний сигнал (новая директива предпринимателя из чата): снимаем флаг
    «цель достигнута», чтобы офис, ушедший в режим мониторинга, переоценил работу
    и подхватил новые задачи/этапы в ближайшем цикле."""
    _completion_announced.pop(ctx.get_tenant(), None)


def _fallback_plan(goal: str) -> list[dict]:
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
    # сайт/лендинг — основной кейс
    return [
        {"id": "t1", "title": "Подготовить оффер и продающие тексты для всех блоков лендинга",
         "role": "marketer", "deps": [], "done_criterion": "готов копирайт: оффер, выгоды, FAQ, CTA"},
        {"id": "t2", "title": "Собрать конверсионный многостраничный лендинг в site/ с формой заявки",
         "role": "designer", "deps": ["t1"],
         "done_criterion": "site/index.html + страницы опубликованы, форма шлёт на /api/site-lead"},
        {"id": "t3", "title": "Проверить формы/CTA и довести лендинг до рабочего состояния",
         "role": "developer", "deps": ["t2"], "done_criterion": "формы работают, сайт опубликован и собирает лиды"},
    ]


def _engagement_complete() -> bool:
    """Все задачи доски выполнены → цель клиента достигнута (надёжнее бизнес-этапов).
    Если появилась новая задача (делегирование/указание) — сбрасываем флаг анонса."""
    if not plan.is_generated():
        return False
    p = plan.progress()
    complete = p["total"] > 0 and p["done"] >= p["total"]
    if not complete:
        _completion_announced.pop(ctx.get_tenant(), None)  # появилась работа — снова активны
    return complete


def _cur_ms() -> str:
    return _current_ms.get(ctx.get_tenant(), "")


def _set_cur_ms(v: str) -> None:
    _current_ms[ctx.get_tenant()] = v


def _strategy_text() -> str:
    f = ctx.tenant_dir() / "strategy.md"
    return f.read_text(encoding="utf-8") if f.exists() else ""


_JUNK_GOALS = {"не знаю", "незнаю", "не знаю.", "-", "—", "нет", "хз", "?", ""}


def _goal() -> str:
    """
    Осмысленная цель компании для промптов. Клиент в онбординге может ответить
    «не знаю» — тогда «Цель компании: не знаю» замусоривала КАЖДЫЙ промпт, хотя
    стратег уже сформулировал реальную цель. Мусорная цель → берём её из стратегии.
    """
    g = (brief.get().get("goal") or "").strip()
    if g.lower() not in _JUNK_GOALS:
        return g
    # Первая содержательная строка стратегии обычно и есть сформулированная цель.
    for line in _strategy_text().splitlines():
        line = line.strip().lstrip("#*-1234567890. ").strip()
        if line.lower().startswith("цель"):
            return line[:200]
    return brief.summary() or "разобраться в нише и предложить первый результат"


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

    await _hire_initial(publish)
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
        goal = _goal()
        await publish({"type": "system", "text": "Архитектор проектирует техническое решение..."})
        try:
            tech_design = await architect.run_async(strategy, goal, publish)
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
            tasks = _fallback_plan(goal)
            await publish({"type": "system",
                           "text": "📋 План собран по умолчанию (LLM-генерация недоступна)"})
        plan.set_tasks(tasks)
        await publish({"type": "system",
                       "text": f"📋 Составлен план: {len(plan.all_tasks())} задач"})

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
                await _publish_site_auto(publish)
                fix_added = await _verify_and_fix_if_needed(strategy, publish)
                if fix_added:
                    # Задача добавлена — офис продолжит работу, не засыпаем
                    await asyncio.sleep(LOOP_INTERVAL)
                    continue
                _completion_announced[tid] = True
                # ЧЕСТНО: помечаем выполненным только активный этап, НЕ фейкуем будущие.
                for s in milestones.all_stages():
                    if s.get("status") == "active":
                        milestones.set_status(s["id"], "done")
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
            await publish({"type": "system",
                           "text": "Офис восстановлен. Директор продолжит управление в следующем цикле."})
            await asyncio.sleep(LOOP_INTERVAL)
            continue
        await _heal_stuck_agents(publish)  # самолечение: сбросить зависших
        if not _has_actionable_move():
            await asyncio.sleep(LOOP_INTERVAL)
            continue
        await publish({"type": "system", "text": f"=== Рабочий цикл #{cycle} ==="})
        tech_design = architect.load()
        try:
            await _orchestrate(strategy, publish, tech_design=tech_design, cycle=cycle)
        except Exception as e:
            err_str = str(e)
            import traceback
            if _is_quota_error(err_str):
                reason = "⛔ Недостаточно баланса у LLM-провайдера. Пополните счёт и нажмите «Возобновить»."
                control.pause(reason)
                await publish({"type": "system", "text": reason})
            else:
                await publish({"type": "error", "agent_id": "orchestrator_1",
                               "text": f"Сбой цикла: {err_str[:150]}"})
                traceback.print_exc()
        await asyncio.sleep(LOOP_INTERVAL)


async def _heal_stuck_agents(publish) -> None:
    """
    Самолечение: агент «думает» дольше MAX_THINK_SECS — его задача зависла
    (модель не ответила/застряла). Сбрасываем в idle, чтобы лидер переназначил.
    """
    now = time.time()
    prefix = f"{ctx.get_tenant()}:"  # только агенты ТЕКУЩЕГО тенанта, не чужие
    for key, since in list(_thinking_since.items()):
        if not key.startswith(prefix):
            continue
        aid = key[len(prefix):]
        if now - since > MAX_THINK_SECS:
            _thinking_since.pop(key, None)
            registry.update_status(aid, "idle")
            state.save_last_run(aid)  # короткий cooldown перед повтором
            tid = _agent_task.pop(key, None)
            if tid and plan.is_generated():
                # АНТИЦИКЛ: если завис дизайнер/разработчик, но сайт УЖЕ написан —
                # не гоняем задачу по кругу заново. Публикуем что есть и принимаем задачу.
                # ВАЖНО: принимаем ТОЛЬКО если index.html менялся ПОСЛЕ старта ЭТОЙ задачи —
                # иначе watchdog закрывал чужой работой задачи, которых агент даже не начал
                # делать (index.html существовал с ранних задач), а реальный результат агента
                # приходил позже и создавал двойные правки (реальный кейс из прода).
                rec = registry.get(aid)
                site_touched = False
                sdir = critic.site_dir()
                if sdir is not None:
                    idx = workspace.resolve(f"{sdir}/index.html" if sdir else "index.html")
                    try:
                        site_touched = idx is not None and idx.is_file() and idx.stat().st_mtime >= since
                    except OSError:
                        site_touched = False
                if rec and rec.role in ("designer", "developer") and site_touched:
                    await _publish_site_auto(publish)
                    plan.complete(tid)
                    await publish({"type": "system",
                                   "text": f"✅ {aid} долго думал, но сайт уже готов — задача {tid} "
                                           f"принята и опубликована (без перезапуска)."})
                    continue
                plan.revert(tid)  # иначе — вернуть зависшую задачу в очередь
            # Trust Score: зависший агент снижает доверие к его отделу
            rec_stuck = registry.get(aid)
            if rec_stuck and rec_stuck.department:
                trust.record_stuck(rec_stuck.department)
            await publish({"type": "system",
                           "text": f"🔧 {aid} завис (> {MAX_THINK_SECS}s) — сброшен, задача переназначится"})


async def _verify_and_fix_if_needed(strategy: str, publish) -> bool:
    """Финальная верификация: если сайт есть и у него критические проблемы —
    добавляем fix-задачу на доску вместо того чтобы объявить работу готовой.
    Возвращает True если задача добавлена (офис продолжит работу)."""
    problems = critic.check_site()
    # Критические (не косметические) проблемы — единый критерий с приёмкой задачи.
    critical = [p for p in problems if critic.is_critical(p)]
    if not critical:
        return False
    # Смотрим, не добавляли ли уже аналогичную fix-задачу
    existing_titles = {t.get("title", "").lower() for t in plan.all_tasks()}
    fix_title = "Исправить критические проблемы сайта: " + "; ".join(critical[:2])[:120]
    if any("исправить критические" in t for t in existing_titles):
        return False  # уже есть, не дублируем
    await publish({"type": "system",
                   "text": f"🔍 Финальная проверка нашла проблемы: {'; '.join(critical[:2])[:100]} — "
                           "добавляю задачу на исправление"})
    fix_task = {
        "id": f"fix_{int(__import__('time').time())}",
        "title": fix_title,
        "role": "developer",
        "deps": [],
        "done_criterion": "форма шлёт на /api/site-lead, сайт открывается без ошибок",
        "status": "pending",
    }
    plan.add_task(fix_task["title"], fix_task["role"], fix_task["done_criterion"],
                  requested_by="orchestrator_1")
    return True


async def _publish_site_auto(publish, note: str = "") -> bool:
    """
    Авто-публикация сайта офисом: как только в site/ есть index.html — публикуем сами,
    не дожидаясь, пока агент вызовет publish_site (он часто забывает/обрывается на
    длинном выводе). «Написал HTML → сайт сразу живой».

    `note` — краткое «что изменилось» в этой правке (из отчёта агента). Идёт в журнал
    ревизий сайта и в сообщение, чтобы каждая публикация читалась как понятная правка.
    """
    sdir = critic.site_dir()
    if sdir is None:
        return False

    # Блок 2: Если уровень автономности требует разрешения перед публикацией — спрашиваем
    # БЛОКИРУЮЩЕ через personal-thread CEO (как делает agent_factory.ask_user).
    # Но только ПЕРВЫЙ раз за офис: видели в проде 5+ повторных «опубликовать?» за один
    # прогон, когда критик несколько раз подряд просил мелкие правки одного и того же
    # сайта — это шум, не новое решение. Разрешение один раз — action одобрен на весь
    # офис (сбрасывается вместе с ним/паузой).
    tid = ctx.get_tenant()
    if autonomy.needs_approval("publish_site"):
        from src.office import questions as questions_mod, threads as threads_mod
        question_text = "Сайт готов к публикации. Опубликовать сейчас? (да/нет)"
        # Дедуп: если такой вопрос уже висит — не плодим повторно
        pending = [m for m in questions_mod.list_pending() if m.get("text") == question_text]
        if pending:
            return False
        qid, fut = questions_mod.ask(question_text, publish, agent_id="orchestrator_1")
        threads_mod.post("orchestrator_1", "orchestrator", question_text,
                         kind="question", question_id=qid)
        await publish({"type": "agent_message", "agent_id": "orchestrator_1", "from": "agent",
                       "kind": "question", "question_id": qid, "text": question_text})
        await publish({"type": "system",
                       "text": f"🔐 Сайт готов — ожидаю разрешения в чате с CEO (уровень: {autonomy.get_level()})"})
        try:
            answer = await asyncio.wait_for(fut, timeout=600)
        except asyncio.TimeoutError:
            questions_mod.answer(qid, "")
            threads_mod.mark_answered(qid)
            await publish({"type": "system",
                           "text": "⌛ Клиент не ответил по публикации — оставляю на согласовании"})
            return False
        threads_mod.mark_answered(qid)
        await publish({"type": "question_answered", "question_id": qid, "agent_id": "orchestrator_1"})
        ok = (answer or "").strip().lower()
        if ok and not any(no in ok for no in ("нет", "no", "стоп", "поз")):
            # Положительный ответ → больше не спрашиваем повторно за этот офис,
            # и повышаем доверие (клиент дал OK)
            autonomy.mark_action_approved("publish_site")
            from src.office import decisions as decisions_mod
            decisions_mod.record(
                action="publish_site", target=f"site (после OK клиента)",
                thought="Клиент одобрил публикацию",
                alternatives=[], confidence=95, risks=[],
                expected_effect="Лендинг живой, форма собирает заявки",
                data_used=["user_approval"], made_by="orchestrator_1",
            )
        else:
            await publish({"type": "system",
                           "text": "⛔ Публикация отклонена клиентом — продолжаю доработку"})
            return False

    tid = ctx.get_tenant()
    title = (brief.get().get("goal", "") or "Сайт")[:60]
    slug = sites.main_slug()  # СТАБИЛЬНЫЙ адрес: одна ссылка на весь прогон, не плодим сайты
    site = sites.save_dir(title, sdir, slug, note=note)
    rev = site.get("revision", 1)
    from src.office import trace
    trace.log("publish", slug=slug, rev=rev, dir=sdir, note=(note or "")[:120])
    if rev <= 1:
        msg = f"🌐 Сайт опубликован: /site/{tid}/{slug} — форма собирает заявки в «Лиды»"
    else:
        tail = f" — {note[:90]}" if note else ""
        msg = f"🌐 Сайт обновлён (правка {rev}): /site/{tid}/{slug}{tail}"
    await publish({"type": "system", "text": msg})
    return True


def _dept_actionable(dept_id: str, now: float) -> bool:
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
        if a.status != "thinking" and not on_cooldown:
            return True
    existing = {a.role for a in members}
    return any(r not in existing for r in worker_roles)


def _has_actionable_move() -> bool:
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
        if _has_orphan_tasks():
            return True
    now = time.time()
    return any(_dept_actionable(did, now) for did in open_depts)


def _has_orphan_tasks() -> bool:
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
    if plan.is_generated() and _has_orphan_tasks():
        servable = set()
        for did in org.catalog():
            servable |= set(org.member_roles(did))
        for t in plan.all_tasks():
            if t.get("status") in ("pending", "in_progress") and not t.get("department") \
                    and t.get("role") not in servable:
                plan.complete(t["id"])
                await publish({"type": "system",
                               "text": f"⏭ Задача {t['id']} ({t.get('role','?')}) пропущена — "
                                       f"роль не входит в отделы, не блокирует сдачу"})

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


def _free_worker_of_role(dept_id: str, role: str, now: float):
    """Свободный (idle, не в cooldown) работник нужной роли в отделе — или None."""
    for a in registry.members_of(dept_id):
        if a.role != role or a.status == "thinking":
            continue
        if (now - state.last_run_for(a.agent_id)) < AGENT_COOLDOWN_SECS:
            continue
        return a
    return None


async def _run_leaders(goal: str, ms: list, publish) -> None:
    now = time.time()
    for dept_id in org.open_departments():
        lead = org.lead_id(dept_id)
        if not lead or not _dept_actionable(dept_id, now):
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
                free = _free_worker_of_role(dept_id, t.get("role", ""), now)
                if free:
                    task_txt = t.get("title", "")
                    if t.get("done_criterion"):
                        task_txt += f"\n✅ ЗАДАЧА ВЫПОЛНЕНА, КОГДА: {t['done_criterion']}"
                    plan.assign(t["id"], free.agent_id)  # доска: взято в работу
                    _agent_task[_tk(free.agent_id)] = t["id"]
                    await _assign(free.agent_id, free.role, task_txt, publish,
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
                await _assign(agent_id, rec.role, task, publish, department=dept_id, objective=objective)


def _is_model_unavailable_error(err: str) -> bool:
    """Модель/канал недоступен у провайдера (не транзиентная ошибка сети/таймаута) —
    например ручное или expert-назначение указывает на несуществующий на шлюзе id.
    Отличается от quota-ошибки: тут нужно сменить модель, а не остановить офис."""
    low = err.lower()
    return "model_not_found" in low or "no available channel" in low


def _is_quota_error(err: str) -> bool:
    """Определяет ошибку нехватки баланса у LLM-провайдера."""
    low = err.lower()
    return (
        "insufficient" in low or "额度不足" in err or "余额不足" in err
        or ("403" in err and ("quota" in low or "balance" in low or "额度" in err or "余额" in err))
        or "预扣费" in err
    )


async def _assign(agent_id: str, role: str, task: str, publish, skill: str = "",
                  department: str = "", objective: str = "", task_id: str = "") -> None:
    await publish({"type": "speech", "agent_id": "orchestrator_1",
                   "text": f"→ Поручаю {agent_id}: {task[:70]}"})
    from src.office import trace
    trace.log("assign", to=agent_id, role=role, dept=department,
              task_id=task_id, task=task[:160])
    # СИНХРОННО помечаем занятость ДО планирования _job: иначе между _assign и реальным
    # стартом корутины (create_task выполняется позже) следующий проход цикла видел
    # работника ещё idle и мог назначить ему вторую задачу той же роли (двойной ассайн).
    registry.update_status(agent_id, "thinking")
    _thinking_since[_tk(agent_id)] = time.time()

    async def _job():
        registry.update_status(agent_id, "thinking")
        _thinking_since[_tk(agent_id)] = time.time()
        _job_t0 = time.time()
        trace.log("agent_start", agent=agent_id, role=role,
                  model=models_module.for_agent(agent_id), skill=skill or "")
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
                # ---- Приёмка качества (критик) для сайтов: дизайнер/разработчик ----
                if role in ("designer", "developer"):
                    await _review_and_maybe_fix(role, agent_id, task, skill, department,
                                                objective, publish, result=result or "")
            registry.update_status(agent_id, "done")
            state.save_last_run(agent_id)
            trace.log("agent_done", agent=agent_id, role=role,
                      sec=round(time.time() - _job_t0, 1), out_len=len(result or ""),
                      task_id=task_id)
            _model_fail_count.pop(_tk(agent_id), None)  # успех — счётчик сбитой модели сбрасываем
            _attribute_result(agent_id, role, result)
            # Память отдела: фиксируем, что отдел сделал — пригодится коллегам в след. циклах
            knowledge.note_result(department, role, result or "")
            # Доска: закрываем ИМЕННО эту задачу (а не «первую по роли»).
            # ПУСТАЯ сдача задачу НЕ закрывает: агент вернул пустой результат (обрыв/
            # только tool-calls) — возвращаем в очередь, иначе фиктивное «выполнено»
            # (реальный кейс: integrator сдал пустоту, t3 закрылась).
            if task_id and plan.is_generated():
                if (result or "").strip():
                    plan.complete(task_id)
                    await publish({"type": "system", "text": f"✅ Задача {task_id} выполнена"})
                else:
                    plan.revert(task_id)
                    await publish({"type": "system",
                                   "text": f"↩️ {agent_id} вернул пустой результат — "
                                           f"задача {task_id} возвращена в очередь"})
            # Trust Score: успешная задача повышает доверие к отделу
            if department:
                trust.record_success(department)
                # Предложение повысить уровень автономности при высоком доверии
                if trust.should_propose_upgrade():
                    trust.mark_upgrade_proposed()
                    proposal = trust.upgrade_proposal_text()
                    if proposal:
                        # Actionable-предложение: событие несёт next_level, чтобы UI показал
                        # кнопку «Повысить» (POST /api/autonomy/upgrade), а не просто текст (B3).
                        nl = autonomy.next_level()
                        await publish({"type": "autonomy_upgrade_offer", "agent_id": "orchestrator_1",
                                       "next_level": nl, "text": f"🤝 {proposal}"})
            # Живость: «сделал → отчитался» — короткий итог в ленту.
            summary = (result or "").strip().replace("\n", " ")[:120]
            if summary:
                await publish({"type": "speech", "agent_id": agent_id, "text": f"✅ Готово: {summary}"})
        except Exception as e:
            err_str = str(e)
            trace.log("agent_error", agent=agent_id, role=role,
                      sec=round(time.time() - _job_t0, 1), error=err_str[:200])
            await publish({"type": "error", "agent_id": agent_id, "text": err_str[:100]})
            registry.update_status(agent_id, "idle")
            if task_id and plan.is_generated():
                plan.revert(task_id)  # упала — вернуть в очередь
            # Trust Score: провал задачи снижает доверие
            if department:
                trust.record_failure(department)
            # Quota/billing 403 → ставим офис на паузу, чтобы не сжигать остаток
            if _is_quota_error(err_str):
                reason = "⛔ Недостаточно баланса у LLM-провайдера. Пополните счёт и нажмите «Возобновить»."
                control.pause(reason)
                await publish({"type": "system", "text": reason})
            elif _is_model_unavailable_error(err_str):
                # Самолечение: назначенная модель недоступна у провайдера. Одной ошибки
                # не трогаем (может быть временный глюк шлюза) — но повтор той же ошибки
                # для того же агента означает, что это НЕ пройдёт само, и без вмешательства
                # офис повторял бы один и тот же провальный вызов бесконечно (было в проде).
                n = _model_fail_count.get(_tk(agent_id), 0) + 1
                _model_fail_count[_tk(agent_id)] = n
                if n >= 2:
                    cleared = models_module.clear_broken_model(agent_id, role)
                    _model_fail_count.pop(_tk(agent_id), None)
                    if cleared:
                        await publish({"type": "system",
                                       "text": f"⚙️ Модель «{cleared}» для {agent_id} недоступна у "
                                               f"провайдера — сброшена на модель офиса по умолчанию, "
                                               f"задача будет повторена."})
                    else:
                        await publish({"type": "system",
                                       "text": f"⚠️ {agent_id} не может получить ответ модели — "
                                               f"похоже, недоступна сама модель офиса по умолчанию. "
                                               f"Проверьте «Компания → Интеллект»."})
            else:
                _model_fail_count.pop(_tk(agent_id), None)
        finally:
            _thinking_since.pop(_tk(agent_id), None)
            _agent_task.pop(_tk(agent_id), None)

    asyncio.create_task(_job())


def _engagement_needs_bot() -> bool:
    """Нужен ли этому клиенту вообще Telegram-бот. Проверяем цель/бриф/план, а не
    факт наличия bot.py — иначе случайно созданный агентом bot.py заставлял критик
    требовать «почини бота» на чисто сайтовом проекте (реальный баг из прода)."""
    b = brief.get()
    hay = " ".join(str(b.get(k, "")) for k in ("goal", "summary", "niche")).lower()
    if any(w in hay for w in ("бот", "bot", "telegram", "телеграм")):
        return True
    try:
        for t in plan.all_tasks():
            if any(w in (t.get("title", "").lower()) for w in ("бот", "bot", "telegram", "телеграм")):
                return True
    except Exception:
        pass
    return False


async def _review_and_maybe_fix(role: str, agent_id: str, task: str, skill: str,
                                department: str, objective: str, publish,
                                result: str = "") -> None:
    """
    Приёмка результата сайта: программные проверки → при проблемах ОДНА доработка.
    Уроки сохраняются в память, выполненная задача плана отмечается готовой.

    `result` — отчёт агента о том, ЧТО он сделал: используется как «что изменилось»
    в журнале ревизий сайта (понятная правка вместо «новый сайт»).
    """
    from src.office import trace
    task_l = (task or "").lower()
    files = [f["path"] for f in workspace.list_files()]
    note = (result or "").strip().replace("\n", " ")[:160]

    # --- Верификация Python-кода ---
    py_files = [p for p in files if p.endswith(".py")]
    if py_files:
        py_problems = critic.check_python_files()
        if py_problems:
            for p in py_problems:
                lessons.add(role, f"Код: {p}")
            feedback = "⚠ Синтаксические ошибки в коде:\n" + "\n".join(f"- {p}" for p in py_problems[:3])
            await publish({"type": "speech", "agent_id": agent_id, "text": feedback[:200]})
            fix_task = (f"{task}\n\n{feedback}\n\nИсправь ошибки в файлах. "
                        f"Прочитай файл через read_file, найди ошибку, перепиши через write_file.")
            ctx_task = _task_with_context(role, fix_task, skill, department=department, objective=objective)
            fn = agent_factory.create(role, ctx_task, agent_id, publish, skill=skill)
            await fn()

    # --- Верификация Telegram-бота ---
    # ВАЖНО: бот-проверку запускаем ТОЛЬКО если бот реально в задаче/цели клиента.
    # Раньше триггером был сам факт наличия bot.py, и случайно созданный агентом файл
    # уводил сайтовый проект в бесконечную «починку бота» (баг из лога прода).
    bot_related = any(w in task_l for w in ("бот", "bot", "telegram", "телеграм"))
    if (bot_related or _engagement_needs_bot()) and any(p in ("bot.py", "main.py") for p in files):
        bot_problems = critic.check_bot()
        if bot_problems:
            for p in bot_problems:
                lessons.add(role, f"Бот: {p}")
            feedback = critic.critique_text_bot(bot_problems)
            await publish({"type": "speech", "agent_id": agent_id,
                           "text": f"🔁 Бот проверен — нужны правки: {feedback[:120]}"})
            fix_task = (f"{task}\n\n{feedback}\n\n"
                        f"Прочитай существующие файлы через list_files + read_file, исправь проблемы.")
            ctx_task = _task_with_context(role, fix_task, skill, department=department, objective=objective)
            fn = agent_factory.create(role, ctx_task, agent_id, publish, skill=skill)
            await fn()
        return  # бот-задача обработана

    site_related = any(w in task_l for w in ("сайт", "лендинг", "landing", "site", "страниц"))
    has_index = any(p == "index.html" or p.endswith("/index.html") for p in files)
    if not (site_related or has_index):
        return  # не сайтовая задача — критик не применим (задачу закроет _job)

    # Сайт всегда публикуем САМИ — не ждём, пока агент вызовет publish_site
    # (он часто забывает или обрывается на длинном выводе). Сайт сразу живой.
    await _publish_site_auto(publish, note=note)

    # Приёмка = программные проверки + ЗРЯЧАЯ проверка в браузере + LLM-оценка результата.
    goal = _goal()
    problems = critic.check_site()
    try:
        problems = problems + await critic.review_site_visual()   # рендер в headless-браузере
    except Exception:
        pass
    try:
        problems = problems + await critic.review_site_llm(goal)
    except Exception:
        pass
    trace.log("critic", agent=agent_id, phase="site", problems=len(problems),
              detail=("; ".join(problems)[:200] if problems else "ok"))
    if not problems:
        return  # сайт принят (задачу плана закроет _job по task_id)

    # Есть проблемы — сохраняем урок и даём РОВНО ОДНУ доработку, потом ДВИГАЕМСЯ дальше
    # (никаких бесконечных переприёмок — это и есть «затуп»). Задачу закроет _job.
    for p in problems:
        lessons.add(role, f"Сайт: {p}")
    feedback = critic.critique_text(problems)
    await publish({"type": "speech", "agent_id": agent_id, "text": f"🔁 {feedback[:120]}"})
    # Инкрементальная правка с обязательным журналом изменений: агент чинит ТОЧЕЧНО
    # существующие файлы (не переписывает сайт заново) и отчитывается, ЧТО поменял.
    fix_task = (f"{task}\n\n{feedback}\n\n"
                f"ЭТО ПРАВКА существующего сайта, НЕ новый сайт:\n"
                f"1. Сначала read_file для каждого файла, который правишь.\n"
                f"2. Меняй ТОЧЕЧНО только нужное, остальное сохрани как есть — НЕ начинай с нуля, "
                f"НЕ сокращай сайт, НЕ выкидывай готовые секции.\n"
                f"3. Публиковать НЕ нужно — офис опубликует сам.\n"
                f"4. В конце ответа ОДНОЙ строкой: «Изменения: …» — что именно поправил.")
    ctx_task = _task_with_context(role, fix_task, skill, department=department, objective=objective)
    fn = agent_factory.create(role, ctx_task, agent_id, publish, skill=skill)
    fix_result = await fn()
    fix_note = (fix_result or "").strip().replace("\n", " ")
    # Берём строку «Изменения: …», если агент её дал — это и есть человекочитаемая правка.
    import re as _re
    m = _re.search(r"Изменени[яе]\s*:\s*(.+)", fix_note)
    fix_note = (m.group(1) if m else fix_note)[:160]
    await _publish_site_auto(publish, note=fix_note or "правки по замечаниям критика")

    # ПОВТОРНАЯ проверка после правки: раньше задача принималась безусловно, даже если
    # правка не помогла — офис сдавал заведомо битый сайт (напр. форма не шлёт лиды).
    # Одна ДОП. попытка на КРИТИЧЕСКИЕ проблемы; если и она не помогла — не молчим,
    # а честно предупреждаем клиента. Задачу всё равно закрываем, чтобы не зациклиться.
    remaining = critic.check_site()
    critical = [p for p in remaining if critic.is_critical(p)]
    trace.log("critic", agent=agent_id, phase="site_recheck",
              problems=len(remaining), critical=len(critical))
    if critical:
        feedback2 = critic.critique_text(critical)
        fix_task2 = (f"{task}\n\nОСТАЛИСЬ КРИТИЧЕСКИЕ ПРОБЛЕМЫ:\n{feedback2}\n\n"
                     f"Почини ТОЧЕЧНО в существующих файлах site/ (read_file → правка), "
                     f"публиковать не нужно. В конце строкой «Изменения: …».")
        ctx_task2 = _task_with_context(role, fix_task2, skill, department=department, objective=objective)
        r2 = await agent_factory.create(role, ctx_task2, agent_id, publish, skill=skill)()
        n2 = (r2 or "").strip().replace("\n", " ")
        m2 = _re.search(r"Изменени[яе]\s*:\s*(.+)", n2)
        await _publish_site_auto(publish, note=(m2.group(1) if m2 else "повторная правка")[:160])
        still = [p for p in critic.check_site() if critic.is_critical(p)]
        if still:
            # Честно: не выдаём битый результат за готовый — просим клиента вмешаться.
            warn = "; ".join(still[:2])[:200]
            await publish({"type": "system",
                           "text": f"⚠️ Сайт сдан, но осталась нерешённая проблема: {warn}. "
                                   f"Нужна ваша правка или уточнение в чате — команда доработает."})
            trace.log("critic", agent=agent_id, phase="site_unresolved", detail=warn)


def _task_with_context(role: str, task: str, skill: str = "",
                       department: str = "", objective: str = "") -> str:
    goal = _goal()
    # «Цель» из брифа — это ответ клиента на «какой результат вы хотите ОТ ОФИСА» (см.
    # onboarding.py), а не описание того, ЧТО продаёт бизнес клиента. Раньше в промпт шло
    # только "Цель компании: {goal}" — и когда goal был буквально «упаковка бизнеса»,
    # marketer/designer собрали сайт, который ПРОДАЁТ «упаковку бизнеса» владельцам квартир
    # (реальный кейс: клиент делает натяжные потолки, просил упаковать СВОЙ бизнес, а не
    # продавать услугу упаковки конечным клиентам). Явно разводим: что продаёт компания
    # (niche/audience из брифа) — отдельно от цели ЭТОГО прогона офиса.
    b = brief.get()
    niche = (b.get("niche") or "").strip()
    audience = (b.get("audience") or "").strip()
    biz_line = ""
    if niche:
        biz_line += f"Бизнес клиента — ЧТО он продаёт конечным покупателям: {niche}\n"
    if audience:
        biz_line += f"Аудитория бизнеса — КОМУ он продаёт: {audience}\n"
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
    tdd_section = f"\n=== ТЕХНИЧЕСКОЕ ЗАДАНИЕ АРХИТЕКТОРА (кратко) ===\n{tdd[:3000]}\n" if tdd else ""
    lessons_section = lessons.context_block(role)  # память: уроки прошлых задач этой роли
    # Трёхслойная память: подбираем релевантные ИМЕННО этой задаче факты
    # (ограничения клиента, его ответы, что отдел уже сделал).
    knowledge_section = knowledge.context_block(task, department=department)
    return (
        f"{biz_line}Цель ЭТОГО прогона офиса (что должен сделать офис для клиента — "
        f"НЕ то, что продаёт компания конечным покупателям): {goal}\n{stage}{dept_line}{skill_line}"
        f"Твоя задача от руководителя: {task}\n"
        f"{tdd_section}{knowledge_section}{lessons_section}\n"
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
            _agent_task[_tk(agent_id)] = task_id
        await _assign(agent_id, role, task, publish, skill=skill,
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
