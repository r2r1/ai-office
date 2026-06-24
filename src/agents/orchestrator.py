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
from src.office import registry, models as models_module, org as org_module

HIREABLE_ROLES = {"salesman", "developer", "marketer", "analyst"}
MAX_PER_ROLE = 1  # один ответственный на роль (единая зона ответственности, без клонов)

_COMPANY_SYSTEM = """Ты — CEO автономной AI-компании. Ты НЕ делаешь работу руками и НЕ ставишь
задачи отдельным сотрудникам — этим занимаются руководители отделов. Твоя задача — управлять
СТРУКТУРОЙ компании: открывать отделы по необходимости, закрывать выполнившие свою цель и
ставить отделам цели. Каждый ход — ОДНО решение.

ОТДЕЛЫ (открывай только когда этого реально требует текущий этап):
- tech (Технический отдел, лидер CTO): продукт, код, боты, сайты, автоматизации, интеграции.
- marketing (Отдел маркетинга, лидер CMO): контент, соцсети, реклама, бренд, привлечение аудитории.
- sales (Отдел продаж, лидер Head of Sales): поиск клиентов, переговоры, конверсия лидов, CRM.

Принципы:
- Если продукт (бот/сайт/код) ещё не создаётся, а цель/этап его требуют — СРАЗУ открой tech. Не тяни с wait.
- Открывай отдел ТОЛЬКО при реальной потребности текущего этапа. Нет задачи на клиентов — не открывай продажи.
- Не открывай уже открытый отдел. Если у открытого отдела выполнена цель — закрой его (close_department).
- Если все нужные отделы открыты и работают — wait.
- ПРИОРИТЕТ УКАЗАНИЙ ПОЛЬЗОВАТЕЛЯ: его решения главнее стратегии. Если в указаниях есть прямая
  просьба (например «запусти бота») — НЕМЕДЛЕННО открой нужный отдел (бот/код/сайт → tech).

Ты также ведёшь бизнес-этапы (вехи): помечай текущий и завершённый этап.

Ответь ТОЛЬКО валидным JSON без markdown:
{
  "thought": "краткая мысль CEO (1 предложение, по-русски)",
  "action": "open_department" | "close_department" | "delegate" | "wait",
  "department": "tech | marketing | sales (для open/close/delegate)",
  "objective": "конкретная цель отдела (для open_department/delegate), иначе null",
  "done_reason": "почему отдел закрывается (для close_department), иначе null",
  "current_milestone": "id текущего этапа",
  "milestone_done": "id этапа, если ТОЛЬКО ЧТО завершён, иначе null",
  "milestone_summary": "что достигнуто на завершённом этапе, иначе null"
}"""

_MILESTONES_SYSTEM = """Ты — директор автономного AI-офиса. Раздели путь к ЦЕЛИ КЛИЕНТА на
3-5 этапов, ведущих к ГОТОВОМУ РАБОЧЕМУ РЕЗУЛЬТАТУ — тому, что клиент попросил.

🎯 Этапы должны заканчиваться СДАЧЕЙ результата клиенту, а не выдуманным ростом бизнеса.
Для «лендинг, который приводит звонки» правильные этапы: подготовка контента/оффера →
сборка лендинга → проверка и публикация → результат сдан (мониторинг заявок). НЕ добавляй
этапы вроде «сбор 50 лидов», «первые продажи», «масштабирование до 1М», если клиент об
этом НЕ просил — это уводит офис в бесконечные недостижимые задачи.

Последний этап — всегда «результат готов / сдан» (после него офис мониторит, а не выдумывает работу).

Ответь ТОЛЬКО валидным JSON без markdown:
{"stages": [{"id": "content", "title": "Контент и оффер"}, {"id": "build", "title": "Сборка"}, {"id": "delivered", "title": "Результат готов"}]}

id — короткий латиницей, title — по-русски. 3-5 этапов."""

