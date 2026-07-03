"""
Orchestrator (CEO) — вершина иерархии офиса.

Он НЕ делает работу руками и НЕ ставит задачи людям — задачи распределяет
детерминированная маршрутизация плана (loop._run_leaders). Что осталось за CEO:
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
from typing import Optional, Callable, Awaitable

from src.core import llm
from src.office import models as models_module, org as org_module
from src.office import prompt_builder

# Документированный инвариант «на роль — один агент» (CLAUDE.md §3.2). Enforcement
# живёт в call-sites: registry.has_role (_hire_leader), leaders.decide («уже в отделе»),
# детерминированная маршрутизация loop._run_leaders. Прежний LLM-решатель уровня
# агентов (decide) удалён как мёртвый код — plan-driven цикл его не вызывал.
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
    # niche/audience/goal сериализует слот Brief в системном промпте (единый
    # сериализатор), здесь — только оперативный контекст этого хода.
    user = (
        f"Стратегия (кратко):\n{strategy[:500]}\n\n"
        f"Этапы сейчас:\n{ms_text}\n\n"
        f"Отделы:\n{departments_text or '(отделов пока нет)'}\n\n"
        f"Доска задач: {board_summary or '(пусто)'}\n\n"
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
