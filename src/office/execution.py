"""
Execution — жизненный цикл исполнения задачи как отдельная подсистема (BOS §12).

Расслоение loop.py (Phase 6): всё, что относится к ИСПОЛНЕНИЮ одной задачи, вынесено
из бог-модуля цикла в отдельную машину состояний:

  assign()              — взять задачу в работу (статус, живость, старт корутины)
  run_task()            — Policy → бюджетный гейт → run_agent → приёмка → эскалация
  heal_stuck_agents()   — watchdog: сброс зависших агентов (делит состояние живости)
  review_and_maybe_fix()— приёмка сайта/бота критиком + одна доработка
  publish_site_auto()   — авто-публикация сайта офисом
  task_with_context()   — обёртка prompt_builder.task_context
  attribute_result()    — вклад результата в текущий этап

Модуль ВЛАДЕЕТ состоянием живости в памяти процесса (watchdog/атрибуция) — это
признанный долг SSOT (BOS §13: вынос живости в мир — после пятёрки ядра); здесь оно
хотя бы сосредоточено в одном месте, а не размазано по циклу. loop импортирует
execution (одностороннее направление), execution НЕ импортирует loop.
"""

import asyncio
import os
import time

from src.core import llm
from src.office import (registry, state, plan, costs, control, knowledge, lessons,
                        trust, autonomy, critic, workspace, sites, brief, milestones,
                        models as models_module, needs)
from src.agents import researcher, strategist, agent_factory
from src.saas import context as ctx

MAX_THINK_SECS = int(os.getenv("AGENT_MAX_THINK_SECS", "240"))  # дольше → считаем зависшим
MAX_TASK_ATTEMPTS = 3  # провалов приёмки до блокировки задачи (эскалация вместо цикла)

# ── Состояние живости в памяти процесса (ключ «tenant:agent_id», не голый id) ──
_thinking_since: dict[str, float] = {}   # когда агент начал «думать» (watchdog)
_agent_task: dict[str, str] = {}         # какую задачу плана он делает
_agent_coro: dict[str, asyncio.Task] = {}  # корутина run_task — для отмены зомби watchdog'ом
_model_fail_count: dict[str, int] = {}   # подряд ошибок «модель недоступна»
_current_ms: dict[str, str] = {}         # tid -> id текущего этапа (для атрибуции результата)


def tk(agent_id: str) -> str:
    """Ключ живости: agent_id одинаков у всех тенантов («developer_1») — без префикса
    тенанта параллельные офисы затирали бы состояние друг друга."""
    return f"{ctx.get_tenant()}:{agent_id}"


def current_task_id(agent_id: str) -> str:
    """id задачи, над которой агент работает СЕЙЧАС (или "") — публичный доступ
    к _agent_task для инструментов вне этого модуля (например note_progress,
    comms_tool_handlers.py), не лезущих в приватное состояние напрямую."""
    return _agent_task.get(tk(agent_id), "")


def cur_ms() -> str:
    return _current_ms.get(ctx.get_tenant(), "")


def set_cur_ms(v: str) -> None:
    _current_ms[ctx.get_tenant()] = v


def reconcile_after_restart() -> list[str]:
    """Сверяет `registry.json` (переживает рестарт — файл на диске) с живостью
    ТЕКУЩЕГО процесса (`_thinking_since` — только память, обнуляется на рестарте).

    Реальный найденный баг: если сервер перезапускается (reload при правке кода,
    краш, обновление) ровно когда агент был в статусе "thinking", запись на диске
    остаётся "thinking" навсегда — НОВЫЙ процесс никогда не заводил для него таймер
    в _thinking_since, поэтому heal_stuck_agents() (обычный watchdog по таймауту)
    никогда его не увидит и не сбросит. При MAX_PER_ROLE=1 роль (developer/
    marketer/sales_lead/...) остаётся занятой навсегда — застревал не один агент,
    а весь отдел, и офис выглядел полностью зависшим клиенту. Зомби-корутина в
    ЭТОМ случае в принципе не может существовать (процесс, где она жила, уже
    мёртв) — поэтому, в отличие от heal_stuck_agents, сбрасываем СРАЗУ при
    старте цикла, без ожидания MAX_THINK_SECS: ждать нечего, эта работа гарантированно
    потеряна вместе со старым процессом.

    Вызывается ОДИН раз в начале _run_office(tid), ДО первого цикла — pending-вопросы
    (ask_user) не считаются зависанием (агент может легитимно ждать клиента с прошлого
    запуска), эти статусы не трогаем."""
    from src.office import questions as questions_mod
    if questions_mod.list_pending():
        return []
    prefix = f"{ctx.get_tenant()}:"
    healed: list[str] = []
    for rec in registry.all_agents():
        if rec.status != "thinking":
            continue
        key = prefix + rec.agent_id
        if key in _thinking_since:
            continue  # реально живая задача в ЭТОМ процессе — не трогаем
        registry.update_status(rec.agent_id, "idle")
        if plan.is_generated():
            for t in plan.all_tasks():
                if t.get("status") == "in_progress" and t.get("assignee") == rec.agent_id:
                    plan.revert(t["id"])
        healed.append(rec.agent_id)
    return healed


def forget_tenant(tid: str) -> None:
    """Чистит per-tenant живость этого модуля (вызывается loop.forget_tenant)."""
    prefix = f"{tid}:"
    for d in (_thinking_since, _agent_task, _model_fail_count):
        for k in [k for k in d if k.startswith(prefix)]:
            d.pop(k, None)
    for k in [k for k in _agent_coro if k.startswith(prefix)]:
        t = _agent_coro.pop(k, None)
        if t and not t.done():
            t.cancel()
    _current_ms.pop(tid, None)