_DECIDE_SYSTEM = """Ты — директор автономного AI-офиса. Ты управляешь командой агентов и
ведёшь бизнес к цели клиента. Каждый ход ты принимаешь ОДНО решение: поручить конкретную
задачу одному агенту, нанять нового специалиста или подождать.

ЗОНЫ ОТВЕТСТВЕННОСТИ (соблюдай строго):
- researcher — исследование, сбор данных, анализ рынка
- strategist — планирование, стратегия, бизнес-модель
- salesman — продажи, поиск клиентов, переговоры, CRM
- developer — технические задачи, автоматизации, продукт, код
- marketer — маркетинг, контент, соцсети, реклама, бренд
- analyst — аналитика данных, метрики, отчёты, KPI
- integrator — подключение внешних сервисов (Telegram и др.), проверка доступов, реальные действия через API. Поручай ему всё, что требует реальной отправки/публикации во внешний сервис.

Принципы:
- Двигай бизнес к текущему этапу. Ставь конкретные, выполнимые задачи с измеримым результатом.
- Не повторяй задачи, которые агент уже сделал, и НЕ повторяй задачу, которая прямо сейчас в работе.
- Назначай задачу агенту строго по его зоне ответственности (role).
- ЕДИНАЯ ОТВЕТСТВЕННОСТЬ: на каждую роль ОДИН агент. Если нужный исполнитель занят (on_cooldown/thinking) — ПОДОЖДИ (action=wait), НЕ нанимай второго такого же. Никаких клонов на одну и ту же работу.
- Если нужной роли вообще нет в команде — найми (только из доступных ролей).
- ПРИОРИТЕТ УКАЗАНИЙ ПОЛЬЗОВАТЕЛЯ: если в разделе «Указания пользователя» есть решение клиента — оно ГЛАВНЕЕ стратегии и ТЗ. Не ставь задачи, противоречащие ему (пример: клиент сказал «не BotsBox, пишем своего бота» → задачи про BotsBox ЗАПРЕЩЕНЫ, поручай разработку своего бота).
- Не поручай подключение платных сторонних конструкторов (Tilda, BotsBox и т.п.), если клиент их не одобрил: сайт публикуется встроенной интеграцией website, бот/код разработчик пишет сам.
- КРИТИЧНО: Все API-ключи доступны ЛЮБОМУ агенту через get_connection(). НЕ выбирай агента потому что "у него ключ".
- Если текущий этап достигнут — пометь его выполненным и опиши, что сделано.
- При найме (action=hire) — указывай конкретный skill агента: его специализацию на весь проект.

Ответь ТОЛЬКО валидным JSON без markdown:
{
  "thought": "краткая мысль директора (1 предложение, по-русски)",
  "action": "assign" | "hire" | "wait",
  "agent_id": "id агента для action=assign (например salesman_1)",
  "role": "роль для action=hire (одна из доступных)",
  "task": "конкретная задача для агента (для assign или hire)",
  "skill": "специализация агента при найме (например: 'создание Telegram-ботов', 'разработка лендингов', 'настройка CRM'), null если assign",
  "current_milestone": "id текущего этапа",
  "milestone_done": "id этапа, если он ТОЛЬКО ЧТО завершён, иначе null",
  "milestone_summary": "что достигнуто на завершённом этапе, иначе null"
}"""


