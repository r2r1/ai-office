"""
Orchestrator (CEO) — вершина иерархии офиса.

Он НЕ делает работу руками и НЕ ставит задачи людям — задачи распределяет
детерминированная маршрутизация плана (planning_engine.run_leaders). Что осталось за CEO:
  • plan_milestones / plan_tasks — разбить путь к цели на этапы и план-граф;
  • decide_company — структура компании: открыть/закрыть отдел, цель отделу;
  • interpret_directive — триаж сообщений владельца (Intent → правки плана);
  • board_decide / generate_initiative — совет директоров и инициативы.

Работает через ядро llm.py, отвечает строгим JSON.

Тексты системных промптов CEO живут файлами policies/ceo_*.md и собираются
prompt_builder.company_system — с тем же слотом Brief (единственный сериализатор
goal≠niche), что у воркеров, и с полным логом в prompts.jsonl (раньше решения CEO
отлаживались вслепую). Литералов промптов в этом модуле нет — engineering-principles
§1 «бизнес-логика не в промптах-литералах», BOS §7.
"""

import json
import time
from typing import Optional, Callable, Awaitable

from src.core import llm
from src.office import models as models_module, org as org_module
from src.office import prompt_builder

# Документированный инвариант «на роль — один агент» (CLAUDE.md §3.2). Enforcement
# живёт в call-sites: registry.has_role (planning_engine.hire_leader), leaders.decide
# («уже в отделе»), детерминированная маршрутизация planning_engine.run_leaders.
# Прежний LLM-решатель уровня агентов (decide) удалён как мёртвый код — plan-driven
# цикл его не вызывал.
MAX_PER_ROLE = 1


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
    # Заблокированные задачи — с ПРИЧИНОЙ, не только счётчиком «⛔N» из board_summary.
    # Раньше CEO видел лишь число и не мог связать вопрос владельца («а зачем нам
    # бот?») с конкретным блокером — отвечал уклончиво вместо «вот эта задача
    # заблокирована по такой-то причине» (реальный кейс, см. handoff).
    from src.office import plan as plan_module
    blocked = plan_module.blocked_tasks()
    blocked_section = ""
    if blocked:
        lines = [f"- «{t.get('title','')[:100]}» ({t.get('role','')}): {t.get('blocked_reason','')[:200]}"
                 for t in blocked[:5]]
        blocked_section = (
            "\n=== ЗАБЛОКИРОВАННЫЕ ЗАДАЧИ (ждут твоего решения) ===\n" + "\n".join(lines) +
            "\nЕсли вопрос предпринимателя касается одной из них — назови её прямо и объясни причину "
            "блокировки, не уходи в общие фразы.\n"
        )
    # niche/audience/goal сериализует слот Brief в системном промпте (единый
    # сериализатор), здесь — только оперативный контекст этого хода.
    user = (
        f"Стратегия (кратко):\n{strategy[:500]}\n\n"
        f"Этапы сейчас:\n{ms_text}\n\n"
        f"Отделы:\n{departments_text or '(отделов пока нет)'}\n\n"
        f"Доска задач: {board_summary or '(пусто)'}\n"
        f"{blocked_section}\n"
        f"=== СООБЩЕНИЕ ПРЕДПРИНИМАТЕЛЯ ===\n{message}\n\n"
        f"Пойми запрос и впиши его в текущую работу."
    )
    system, _pid = prompt_builder.company_system(
        "ceo_directive", "orchestrator_1", "orchestrator", user)
    raw = await llm.run_agent(
        system=system,
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

    user = f"Стратегия:\n{strategy[:2500]}\n\nРаздели путь на этапы."
    system, _pid = prompt_builder.company_system(
        "ceo_milestones", "orchestrator_1", "orchestrator", user)
    raw = await llm.run_agent(
        system=system,
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
    user = (f"Стратегия:\n{strategy[:2000]}\n\n"
            f"ТЗ (кратко):\n{tech_design[:1200]}\n\nСоставь граф задач.")
    system, _pid = prompt_builder.company_system(
        "ceo_plan", "orchestrator_1", "orchestrator", user)
    raw = await llm.run_agent(
        system=system,
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
    Ключ `_prompt_id` в результате — ссылка на залогированный промпт для сшивки
    Observability (Decision ← промпт, который его вызвал).
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
    # Портфель проектов (BOS §6.2): decide_company — ОТДЕЛЬНЫЙ путь сборки промпта
    # (company_system), не task_context воркера — portfolio_block, добавленный туда
    # для делегированных задач лидеру, сюда не долетал вообще (реальный кейс живого
    # прогона: CEO принимал решения об отделах, ни разу не увидев список проектов).
    directives_section += prompt_builder.portfolio_block("orchestrator")
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

    # goal сериализует слот Brief в системном промпте (единый сериализатор goal≠niche).
    user = (
        f"Стратегия (кратко):\n{strategy[:1500]}\n"
        f"{directives_section}\n"
        f"Этапы пути:\n{ms_text}\n\n"
        f"Отделы сейчас:\n{dept_text}\n\n"
        f"Прими ОДНО решение: open_department (если этап требует новой способности), "
        f"close_department (если цель отдела выполнена), delegate (обновить цель открытого отдела) "
        f"или wait."
    )

    system, pid = prompt_builder.company_system(
        "ceo_company", "orchestrator_1", "orchestrator", user)
    raw = await llm.run_agent(
        system=system,
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
    # prompt_id решения → в Decision (loop читает decision["_prompt_id"]) для сшивки.
    decision["_prompt_id"] = pid
    return decision


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
    system, _pid = prompt_builder.company_system(
        "ceo_board", "orchestrator_1", "orchestrator", user)
    raw = await llm.run_agent(
        system=system,
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


async def generate_initiative(
    goal: str,
    strategy: str,
    opportunity_summary: str,
    publish: Optional[Callable[[dict], Awaitable[None]]] = None,
) -> dict:
    """CEO генерирует проактивную инициативу на основе наблюдаемой возможности."""
    user = (
        f"Стратегия (кратко):\n{strategy[:800]}\n\n"
        f"Наблюдаемая возможность: {opportunity_summary}\n\n"
        "Сформулируй инициативу с конкретными задачами."
    )
    system, _pid = prompt_builder.company_system(
        "ceo_initiative", "orchestrator_1", "orchestrator", user)
    raw = await llm.run_agent(
        system=system,
        user=user,
        model=models_module.for_agent("orchestrator_1"),
        max_tokens=500,
        use_search=False,
        agent_id="orchestrator_1",
    )
    return _parse_json(raw) or {}


async def generate_onboarding_result(
    goal: str,
    strategy: str,
    publish: Optional[Callable[[dict], Awaitable[None]]] = None,
) -> dict:
    """Момент первого впечатления (BOS §5, минимальный онбординг): клиент дал
    пару предложений — офис сразу после стратегии отдаёт аналитику, точки
    роста и 2-3 готовые инициативы на выбор, а не молча начинает работу за
    его спиной. Раньше инициативы рождались ТОЛЬКО реактивно из opportunity-
    событий в циклах CEO — первый визит клиента был пуст."""
    user = (
        f"Цель клиента: {goal[:400]}\n\n"
        f"Стратегия (кратко):\n{strategy[:1200]}\n\n"
        "Дай аналитику, точки роста и 2-3 инициативы для первого шага."
    )
    if publish:
        await publish({"type": "thinking", "agent_id": "orchestrator_1",
                       "text": "Готовлю анализ и первые предложения для клиента..."})
    system, _pid = prompt_builder.company_system(
        "onboarding_result", "orchestrator_1", "orchestrator", user)
    raw = await llm.run_agent(
        system=system,
        user=user,
        model=models_module.for_agent("orchestrator_1"),
        max_tokens=1200,
        use_search=False,
        agent_id="orchestrator_1",
    )
    result = _parse_json(raw)
    if not result:
        return {"analysis": [], "growth_points": [], "initiatives": []}
    result.setdefault("analysis", [])
    result.setdefault("growth_points", [])
    result.setdefault("initiatives", [])
    return result


async def interpret_dashboard_request(text: str) -> dict:
    """Ручная кастомизация бизнес-дашборда: клиент просит график/метрику словами
    ("построй график выручки по месяцам за 12 месяцев"). CEO выбирает ОДНУ из
    реально измеримых метрик (dashboard.available_metrics() — единственный
    источник правды) или честно отказывает с объяснением — никогда не
    выполняет ответ LLM как есть: metric_id/chart_type/group_by всегда
    перепроверяются против whitelist здесь, а не доверяются модели."""
    from src.office import dashboard as dashboard_module
    metrics = dashboard_module.available_metrics()
    now = time.time()
    metrics_block = "\n".join(
        f"- {m['metric_id']}: {m['label']} ({m['unit']}, {m['kind']}), "
        f"данные есть за {max(1, int((now - m['earliest_ts']) / 86400))} дн., точек: {m['count']}"
        for m in metrics
    ) or "(пока вообще нет ни одной измеримой метрики)"
    system, _pid = prompt_builder.company_system(
        "dashboard_widget", "orchestrator_1", "orchestrator", text,
        fmt={"metrics_block": metrics_block})
    raw = await llm.run_agent(
        system=system, user=text,
        model=models_module.for_agent("orchestrator_1"),
        max_tokens=700, use_search=False, agent_id="orchestrator_1",
    )
    result = _parse_json(raw)
    if not result:
        return {"ok": False, "reason": "Не удалось разобрать запрос — переформулируй короче.",
                "suggest_integration": "", "tasks": []}
    if not result.get("ok"):
        # tasks (BOS §4 гибкость сервиса): не просто "нет метрики", а конкретная
        # инициатива, которая сама заведёт метрику — скрипт + повторяющийся
        # процесс + record_metric с НОВЫМ metric_id (не хардкод под сценарий).
        tasks = [t for t in (result.get("tasks") or [])
                 if isinstance(t, dict) and (t.get("title") or "").strip() and (t.get("role") or "").strip()][:4]
        return {"ok": False, "reason": (result.get("reason") or "Не хватает данных для этого графика.")[:300],
                "suggest_integration": (result.get("suggest_integration") or "")[:200], "tasks": tasks}

    valid_ids = {m["metric_id"] for m in metrics}
    metric_id = result.get("metric_id", "")
    if metric_id not in valid_ids:
        return {"ok": False, "reason": f"Метрика «{metric_id}» не найдена среди измеримых.",
                "suggest_integration": ""}
    chart_type = result.get("chart_type") if result.get("chart_type") in dashboard_module.ALLOWED_CHART_TYPES else "line"
    group_by = result.get("group_by") if result.get("group_by") in dashboard_module.ALLOWED_GROUP_BY else "day"
    range_days = result.get("range_days")
    if not isinstance(range_days, (int, float)) or range_days <= 0:
        range_days = 90
    range_days = min(int(range_days), dashboard_module.MAX_RANGE_DAYS)
    title = (result.get("title") or "").strip()[:80] or metric_id
    return {"ok": True, "metric_id": metric_id, "chart_type": chart_type,
            "group_by": group_by, "range_days": range_days, "title": title}


async def classify_recurring(project_title: str, goal: str, tasks_summary: str) -> dict:
    """BOS §5: по завершении Project CEO сам решает — разовый результат (в архив)
    или на самом деле непрерывный цикл (Process, запускается автоматически).
    Возвращает {} при сбое разбора — вызывающий трактует это как «не recurring»,
    а не падает."""
    user = (
        f"Проект: «{project_title}»\nЦель: {goal[:400]}\n\n"
        f"Что делала команда (задачи):\n{tasks_summary[:800]}\n\n"
        "Это разовый результат или непрерывный цикл?"
    )
    system, _pid = prompt_builder.company_system(
        "ceo_process_classify", "orchestrator_1", "orchestrator", user)
    raw = await llm.run_agent(
        system=system,
        user=user,
        model=models_module.for_agent("orchestrator_1"),
        max_tokens=250,
        use_search=False,
        agent_id="orchestrator_1",
    )
    return _parse_json(raw) or {}