def touch(agent_id: str) -> None:
    """Отметка «агент реально работает» — вызывается из llm.run_agent после каждого
    ответа API/инструмента (through agent_factory). Без неё watchdog считал ДОЛГУЮ
    законную работу (цепочка правок сайта > MAX_THINK_SECS суммарно) зависанием,
    сбрасывал агента и переназначал задачу — при живой старой корутине это давало
    ДВУХ исполнителей, параллельно переписывающих site/ (реальный прод-кейс)."""
    key = tk(agent_id)
    if key in _thinking_since:
        _thinking_since[key] = time.time()


def engagement_needs_bot() -> bool:
    """Нужен ли этому клиенту вообще Telegram-бот. Проверяем цель/бриф/план, а не
    факт наличия bot.py — иначе случайно созданный агентом bot.py заставлял критик
    требовать «почини бота» на чисто сайтовом проекте (реальный баг из прода)."""
    b = brief.get()
    hay = " ".join(str(b.get(k, "")) for k in ("goal", "summary", "niche"))
    if needs.is_bot_reference(hay):
        return True
    try:
        for t in plan.all_tasks():
            if needs.is_bot_reference(t.get("title", "")):
                return True
    except Exception:
        pass
    return False


def task_with_context(role: str, task: str, skill: str = "",
                      department: str = "", objective: str = "",
                      touches_site: bool = True, task_id: str = "") -> str:
    """Контекст задачи собирает Prompt Builder — единая точка сборки промптов
    (docs/bos-architecture.md §7). Обёртка сохранена для читаемости вызовов.
    `touches_site` по умолчанию True — вызовы из фикс-цикла критика (см. call
    sites выше) всегда реально про сайт; единственный вызов, который считает
    его явно (run_task выше) — обычное исполнение задачи плана.
    `task_id` — прокидывается в progress_note (см. plan.set_progress_note/
    prompt_builder.task_context: заметка «что уже сделано» переживает
    переназначение той же задачи)."""
    from src.office import prompt_builder
    return prompt_builder.task_context(role, task, skill,
                                       department=department, objective=objective,
                                       touches_site=touches_site, task_id=task_id)


def attribute_result(agent_id: str, role: str, result: str) -> None:
    if not result or role in ("orchestrator", "hr"):
        return
    cur = cur_ms()
    if cur and milestones.get(cur):
        milestones.add_item(cur, result[:200], agent_id, role)


async def publish_site_auto(publish, note: str = "") -> bool:
    """
    Авто-публикация сайта офисом: как только в site/ есть index.html — публикуем сами,
    не дожидаясь, пока агент вызовет publish_site (он часто забывает/обрывается на
    длинном выводе). «Написал HTML → сайт сразу живой».

    `note` — краткое «что изменилось» в этой правке (из отчёта агента). Идёт в журнал
    ревизий сайта и в сообщение, чтобы каждая публикация читалась как понятная правка.
    """
    # Проект со сборкой (package.json+build): сначала собираем — публикуется ВЫХОД
    # сборки (dist/), не исходники. Кеш по отпечатку исходников: без изменений —
    # мгновенный no-op, npm не запускается. Провал сборки → сайт не публикуем,
    # исполнитель получит лог через критика/приёмку (site_builder.cached_problem).
    from src.office import site_builder
    built = await site_builder.ensure_built(publish)
    if built.get("kind") == "build" and not built.get("ok"):
        return False
    sdir = critic.site_dir()
    if sdir is None:
        return False

    # Форензик-аудит 2026-07-18 («Кухни на заказ КМВ»): сайт был опубликован с
    # автоподобранной палитрой (design_style.ensure_style_line — детерминированный
    # фолбэк, если marketer/designer пропустили шаг подтверждения владельцем,
    # builtin_skills/brand_book.md шаг 4), хотя черновик бренд-бука с вариантами
    # УЖЕ существовал. Публикация не сверялась с этим фактом вообще. Это НЕ то же
    # самое, что общий гейт autonomy.needs_approval("publish_site") ниже — тот
    # можно один раз пройти навсегда за весь офис (см. mark_action_approved),
    # а вопрос стиля специфичен для КАЖДОГО набора кандидатов и не должен
    # проскакивать вместе с общим разрешением на публикацию.
    from src.office import design_style
    style_content = workspace.read_file("docs/site_content.md")
    if design_style.is_auto_picked(style_content):
        from src.office import questions as questions_mod, threads as threads_mod
        question_text = ("Стиль сайта подобран автоматически (владелец не выбирал направление) — "
                          "опубликовать как есть, или сначала показать варианты на выбор?")
        pending = [m for m in questions_mod.list_pending() if m.get("text") == question_text]
        if pending:
            return False
        qid, fut = questions_mod.ask(question_text, publish, agent_id="orchestrator_1")
        threads_mod.post("orchestrator_1", "orchestrator", question_text,
                         kind="question", question_id=qid)
        await publish({"type": "agent_message", "agent_id": "orchestrator_1", "from": "agent",
                       "kind": "question", "question_id": qid, "text": question_text})
        await publish({"type": "system",
                       "text": "🎨 Стиль сайта не подтверждён владельцем — жду ответа перед публикацией"})
        try:
            answer = await asyncio.wait_for(fut, timeout=600)
        except asyncio.TimeoutError:
            questions_mod.answer(qid, "")
            threads_mod.mark_answered(qid)
            await publish({"type": "system",
                           "text": "⌛ Клиент не ответил про стиль — публикацию откладываю"})
            return False
        threads_mod.mark_answered(qid)
        await publish({"type": "question_answered", "question_id": qid, "agent_id": "orchestrator_1"})
        ok = (answer or "").strip().lower()
        if not ok or any(no in ok for no in ("нет", "no", "стоп", "поз", "вариант", "покаж")):
            await publish({"type": "system",
                           "text": "⛔ Публикация с автостилем отклонена — жду выбор направления"})
            return False
        # Явное "опубликовать как есть" — снимаем автометку, чтобы вопрос не
        # повторялся на каждой следующей ревизии этого же сайта.
        cleaned = style_content.replace(" — направление подобрано автоматически (маркетинг не указал явно)", "")
        workspace.write_file("docs/site_content.md", cleaned)

    # Блок 2: Если уровень автономности требует разрешения перед публикацией — спрашиваем
    # БЛОКИРУЮЩЕ через personal-thread CEO (как делает agent_factory.ask_user).
    # Но только ПЕРВЫЙ раз за офис: видели в проде 5+ повторных «опубликовать?» за один
    # прогон, когда критик несколько раз подряд просил мелкие правки одного и того же
    # сайта — это шум, не новое решение. Разрешение один раз — action одобрен на весь
    # офис (сбрасывается вместе с ним/паузой).
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
    # Слаг ТЕКУЩЕГО проекта (Фаза 3, параллельные проекты) — стабильный адрес
    # на весь прогон ЭТОГО проекта, но не общий на все параллельные проекты
    # тенанта (иначе публикация проекта B перезаписывает адрес проекта A).
    slug = sites.slug_for_current_project()
    site = sites.save_dir(title, sdir, slug, note=note)
    rev = site.get("revision", 1)
    from src.office import trace
    trace.log("publish", slug=slug, rev=rev, dir=sdir, note=(note or "")[:120])
    if rev <= 1:
        # Measurement (Phase 3b): первая публикация — появляется измеримая цель
        # «Заявки в неделю» с реальной метрикой (leads за 7 дней) и снимок метрик.
        from src.office import objectives as objectives_mod, metrics as metrics_mod
        obj = objectives_mod.ensure_leads_objective()
        metrics_mod.collect()
        if obj:
            await publish({"type": "system",
                           "text": "🎯 Появилась измеримая цель «Заявки в неделю» — "
                                   "офис начал считать результат сайта"})
        msg = f"🌐 Сайт опубликован: /site/{tid}/{slug} — форма собирает заявки в «Лиды»"
    else:
        tail = f" — {note[:90]}" if note else ""
        msg = f"🌐 Сайт обновлён (правка {rev}): /site/{tid}/{slug}{tail}"
    await publish({"type": "system", "text": msg})
    return True