_DIRECTIVE_SYSTEM = """Ты — CEO автономного AI-офиса. Владелец бизнеса (предприниматель) написал
тебе в общий чат. Твоя работа — ПОНЯТЬ запрос и ОРГАНИЧНО вписать его в текущую работу офиса:
сориентировать команду, при необходимости подправить этапы и поставить новые задачи.

Сначала определи характер сообщения (scope):
- "steer"     — указание/просьба/новая цель, влияющая на работу (делаем X, добавь Y, поменяй приоритет).
- "question"  — предприниматель что-то спрашивает (статус, «что сделано?»). Работу НЕ меняем.
- "smalltalk" — благодарность/реплика без задачи. Работу НЕ меняем.

Ответь предпринимателю КОРОТКО и по-деловому от первого лица (1–3 предложения, по-русски):
что понял и что именно изменишь в работе. Не выдумывай уже выполненную работу.

Если scope="steer" — сформулируй directive (суть указания одной фразой для команды) и при
РЕАЛЬНОЙ необходимости:
• milestone_ops — правки этапов (вех):
    {"op":"add","title":"...","after":"<id этапа|null>"}   — добавить бизнес-этап
    {"op":"retitle","id":"<id>","title":"..."}             — переименовать
    {"op":"focus","id":"<id>"}                             — сделать этап текущим
    {"op":"note","id":"<id>","text":"..."}                 — заметка-обоснование
• new_tasks — НОВЫЕ задачи на доску, если запрос требует новой работы. Роль строго одна из:
  developer, designer, integrator, marketer, salesman.
    {"title":"...","role":"developer","done_criterion":"как проверить готовность"}

Не дублируй уже идущую работу. Не плоди задачи, которых предприниматель не просил.
Если ничего менять не нужно (question/smalltalk или указание уже учтено) — массивы пустые.

Ответь ТОЛЬКО валидным JSON без markdown:
{
  "reply": "ответ предпринимателю от лица CEO (1–3 предложения)",
  "scope": "steer" | "question" | "smalltalk",
  "directive": "нормализованная суть указания одной фразой (пусто если не steer)",
  "milestone_ops": [],
  "new_tasks": [],
  "priority": "now" | "normal"
}"""


async def interpret_directive(
    goal: str,
    strategy: str,
    milestone_list: list[dict],
    departments_text: str,
    board_summary: str,
    message: str,
    publish: Optional[Callable[[dict], Awaitable[None]]] = None,
) -> dict:
    """CEO-триаж сообщения предпринимателя: понять и вписать в текущую работу.

    Возвращает {reply, scope, directive, milestone_ops, new_tasks, priority}.
    Безопасно: при сбое LLM вернёт {} — вызывающая сторона делает фолбэк.
    """
    if publish:
        await publish({"type": "thinking", "agent_id": "orchestrator_1",
                       "text": "Обдумываю ваш запрос и как вписать его в работу..."})

    ms_text = "\n".join(
        f"- {m.get('id')}: {m.get('title')} [{m.get('status')}]" for m in milestone_list
    ) or "(этапов ещё нет)"
    user = (
        f"Цель компании: {goal}\n\n"
        f"Стратегия (кратко):\n{strategy[:500]}\n\n"
        f"Этапы сейчас:\n{ms_text}\n\n"
        f"Отделы:\n{departments_text or '(отделов пока нет)'}\n\n"
        f"Доска задач: {board_summary or '(пусто)'}\n\n"
        f"=== СООБЩЕНИЕ ПРЕДПРИНИМАТЕЛЯ ===\n{message}\n\n"
        f"Пойми запрос и впиши его в текущую работу."
    )
    raw = await llm.run_agent(
        system=_DIRECTIVE_SYSTEM,
        user=user,
        model=models_module.for_agent("orchestrator_1"),
        max_tokens=600,
        use_search=False,
        agent_id="orchestrator_1",
    )
    return _parse_json(raw)


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
    # Подстраховка — ЧЕСТНЫЕ этапы про сдачу результата, а НЕ бизнес-фантазии
    # («первые клиенты», «масштабирование») которые офис не может реально достичь за прогон
    # и которые потом фейково помечались выполненными.
    if not stages or not isinstance(stages, list):
        stages = [
            {"id": "offer", "title": "Оффер и позиционирование"},
            {"id": "build", "title": "Сборка результата"},
            {"id": "delivered", "title": "Результат готов и сдан"},
        ]
    return stages[:6]


