"""
Orchestrator (CEO) — вершина иерархии офиса.

Он НЕ делает работу руками и НЕ ставит задачи людям — задачи распределяет
детерминированная маршрутизация плана (loop._run_leaders). Что осталось за CEO:
  • plan_milestones / plan_tasks — разбить путь к цели на этапы и план-граф;
  • decide_company — структура компании: открыть/закрыть отдел, цель отделу;
  • interpret_directive — триаж сообщений владельца (Intent → правки плана);
  • board_decide / generate_initiative — совет директоров и инициативы.

Работает через ядро llm.py, отвечает строгим JSON.
"""

import json
from typing import Optional, Callable, Awaitable

from src.core import llm
from src.office import models as models_module, org as org_module

# Документированный инвариант «на роль — один агент» (CLAUDE.md §3.2). Enforcement
# живёт в call-sites: registry.has_role (_hire_leader), leaders.decide («уже в отделе»),
# детерминированная маршрутизация loop._run_leaders. Прежний LLM-решатель уровня
# агентов (decide) удалён как мёртвый код — plan-driven цикл его не вызывал.
MAX_PER_ROLE = 1

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
  "milestone_summary": "что достигнуто на завершённом этапе, иначе null",
  "alternatives": [{"action": "...", "reason": "почему не выбрано"}],
  "confidence": 75,
  "risks": ["риск 1"],
  "expected_effect": "что произойдёт после этого решения",
  "data_used": ["strategy", "events", "user_directives"]
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