async def review_and_maybe_fix(role: str, agent_id: str, task: str, skill: str,
                               department: str, objective: str, publish,
                               result: str = "", started_ts: float = 0.0) -> None:
    """
    Приёмка результата сайта: программные проверки → при проблемах ОДНА доработка.
    Уроки сохраняются в память, выполненная задача плана отмечается готовой.

    `result` — отчёт агента о том, ЧТО он сделал: используется как «что изменилось»
    в журнале ревизий сайта (понятная правка вместо «новый сайт»).
    `started_ts` — момент старта задачи: гейт синтаксиса JS/HTML проверяет только
    файлы, тронутые ЭТОЙ задачей (workspace.verify(changed_since=...)).
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
            await publish({"type": "speech", "agent_id": agent_id, "text": feedback})
            fix_task = (f"{task}\n\n{feedback}\n\nИсправь ошибки в файлах. "
                        f"Прочитай файл через read_file, найди ошибку, перепиши через write_file.")
            ctx_task = task_with_context(role, fix_task, skill, department=department, objective=objective)
            fn = agent_factory.create(role, ctx_task, agent_id, publish, skill=skill, title=task)
            await fn()

    # --- Верификация Telegram-бота ---
    # ВАЖНО: бот-проверку запускаем ТОЛЬКО если бот реально в задаче/цели клиента.
    bot_related = needs.is_bot_reference(task_l)
    if (bot_related or engagement_needs_bot()) and any(p in ("bot.py", "main.py") for p in files):
        bot_problems = critic.check_bot()
        if bot_problems:
            for p in bot_problems:
                lessons.add(role, f"Бот: {critic.text_of(p)}")
            feedback = critic.critique_text_bot(bot_problems)
            await publish({"type": "speech", "agent_id": agent_id,
                           "text": f"🔁 Бот проверен — нужны правки: {feedback[:120]}"})
            fix_task = (f"{task}\n\n{feedback}\n\n"
                        f"Прочитай существующие файлы через list_files + read_file, исправь проблемы.")
            ctx_task = task_with_context(role, fix_task, skill, department=department, objective=objective)
            fn = agent_factory.create(role, ctx_task, agent_id, publish, skill=skill, title=task)
            await fn()
        return  # бот-задача обработана

    site_related = any(w in task_l for w in ("сайт", "лендинг", "landing", "site", "страниц"))
    has_index = any(p == "index.html" or p.endswith("/index.html") for p in files)
    if not (site_related or has_index):
        return  # не сайтовая задача — критик не применим (задачу закроет run_task)

    # --- Гейт синтаксиса JS/HTML ДО публикации (реальный прод-баг) ---
    # Раньше сайт публиковался на ЖИВОЙ URL безусловно, а синтаксис JS проверялся
    # только ПОСЛЕ, зрячим headless-браузером (ниже) — реальный кейс: designer на
    # дешёвой модели написал сырой JSX («<div>») вместо React.createElement вопреки
    # явному запрету скилла framer_motion_3d_site.md, site/app.js не парсился
    # браузером («Unexpected token '<'»), а сломанная версия была ЖИВОЙ на публичном
    # URL ~17 минут и несколько циклов правок, пока ошибку не поймал визуальный critic.
    # node --check (workspace.verify) ловит это мгновенно и БЕЗ LLM — гейтим публикацию им.
    v = workspace.verify(changed_since=started_ts)
    if not v.get("ok"):
        for e in v["errors"]:
            lessons.add(role, f"Синтаксис: {e}")
        feedback = ("⚠ Синтаксические ошибки JS/HTML — сайт НЕ публикуется, пока не исправлено:\n"
                    + "\n".join(f"- {e}" for e in v["errors"][:3]))
        await publish({"type": "speech", "agent_id": agent_id, "text": feedback})
        fix_task = (f"{task}\n\n{feedback}\n\nИсправь синтаксис в файлах. "
                    f"Прочитай файл через read_file, найди ошибку, перепиши через write_file.")
        ctx_task = task_with_context(role, fix_task, skill, department=department, objective=objective)
        fn = agent_factory.create(role, ctx_task, agent_id, publish, skill=skill, title=task)
        await fn()
        v = workspace.verify(changed_since=started_ts)
        if not v.get("ok"):
            await publish({"type": "system",
                           "text": "⛔ Сайт НЕ опубликован: остались синтаксические ошибки JS/HTML "
                                   "после попытки правки — команда попробует снова в следующем цикле."})
            return  # НЕ публикуем синтаксически битый код

    # Сайт всегда публикуем САМИ — не ждём, пока агент вызовет publish_site.
    await publish_site_auto(publish, note=note)

    # Приёмка = программные проверки + ЗРЯЧАЯ проверка в браузере + LLM-оценка результата.
    goal = brief.effective_goal()
    b = brief.get()
    niche = (b.get("niche") or "").strip()
    audience = (b.get("audience") or "").strip()
    problems = critic.check_site()
    try:
        problems = problems + await critic.review_site_visual()   # рендер в headless-браузере
    except Exception:
        pass
    try:
        problems = problems + await critic.review_site_llm(goal, niche=niche, audience=audience)
    except Exception:
        pass
    trace.log("critic", agent=agent_id, phase="site", problems=len(problems),
              detail=("; ".join(critic.text_of(p) for p in problems)[:200] if problems else "ok"))
    if not problems:
        return  # сайт принят (задачу плана закроет run_task по task_id)

    # Есть проблемы — сохраняем урок и даём РОВНО ОДНУ доработку, потом ДВИГАЕМСЯ дальше.
    for p in problems:
        lessons.add(role, f"Сайт: {critic.text_of(p)}")
    feedback = critic.critique_text(problems)
    await publish({"type": "speech", "agent_id": agent_id, "text": f"🔁 {feedback}"})
    # Инкрементальная правка с обязательным журналом изменений.
    fix_task = (f"{task}\n\n{feedback}\n\n"
                f"ЭТО ПРАВКА существующего сайта, НЕ новый сайт:\n"
                f"1. Сначала read_file для каждого файла, который правишь.\n"
                f"2. Меняй ТОЧЕЧНО только нужное, остальное сохрани как есть — НЕ начинай с нуля, "
                f"НЕ сокращай сайт, НЕ выкидывай готовые секции.\n"
                f"3. Публиковать НЕ нужно — офис опубликует сам.\n"
                f"4. В конце ответа ОДНОЙ строкой: «Изменения: …» — что именно поправил.")
    ctx_task = task_with_context(role, fix_task, skill, department=department, objective=objective)
    fn = agent_factory.create(role, ctx_task, agent_id, publish, skill=skill, title=task)
    fix_result = await fn()
    fix_note = (fix_result or "").strip().replace("\n", " ")
    import re as _re
    m = _re.search(r"Изменени[яе]\s*:\s*(.+)", fix_note)
    fix_note = (m.group(1) if m else fix_note)[:160]
    await publish_site_auto(publish, note=fix_note or "правки по замечаниям критика")

    # ПОВТОРНАЯ проверка после правки: одна ДОП. попытка на КРИТИЧЕСКИЕ проблемы.
    remaining = critic.check_site()
    critical = [p for p in remaining if critic.is_critical(p)]
    trace.log("critic", agent=agent_id, phase="site_recheck",
              problems=len(remaining), critical=len(critical))
    if critical:
        feedback2 = critic.critique_text(critical)
        fix_task2 = (f"{task}\n\nОСТАЛИСЬ КРИТИЧЕСКИЕ ПРОБЛЕМЫ:\n{feedback2}\n\n"
                     f"Почини ТОЧЕЧНО в существующих файлах site/ (read_file → правка), "
                     f"публиковать не нужно. В конце строкой «Изменения: …».")
        ctx_task2 = task_with_context(role, fix_task2, skill, department=department, objective=objective)
        r2 = await agent_factory.create(role, ctx_task2, agent_id, publish, skill=skill, title=task)()
        n2 = (r2 or "").strip().replace("\n", " ")
        m2 = _re.search(r"Изменени[яе]\s*:\s*(.+)", n2)
        await publish_site_auto(publish, note=(m2.group(1) if m2 else "повторная правка")[:160])
        still = [p for p in critic.check_site() if critic.is_critical(p)]
        if still:
            warn = "; ".join(critic.text_of(p) for p in still[:2])[:200]
            await publish({"type": "system",
                           "text": f"⚠️ Сайт сдан, но осталась нерешённая проблема: {warn}. "
                                   f"Нужна ваша правка или уточнение в чате — команда доработает."})
            trace.log("critic", agent=agent_id, phase="site_unresolved", detail=warn)


async def assign(agent_id: str, role: str, task: str, publish, skill: str = "",
                 department: str = "", objective: str = "", task_id: str = "") -> None:
    """Взять задачу в работу: анонс, статус thinking, привязка живости, старт корутины."""
    # Человекочитаемая роль в сообщении, не сырой agent_id (marketer_p1_45123
    # и т.п.) — владелец бизнеса видел внутренний technical id как часть
    # обычного предложения (найдено при живом дизайн-аудите).
    from src.office import roles as _roles
    role_title = _roles.ROLE_META.get(role, {}).get("title", role)
    await publish({"type": "speech", "agent_id": "orchestrator_1",
                   "text": f"→ Поручаю {role_title}: {task[:70]}"})
    from src.office import trace
    trace.log("assign", to=agent_id, role=role, dept=department,
              task_id=task_id, task=task[:160])
    # СИНХРОННО помечаем занятость ДО планирования корутины: иначе между assign и
    # реальным стартом run_task следующий проход цикла видел работника idle и мог
    # назначить ему вторую задачу той же роли (двойной ассайн).
    registry.update_status(agent_id, "thinking")
    _thinking_since[tk(agent_id)] = time.time()
    if task_id and plan.is_generated():
        _agent_task[tk(agent_id)] = task_id  # раньше ставили call-sites цикла перед assign
    # Хэндл корутины сохраняем: watchdog обязан УБИТЬ зомби при сбросе агента, а не
    # только пометить его idle — иначе старая корутина продолжает писать файлы и
    # закрывать задачи параллельно с новым исполнителем (реальный прод-кейс: t2
    # «принята» дважды, designer и developer затирали site/index.html друг друга).
    _agent_coro[tk(agent_id)] = asyncio.create_task(
        run_task(agent_id, role, task, publish, skill, department, objective, task_id))


async def run_task(agent_id: str, role: str, task: str, publish, skill: str = "",
                   department: str = "", objective: str = "", task_id: str = "") -> None:
    """Жизненный цикл одной задачи: Policy → бюджетный гейт → run_agent → приёмка →
    эскалация. Была вложенным замыканием _job внутри _assign — вынесена в модульную
    функцию (захватывала только параметры _assign, скрытых локалей нет)."""
    from src.office import trace
    t_rec_policy = (plan.get_task(task_id) if task_id and plan.is_generated() else None) or {"title": task}
    # Реальный найденный баг (живой прогон): и подсказка «строишь/правишь сайт»
    # в промпте (prompt_builder.task_context), и ensure_style_line/design_tokens
    # ниже включались для ЛЮБОЙ задачи developer/designer безусловно — включая
    # задачи вообще не про сайт (фоновый скрипт, повторяющийся процесс метрики).
    # Итог: developer, которому поручили "завести процесс курса USD/RUB",
    # вместо этого несколько раз подряд собрал и переделал целый сайт под
    # чужим слагом — часы работы и реальные деньги в никуда, а настоящая
    # задача так и не была выполнена. touches_site — тот же критерий, что уже
    # использует routers/work.py при решении, куда положить задачи инициативы.
    touches_site = plan.touches_site(t_rec_policy) if role in ("designer", "developer") else False
    # Параллельные Work (Фаза 3): переключаем workspace на подпапку ПРОЕКТА этой
    # задачи ДО первого write_file/read_file — run_task целиком выполняется в
    # своём asyncio.Task (создан в assign()), поэтому contextvars.ContextVar
    # изолирует эту область от параллельно исполняющейся задачи ДРУГОГО проекта
    # без явного лока (см. workspace.set_project_dir docstring).
    if task_id and plan.is_generated():
        from src.office import projects as projects_module
        workspace.set_project_dir(projects_module.workspace_dir_of(t_rec_policy.get("project", "")))
    registry.update_status(agent_id, "thinking")
    _thinking_since[tk(agent_id)] = time.time()
    _job_t0 = time.time()
    # Execution Policy (BOS §6): модель выбирается ПО ЗАДАЧЕ (рутина → дешёвая),
    # оценка стоимости пишется в trace ДО исполнения. Оверрайды владельца главнее.
    from src.office import execution_policy
    policy = execution_policy.decide(t_rec_policy, agent_id, role)
    # Анти-заклинивание скилла: 3+ провала задачи с ОДНИМ и тем же скиллом — смени
    # способ, а не ретрай того же пути. Реальный прогон: designer 7 раз подряд брал
    # framer_motion_3d_site, зависал на одинаковом месте и был убит watchdog'ом —
    # почти 1.5 часа и деньги в никуда, стратегия ни разу не поменялась.
    _attempts = int(t_rec_policy.get("attempts") or 0)
    if _attempts >= 3 and skill:
        from src.office import trace as _trace
        _trace.log("skill_switch", agent=agent_id, task_id=task_id,
                   dropped=skill, attempts=_attempts)
        await publish({"type": "system",
                       "text": f"🔁 {_attempts} попыток со скиллом «{skill}» не сработали — "
                               f"исполнитель меняет способ"})
        task = (task + f"\n\n⚠ ВАЖНО: предыдущие {_attempts} попыток этой задачи со скиллом "
                       f"«{skill}» НЕ завершились (зависания/ошибки). НЕ вызывай его снова. "
                       f"Возьми другой способ через use_skill (для сайта — «Премиальный сайт "
                       f"(без 3D)») или сделай работу напрямую своими инструментами.")
        skill = ""
    # BOS §6: оценка стоимости сверяется с ОСТАТКОМ бюджета ДО исполнения.
    if costs.would_exceed(policy["estimated_usd"]):
        registry.update_status(agent_id, "idle")
        _thinking_since.pop(tk(agent_id), None)
        _agent_task.pop(tk(agent_id), None)
        if task_id and plan.is_generated():
            plan.revert(task_id)
        reason = (f"⛔ Оценка задачи ~${policy['estimated_usd']:.2f} превышает остаток "
                  f"бюджета — офис на паузе. Повысьте лимит в «Компания → Лимиты».")
        control.pause(reason)
        trace.log("budget_gate", agent=agent_id, task_id=task_id,
                  est_usd=policy["estimated_usd"])
        await publish({"type": "system", "text": reason})
        summary = control.summary_text()
        if summary:
            await publish({"type": "system", "text": summary})
        return
    trace.log("agent_start", agent=agent_id, role=role,
              model=policy["model"], tier=policy["tier"],
              est_usd=policy["estimated_usd"], skill=skill or "")
    # Резерв бюджета ДО вызова LLM (см. costs.reserve докстринг) — закрывает
    # гонку между этим would_exceed() и record(), который пишется только
    # ПОСЛЕ ответа API: несколько параллельных задач иначе могли независимо
    # пройти проверку выше по одному и тому же totals() и совместно
    # проскочить лимит. Снимается в finally — после успеха реальная
    # стоимость уже учтена record()'ом, после провала реальной стоимости
    # не было вовсе.
    costs.reserve(policy["estimated_usd"])
    try:
        if role == "researcher":
            result = await researcher.run_async(task, depth="quick", publish=publish, agent_id=agent_id)
            state.save_deliverable(agent_id, role, t_rec_policy.get("title") or task, result)
        elif role == "strategist":
            result = await strategist.run_async(task, publish=publish, agent_id=agent_id, save=False)
        else:
            if role in ("designer", "developer") and touches_site:
                # Гарантируем «Стиль: …» ДО того, как модель начнёт строить сайт —
                # инструкция в скилле («marketer пишет строку, designer читает») не
                # гарантия: в проде marketer пропускал этот необязательный шаг под
                # давлением токенов, designer тоже не спрашивал коллегу, и сайт
                # строился по дефолтам модели — одинаково для любой ниши (см. handoff).
                # Идемпотентно: если строка уже есть (marketer справился сам) — не трогаем.
                from src.office import design_style
                b = brief.get()
                design_style.ensure_style_line(b.get("niche", ""), b.get("audience", ""))
                # Стек больше НЕ ротируется по нише (был выбор из 4 конкурирующих
                # скиллов — vanilla/React-esm.sh/Vue/Alpine) — платформа держит один
                # системный стек (vite_react_site), явно называемый в use_skill
                # designer/developer через ключевые слова скилла; ensure_stack_line
                # удалён вместе с design_style.STACKS.
                # Готовая CSS-шкала оттенков акцента (50-900) вместо того, чтобы
                # designer/developer придумывали hover/active-цвета на глаз —
                # несогласованно между файлами одной и той же страницы.
                design_style.ensure_design_tokens(b.get("niche", ""), b.get("audience", ""))
            ctx_task = task_with_context(role, task, skill, department=department, objective=objective,
                                        touches_site=touches_site, task_id=task_id)
            # title — короткая подпись для «Артефактов»/«Готовых результатов», НЕ
            # весь ctx_task/task: task здесь — уже составленный planning_engine
            # текст ("заголовок\n✅ ЗАДАЧА ВЫПОЛНЕНА, КОГДА: ...\n<фидбек>"), а не
            # чистое имя задачи. save_deliverable режет title по символам — раньше
            # резало эту составную строку прямо посреди "КОГДА: ..." (реальный
            # баг на скриншоте UI). t_rec_policy.get("title") — чистый заголовок
            # из plan.json, без критерия/фидбека.
            fn = agent_factory.create(role, ctx_task, agent_id, publish, skill=skill,
                                      model=policy["model"], title=t_rec_policy.get("title") or task)
            result = await fn()
            # ---- Приёмка качества (критик) для сайтов: дизайнер/разработчик ----
            if role in ("designer", "developer"):
                await review_and_maybe_fix(role, agent_id, task, skill, department,
                                           objective, publish, result=result or "",
                                           started_ts=_job_t0)
        registry.update_status(agent_id, "done")
        state.save_last_run(agent_id)
        trace.log("agent_done", agent=agent_id, role=role,
                  sec=round(time.time() - _job_t0, 1), out_len=len(result or ""),
                  task_id=task_id)
        _model_fail_count.pop(tk(agent_id), None)  # успех — счётчик сбитой модели сбрасываем
        attribute_result(agent_id, role, result)
        # Память отдела: фиксируем, что отдел сделал — пригодится коллегам в след. циклах
        knowledge.note_result(department, role, result or "")
        # Доска: закрываем ИМЕННО эту задачу — но ТОЛЬКО через приёмку (BOS §8).
        if task_id and plan.is_generated():
            from src.office import acceptance, events as events_mod
            t_rec = plan.get_task(task_id) or {}
            verdict = acceptance.check(t_rec.get("title", task) or task, role, result or "",
                                       done_criterion=t_rec.get("done_criterion", ""),
                                       started_ts=_job_t0,
                                       artifacts=plan.artifacts_of(t_rec),
                                       project_id=t_rec.get("project", ""),
                                       agent_id=agent_id)
            warns = verdict.get("warnings", [])
            trace.log("acceptance", agent=agent_id, task_id=task_id,
                      passed=verdict["passed"], levels=str(verdict["levels"]),
                      problems="; ".join(verdict["problems"])[:200],
                      warnings="; ".join(warns)[:200])
            if verdict["passed"]:
                plan.complete(task_id, acceptance=verdict)
                note = " (приёмка пройдена)"
                if warns:
                    # L1: работа принята, но вне согласованного контракта — не блок,
                    # а сигнал владельцу/CEO (предупреждение живёт в вердикте задачи).
                    note = " ⚠ принята с замечанием: " + "; ".join(warns)[:120]
                await publish({"type": "system",
                               "text": f"✅ Задача {task_id}{note}"})
            else:
                attempts = plan.revert(task_id)
                fb = acceptance.feedback_text(verdict)
                await publish({"type": "system",
                               "text": f"↩️ Задача {task_id} НЕ прошла приёмку "
                                       f"(попытка {attempts}): "
                                       + "; ".join(verdict["problems"])[:140]})
                lessons.add(role, f"Приёмка {task_id}: " + "; ".join(verdict["problems"])[:180])
                if attempts >= MAX_TASK_ATTEMPTS:
                    reason = "; ".join(verdict["problems"])[:200] or "приёмка не проходит"
                    plan.block(task_id, reason)
                    events_mod.raise_event(
                        "blocker",
                        f"Задача {task_id} заблокирована после {attempts} попыток: {reason}",
                        from_role=role, from_agent=agent_id, task_id=task_id)
                    await publish({"type": "system",
                                   "text": f"⛔ Задача {task_id} заблокирована после "
                                           f"{attempts} неудачных попыток — нужно решение "
                                           f"CEO или уточнение клиента. Причина: {reason[:120]}"})
                    # Blocker гарантированно доходит до владельца (BOS §10): сообщение
                    # в личный чат CEO зажигает бейдж непрочитанного, а не тонет в ленте.
                    from src.office import threads as threads_mod
                    t_rec_b = plan.get_task(task_id) or {}
                    note = (f"⛔ Задача «{(t_rec_b.get('title') or task_id)[:80]}» заблокирована: "
                            f"{reason[:160]}. Разблокировать можно во вкладке "
                            f"«Проект → Задачи» — команда попробует заново.")
                    threads_mod.post("orchestrator_1", "agent", note, kind="msg")
                    await publish({"type": "agent_message", "agent_id": "orchestrator_1",
                                   "from": "agent", "kind": "msg", "text": note})
                elif fb:
                    # Форензик-аудит 2026-07-18: задача (обложки кейсов) отклонялась
                    # ПОДРЯД по ОДНОЙ И ТОЙ ЖЕ причине ("дизайн-направление не
                    # подтверждено владельцем") несколько раз, но CEO узнавал об
                    # этом только на 3-й, финальной блокировке (events_mod.raise_event
                    # ниже) — Event Layer молчал все предыдущие разы, а CEO тем
                    # временем 7 раз подряд принимал одно и то же decide-решение
                    # вслепую, не видя, что реальный блокер не сдвинулся. Раньше
                    # причина эскалации была видна в теле лога чуть выше как
                    # "приёмка не проходит" — реальный текст показывает repeat.
                    prev_fb = (t_rec.get("last_feedback") or "").strip()
                    if prev_fb and prev_fb == fb.strip():
                        events_mod.raise_event(
                            "blocker",
                            f"Задача {task_id} второй раз подряд отклонена по ТОЙ ЖЕ причине: "
                            f"{fb[:180]}",
                            from_role=role, from_agent=agent_id, task_id=task_id)
                    # Фидбек приёмки сохраняется в задаче — попадёт исполнителю при переназначении.
                    plan.set_feedback(task_id, fb)
        # Trust Score: успешная задача повышает доверие к отделу
        if department:
            trust.record_success(department)
            if trust.should_propose_upgrade():
                trust.mark_upgrade_proposed()
                proposal = trust.upgrade_proposal_text()
                if proposal:
                    nl = autonomy.next_level()
                    await publish({"type": "autonomy_upgrade_offer", "agent_id": "orchestrator_1",
                                   "next_level": nl, "text": f"🤝 {proposal}"})
        # Живость: «сделал → отчитался» — короткий итог в ленту. Агент часто
        # сам начинает ответ с «Готово!»/«Готово:» — конкатенация с префиксом
        # ниже давала видимое «Готово: Готово! ...» (найдено при живом аудите).
        import re as _re_summary
        summary = (result or "").strip().replace("\n", " ")
        summary = _re_summary.sub(r"^готово[!:.\s]*", "", summary, flags=_re_summary.IGNORECASE).strip()[:120]
        if summary:
            await publish({"type": "speech", "agent_id": agent_id, "text": f"✅ Готово: {summary}"})
    except Exception as e:
        # str(TimeoutError) — пустая строка: 7 подряд agent_error с error="" в
        # реальном прогоне были недиагностируемы. Всегда включаем тип исключения.
        err_str = str(e).strip() or ""
        err_str = f"{type(e).__name__}: {err_str}" if err_str else type(e).__name__
        trace.log("agent_error", agent=agent_id, role=role,
                  sec=round(time.time() - _job_t0, 1), error=err_str[:200])
        await publish({"type": "error", "agent_id": agent_id, "text": err_str[:100]})
        registry.update_status(agent_id, "idle")
        if task_id and plan.is_generated():
            plan.revert(task_id)  # упала — вернуть в очередь
        if department:
            trust.record_failure(department)
        # Quota/billing 403 → ставим офис на паузу, чтобы не сжигать остаток
        if llm.is_quota_error(err_str):
            reason = "⛔ Недостаточно баланса у LLM-провайдера. Пополните счёт и нажмите «Возобновить»."
            control.pause(reason)
            await publish({"type": "system", "text": reason})
            summary = control.summary_text()
            if summary:
                await publish({"type": "system", "text": summary})
        elif llm.is_model_unavailable_error(err_str):
            # Самолечение: назначенная модель недоступна у провайдера. Повтор той же
            # ошибки для того же агента → сбрасываем модель на дефолт офиса.
            n = _model_fail_count.get(tk(agent_id), 0) + 1
            _model_fail_count[tk(agent_id)] = n
            if n >= 2:
                cleared = models_module.clear_broken_model(agent_id, role)
                _model_fail_count.pop(tk(agent_id), None)
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
            _model_fail_count.pop(tk(agent_id), None)
    finally:
        costs.release_reservation(policy["estimated_usd"])
        _thinking_since.pop(tk(agent_id), None)
        _agent_task.pop(tk(agent_id), None)
        # Снимаем СВОЙ хэндл (identity-check): если watchdog уже переназначил задачу
        # и под ключом лежит НОВАЯ корутина — её не трогаем.
        if _agent_coro.get(tk(agent_id)) is asyncio.current_task():
            _agent_coro.pop(tk(agent_id), None)


async def heal_stuck_agents(publish) -> None:
    """
    Самолечение: агент «думает» дольше MAX_THINK_SECS — его задача зависла (модель не
    ответила/застряла). Сбрасываем в idle, чтобы лидер переназначил. Делит состояние
    живости (_thinking_since/_agent_task) с run_task.
    """
    now = time.time()
    prefix = f"{ctx.get_tenant()}:"  # только агенты ТЕКУЩЕГО тенанта, не чужие
    # Агент, ждущий СВОЕГО ответа клиента (ask_user/одобрение публикации), НЕ
    # завис — штатное ожидание дольше MAX_THINK_SECS. ⚠️ Раньше это проверялось
    # ОДНИМ вопросом на весь тенант (list_pending()) — любой открытый вопрос
    # ЛЮБОГО агента продлевал таймер ВСЕМ, включая тех, кто реально завис и
    # никого ни о чём не спрашивал (production-readiness worklist п.5).
    # questions.pending_for(aid) — персонально, только СВОЙ вопрос защищает.
    from src.office import questions as questions_mod
    for key, since in list(_thinking_since.items()):
        if not key.startswith(prefix):
            continue
        aid = key[len(prefix):]
        if questions_mod.pending_for(aid):
            _thinking_since[key] = now
            continue
        if now - since > MAX_THINK_SECS:
            _thinking_since.pop(key, None)
            # Зомби-корутину ОТМЕНЯЕМ, а не просто «забываем»: иначе она продолжает
            # писать файлы и закрывать задачи параллельно с новым исполнителем
            # (llm.CALL_TIMEOUT ограничивает один вызов API, но не всю run_task).
            zombie = _agent_coro.pop(key, None)
            if zombie and not zombie.done():
                zombie.cancel()
            registry.update_status(aid, "idle")
            state.save_last_run(aid)  # короткий cooldown перед повтором
            tid = _agent_task.pop(key, None)
            if tid and plan.is_generated():
                # АНТИЦИКЛ: завис дизайнер/разработчик, но сайт УЖЕ написан — не гоняем
                # задачу по кругу. Публикуем что есть и принимаем задачу. ТОЛЬКО если
                # index.html менялся ПОСЛЕ старта ЭТОЙ задачи (иначе закрывали бы чужой работой).
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
                    # BOS §8: даже антицикл-закрытие идёт через приёмку (детерминированно).
                    critical = [p for p in critic.check_site() if critic.is_critical(p)]
                    if not critical:
                        await publish_site_auto(publish)
                        plan.complete(tid, acceptance={"passed": True, "problems": [],
                                                       "levels": {"build": "skip",
                                                                  "functional": "ok",
                                                                  "acceptance": "watchdog"}})
                        await publish({"type": "system",
                                       "text": f"✅ {aid} долго думал, но сайт уже готов — задача {tid} "
                                               f"принята и опубликована (без перезапуска)."})
                        continue
                    plan.set_feedback(tid, "⚠ ПРИЁМКА НЕ ПРОЙДЕНА (сайт написан, но есть "
                                           "критические проблемы):\n"
                                      + "\n".join(f"- {critic.text_of(p)}" for p in critical[:3]))
                plan.revert(tid)  # иначе — вернуть зависшую задачу в очередь
            # Trust Score: зависший агент снижает доверие к его отделу
            rec_stuck = registry.get(aid)
            if rec_stuck and rec_stuck.department:
                trust.record_stuck(rec_stuck.department)
            await publish({"type": "system",
                           "text": f"🔧 {aid} завис (> {MAX_THINK_SECS}s) — сброшен, задача переназначится"})