_PLAN_SYSTEM = """Ты — операционный директор автономной AI-компании. На вход — цель клиента,
стратегия и ТЗ. Составь граф задач, который ВЕДЁТ К ГОТОВОМУ РЕЗУЛЬТАТУ, который просил клиент.

Доступные роли (ТОЛЬКО эти — у каждой есть отдел-исполнитель):
- developer — кастомный код, скрипты, автоматизации
- designer — красивые многостраничные сайты/лендинги (HTML/CSS/JS)
- integrator — подключение внешних сервисов, запуск готового Telegram-бота записи
- marketer — контент, тексты, офферы для САМОГО результата (например тексты лендинга)
- salesman — поиск клиентов, офферы, карточки на картах, переговоры
НЕ используй другие роли (analyst/researcher/architect) в задачах — их некому исполнять в отделах.

🎯 ГЛАВНОЕ: задачи = только то, что нужно, чтобы ВЫПОЛНИТЬ ЗАПРОС КЛИЕНТА и довести до
рабочего состояния. Это КОНЕЧНЫЙ набор задач — когда они сделаны, цель достигнута и офис
останавливается. НЕ добавляй недостижимую/бесконечную работу, которую клиент не просил:
«собрать 50 B2B-лидов», «холодный outreach», «продать лендинг другим компаниям»,
«масштабирование» — НЕЛЬЗЯ, если клиент об этом прямо не просил. Для «лендинга под звонки»
задачи: тексты/оффер (marketer) → сборка лендинга (designer) → проверка и публикация. Точка.

🚫 НЕ ВЫДУМЫВАЙ ПРОДУКТ. Если клиент НЕ просил конкретный артефакт (сайт/лендинг/бот/приложение),
а сформулировал стратегическую цель («открыть бизнес», «внедрять ИИ», «выйти на рынок») — НЕ
строй лендинг по умолчанию. Тогда ПЕРВАЯ И ЕДИНСТВЕННАЯ задача: marketer готовит план запуска
и рекомендации на основе стратегии и через ask_user СПРАШИВАЕТ клиента, что строить первым.
Стройте продукт только когда клиент его явно выбрал. Упоминание продукта как услуги бизнеса
клиента (напр. «продаю ботов») — это НЕ просьба построить такой продукт для него.

Правила:
- 3–7 задач, каждая — самостоятельный измеримый результат, ведущий к сдаче.
- Указывай зависимости (deps) ТОЛЬКО когда задача реально требует результата другой.
- Независимые задачи (без общих deps) офис делает ПАРАЛЛЕЛЬНО — используй это.
- done_criterion — как проверить, что задача выполнена (конкретно).

Ответь ТОЛЬКО валидным JSON без markdown:
{
  "tasks": [
    {"id": "t1", "title": "...", "role": "designer", "deps": [], "done_criterion": "..."},
    {"id": "t2", "title": "...", "role": "salesman", "deps": [], "done_criterion": "..."}
  ]
}"""


async def plan_tasks(
    strategy: str,
    goal: str,
    tech_design: str = "",
    publish: Optional[Callable[[dict], Awaitable[None]]] = None,
) -> list[dict]:
    """Граф конкретных задач (роль + зависимости + критерий готовности) из стратегии/ТЗ."""
    if publish:
        await publish({"type": "thinking", "agent_id": "orchestrator_1",
                       "text": "Раскладываю цель на граф задач..."})
    user = (f"Цель клиента: {goal}\n\nСтратегия:\n{strategy[:2000]}\n\n"
            f"ТЗ (кратко):\n{tech_design[:1200]}\n\nСоставь граф задач.")
    raw = await llm.run_agent(
        system=_PLAN_SYSTEM,
        user=user,
        model=models_module.for_agent("orchestrator_1"),
        max_tokens=900,
        use_search=False,
        agent_id="orchestrator_1",
    )
    data = _parse_json(raw)
    tasks = data.get("tasks", [])
    return tasks if isinstance(tasks, list) else []