⚠️ ЕСЛИ предприниматель указывает на КОНКРЕТНЫЙ ДЕФЕКТ в уже сданной работе (сайт неверно
что-то продаёт, форма не работает, текст не соответствует бизнесу и т.п.) — это ВСЕГДА
new_tasks с ролью designer/developer, даже если все задачи на доске "done". Правка этапов
(milestone_ops) сама по себе НИЧЕГО не чинит — файл никто не тронет, если не поставить
задачу. Реальный кейс бага: CEO ответил предпринимателю "скорректирую фокус лендинга",
сдвинул этап через milestone_ops, но new_tasks оставил пустым — сайт остался
неисправленным, потому что "фокус этапа" не заставляет никого редактировать файл.

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
    niche: str = "",
    audience: str = "",
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
    biz_line = ""
    if niche:
        biz_line += f"Бизнес клиента — что он продаёт конечным покупателям: {niche}\n"
    if audience:
        biz_line += f"Аудитория — кому продаёт: {audience}\n"
    user = (
        f"{biz_line}Цель ЭТОГО прогона офиса (не то, что продаёт компания конечным "
        f"покупателям): {goal}\n\n"
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

    from src.office import memory as memory_module, lessons as lessons_module
    from src.office import world as world_module
    from src.office import events as events_module
    user_directives = memory_module.context_block() or ""
    directives_section = (
        f"\n=== УКАЗАНИЯ ПОЛЬЗОВАТЕЛЯ (ПРИОРИТЕТ) ===\n{user_directives}\n"
        if user_directives.strip() else ""
    )
    # World Model: CEO смотрит на единый срез «где компания сейчас» (Business State +
    # Objectives), а не восстанавливает картину из кусков — BOS §4, SSOT.
    directives_section += world_module.context_block()
    # Event Layer (BOS §10): сигналы отделов CEO видит ЗДЕСЬ — прежний потребитель
    # (decide) мёртв с перехода на plan-driven цикл, и problem/signal/info не читал
    # никто. После показа помечаем их обработанными детерминированно; opportunity
    # оставляем блоку инициатив (_orchestrate), blocker — до разблокировки задачи.
    pending_events = events_module.pending()
    directives_section += events_module.context_block()

    # Нерешённые замечания от критика — CEO видит незакрытые проблемы результатов
    all_lessons = lessons_module.all_lessons()
    if all_lessons:
        lessons_lines = []
        for role, items in all_lessons.items():
            for it in items[-3:]:  # последние 3 по роли
                lessons_lines.append(f"  [{role}] {it.get('text','')[:120]}")
        if lessons_lines:
            directives_section += (
                "\n=== ОТКРЫТЫЕ ЗАМЕЧАНИЯ ПО РЕЗУЛЬТАТАМ (требуют внимания) ===\n"
                + "\n".join(lessons_lines) + "\n"
            )

    if publish:
        await publish({"type": "thinking", "agent_id": "orchestrator_1",
                       "text": "Решаю, какие отделы нужны компании сейчас..."})

    user = (
        f"Цель компании: {goal}\n\n"
        f"Стратегия (кратко):\n{strategy[:1500]}\n"
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

    # problem/signal/info показаны CEO этим ходом → обработаны (иначе копились в
    # pending навсегда и раздували контекст каждого следующего решения).
    seen = [e["id"] for e in pending_events if e.get("kind") in ("problem", "signal", "info")]
    if seen:
        events_module.mark_processed(seen)

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


_BOARD_SYSTEM = """Ты — CEO автономной AI-компании. Только что прошло заседание совета директоров.
Ты выслушал позиции лидеров отделов. Прими итоговое решение по спорному вопросу.
Ответь ТОЛЬКО валидным JSON без markdown:
{
  "conclusion": "финальное решение CEO (2-3 предложения, по-русски)",
  "action_plan": ["шаг 1", "шаг 2"],
  "confidence": 80,
  "risks": ["остаточный риск"],
  "expected_effect": "что изменится после выполнения плана"
}"""


async def board_decide(
    conflict: str,
    positions: dict[str, str],
    publish: Optional[Callable[[dict], Awaitable[None]]] = None,
) -> dict:
    """Финальное решение CEO после выслушивания позиций отделов."""
    if publish:
        await publish({"type": "thinking", "agent_id": "orchestrator_1",
                       "text": "Взвешиваю позиции отделов и принимаю решение..."})

    pos_text = "\n".join(
        f"- {dept}: {view[:250]}" for dept, view in positions.items()
    ) or "(нет позиций)"
    user = (
        f"Спорный вопрос: {conflict}\n\n"
        f"Позиции лидеров отделов:\n{pos_text}\n\n"
        "Прими финальное решение совета директоров."
    )
    raw = await llm.run_agent(
        system=_BOARD_SYSTEM,
        user=user,
        model=models_module.for_agent("orchestrator_1"),
        max_tokens=500,
        use_search=False,
        agent_id="orchestrator_1",
    )
    result = _parse_json(raw)
    if not result:
        result = {"conclusion": "Совет рекомендует продолжить работу в штатном режиме.",
                  "confidence": 50, "risks": [], "expected_effect": ""}
    return result


_INITIATIVE_SYSTEM = """Ты — CEO автономной AI-компании. На основе текущей ситуации
предложи одну конкретную инициативу с оценкой эффекта и готовыми задачами.
Ответь ТОЛЬКО валидным JSON без markdown:
{
  "title": "Краткое название инициативы",
  "rationale": "Почему сейчас это важно (1-2 предложения, конкретные данные)",
  "expected_outcome": "Конкретный ожидаемый результат (например: +15% конверсии)",
  "estimated_effort": "1-2 цикла",
  "tasks": [
    {"title": "Задача 1", "role": "designer", "done_criterion": "..."}
  ]
}"""


async def generate_initiative(
    goal: str,
    strategy: str,
    opportunity_summary: str,
    publish: Optional[Callable[[dict], Awaitable[None]]] = None,
) -> dict:
    """CEO генерирует проактивную инициативу на основе наблюдаемой возможности."""
    user = (
        f"Цель компании: {goal}\n\n"
        f"Стратегия (кратко):\n{strategy[:800]}\n\n"
        f"Наблюдаемая возможность: {opportunity_summary}\n\n"
        "Сформулируй инициативу с конкретными задачами."
    )
    raw = await llm.run_agent(
        system=_INITIATIVE_SYSTEM,
        user=user,
        model=models_module.for_agent("orchestrator_1"),
        max_tokens=500,
        use_search=False,
        agent_id="orchestrator_1",
    )
    return _parse_json(raw) or {}