async def decide_company(
    goal: str,
    strategy: str,
    milestones: list[dict],
    publish: Optional[Callable[[dict], Awaitable[None]]] = None,
) -> dict:
    """
    Решение CEO на уровне КОМПАНИИ: какой отдел открыть/закрыть/что ему поручить.
    Возвращает dict с action: open_department | close_department | delegate | wait.
    """
    ms_lines = [f"- [{m['status']}] {m['id']}: {m['title']}" for m in milestones]
    ms_text = "\n".join(ms_lines) or "этапы ещё не заданы"

    # Статус отделов: открытые — с целью и дайджестом подчинённых (видимость CEO через лидеров)
    dept_lines = []
    for did, info in org_module.catalog().items():
        st = org_module.state_of(did)
        if st.get("status") == "open":
            digest = org_module.department_digest(did)
            obj = st.get("objective") or "цель не задана"
            dept_lines.append(f"🟢 {did} ({info['name']}) — ОТКРЫТ. Цель: {obj}\n{digest}")
        else:
            dept_lines.append(f"⚪ {did} ({info['name']}) — закрыт. Назначение: {info['hint']}")
    dept_text = "\n\n".join(dept_lines)

    from src.office import memory as memory_module
    user_directives = memory_module.context_block() or ""
    directives_section = (
        f"\n=== УКАЗАНИЯ ПОЛЬЗОВАТЕЛЯ (ПРИОРИТЕТ) ===\n{user_directives}\n"
        if user_directives.strip() else ""
    )

    if publish:
        await publish({"type": "thinking", "agent_id": "orchestrator_1",
                       "text": "Решаю, какие отделы нужны компании сейчас..."})

    user = (
        f"Цель компании: {goal}\n\n"
        f"Стратегия (кратко):\n{strategy[:400]}\n"
        f"{directives_section}\n"
        f"Этапы пути:\n{ms_text}\n\n"
        f"Отделы сейчас:\n{dept_text}\n\n"
        f"Прими ОДНО решение: open_department (если этап требует новой способности), "
        f"close_department (если цель отдела выполнена), delegate (обновить цель открытого отдела) "
        f"или wait."
    )

    raw = await llm.run_agent(
        system=_COMPANY_SYSTEM,
        user=user,
        model=models_module.for_agent("orchestrator_1"),
        max_tokens=400,
        use_search=False,
        agent_id="orchestrator_1",
    )
    decision = _parse_json(raw)
    if not decision:
        return {"action": "wait", "thought": "CEO не принял решение, жду следующий цикл"}

    action = decision.get("action", "wait")
    dept = decision.get("department", "")
    if action in ("open_department", "close_department", "delegate"):
        if dept not in org_module.catalog():
            return {"action": "wait", "thought": f"Неизвестный отдел {dept} — жду"}
        if action == "open_department" and org_module.is_open(dept):
            return {"action": "wait", "thought": f"Отдел {dept} уже открыт — жду"}
        if action in ("close_department", "delegate") and not org_module.is_open(dept):
            return {"action": "wait", "thought": f"Отдел {dept} не открыт — нечего {action}"}
    return decision


async def decide(
    goal: str,
    strategy: str,
    milestones: list[dict],
    publish: Optional[Callable[[dict], Awaitable[None]]] = None,
    agent_availability: Optional[dict] = None,
    tech_design: str = "",
) -> dict:
    """
    Главное решение директора: кому что поручить дальше.
    Возвращает dict с action: assign | hire | wait.
    agent_availability: {agent_id: {status, on_cooldown, cooldown_secs}}
    """
    agents = registry.all_agents()
    avail = agent_availability or {}

    # Подсчёт агентов по ролям
    role_counts = {}
    for a in agents:
        role_counts[a.role] = role_counts.get(a.role, 0) + 1

    existing_roles = {a.role for a in agents if a.role in HIREABLE_ROLES}
    hireable_missing = HIREABLE_ROLES - existing_roles

    # Сводка по команде с доступностью и последними результатами
    from src.office import state
    roster_lines = []
    for a in agents:
        avl = avail.get(a.agent_id, {})
        cooldown_note = f"🔴занят/кулдаун {avl['cooldown_secs']}с" if avl.get("on_cooldown") else "🟢свободен"
        if a.status == "thinking":
            cooldown_note = "🔴думает"
        last = state.result_for(a.agent_id)
        last_short = (last[:100] + "…") if last and len(last) > 100 else (last or "ещё не сдавал")
        roster_lines.append(
            f"- {a.agent_id} ({a.role}) [{cooldown_note}]: {last_short}"
        )
    roster = "\n".join(roster_lines) or "команда пустая"

    ms_lines = [f"- [{m['status']}] {m['id']}: {m['title']}" for m in milestones]
    ms_text = "\n".join(ms_lines) or "этапы ещё не заданы"

    # Нанимать можно только ОТСУТСТВУЮЩУЮ роль — занятых не клонируем (единая ответственность)
    available_to_hire = hireable_missing

    # Указания пользователя (его ответы агентам) — приоритетнее стратегии и ТЗ
    from src.office import memory as memory_module
    user_directives = memory_module.context_block() or ""

    if publish:
        await publish({"type": "thinking", "agent_id": "orchestrator_1",
                       "text": "Анализирую команду и решаю, что делать дальше..."})

    tdd_section = f"\nТЗ архитектора:\n{tech_design[:500]}\n" if tech_design else ""
    directives_section = f"\n=== УКАЗАНИЯ ПОЛЬЗОВАТЕЛЯ (ПРИОРИТЕТ над стратегией/ТЗ) ===\n{user_directives}\n" if user_directives.strip() else ""
    user = (
        f"Цель: {goal}\n\n"
        f"Стратегия (кратко):\n{strategy[:400]}\n"
        f"{tdd_section}"
        f"{directives_section}\n"
        f"Этапы пути:\n{ms_text}\n\n"
        f"Команда сейчас (статус и доступность):\n{roster}\n\n"
        f"Роли доступные для найма (только отсутствующие): {', '.join(sorted(available_to_hire)) or 'нет — все нужные роли уже в команде'}\n\n"
        f"Прими ОДНО решение: assign (поручить 🟢свободному агенту), "
        f"hire (только отсутствующую роль), или wait (если нужный исполнитель занят — жди, не клонируй)."
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
        if role not in HIREABLE_ROLES:
            decision["action"] = "wait"
            decision["thought"] = f"Роль {role} не подходит для найма — жду"
        elif role_counts.get(role, 0) >= MAX_PER_ROLE:
            decision["action"] = "wait"
            decision["thought"] = f"Уже {role_counts.get(role, 0)} агентов роли {role} — жду освобождения"

    elif action == "assign":
        aid = decision.get("agent_id", "")
        rec = registry.get(aid)
        if rec is None:
            # пробуем найти агента по роли
            role_hint = decision.get("role", "")
            match = next((a for a in agents if a.role == role_hint), None)
            if match:
                decision["agent_id"] = match.agent_id
                rec = match
            else:
                decision["action"] = "wait"
                decision["thought"] = "Указан несуществующий агент — жду"
                return decision

        # Если директор всё равно выбрал занятого агента — ищем свободного той же роли
        if rec and avail.get(rec.agent_id, {}).get("on_cooldown"):
            role = rec.role
            free = next(
                (a for a in agents if a.role == role and not avail.get(a.agent_id, {}).get("on_cooldown")),
                None,
            )
            if free:
                decision["agent_id"] = free.agent_id
            else:
                # Единая ответственность: исполнитель занят — ждём его, не клонируем роль
                decision["action"] = "wait"
                decision["thought"] = f"{role} занят текущей задачей — жду результат, не дублирую"

    return decision
