"""
Лидеры отделов (CTO / CMO / Head of Sales) — управляют своими работниками.

В отличие от CEO (orchestrator.decide_company — управляет ОТДЕЛАМИ), лидер принимает
решение ВНУТРИ своего отдела: кому из подчинённых что поручить или кого нанять.
Лидер видит дайджест всего, что сделали его подчинённые (org.department_digest) —
это «видимость лидера вниз по иерархии».
"""

import json
from typing import Optional, Callable, Awaitable

from src.core import llm
from src.office import registry, models as models_module, org as org_module
from src.agents.orchestrator import _parse_json

_LEADER_SYSTEM = """Ты — руководитель отдела в автономной AI-компании ({title}). CEO поставил
твоему отделу цель. Ты НЕ делаешь работу руками — ты управляешь подчинёнными: на каждом ходу
принимаешь ОДНО решение — поручить задачу свободному работнику, нанять отсутствующего работника
своего отдела или подождать.

Работники твоего отдела и их зоны: {roles_desc}

Принципы:
- Двигай отдел к цели от CEO. Ставь конкретные, выполнимые задачи с измеримым результатом.
- Не повторяй задачи, которые работник уже сделал или делает прямо сейчас.
- ЕДИНАЯ ОТВЕТСТВЕННОСТЬ: на каждую роль ОДИН работник. Если нужный занят — wait, не клонируй.
- Если нужной роли нет в отделе — найми (только из ролей своего отдела).
- Все API-ключи доступны любому через get_connection — не выбирай работника «потому что у него ключ».

Ответь ТОЛЬКО валидным JSON без markdown:
{{
  "thought": "краткая мысль (1 предложение, по-русски)",
  "action": "assign" | "hire" | "wait",
  "agent_id": "id работника для assign (например developer_1)",
  "role": "роль для hire (одна из ролей отдела)",
  "task": "конкретная задача (для assign или hire)",
  "skill": "специализация при найме, иначе null",
  "report": "краткий отчёт для CEO о состоянии отдела"
}}"""

_ROLE_DESC = {
    "developer": "developer — КАСТОМНЫЙ код (НЕ нужен для обычного бота записи), сайты, автоматизации",
    "integrator": "integrator — реальные действия во внешних сервисах + ЗАПУСК готового бота записи (launch_bot)",
    "architect": "architect — техническое проектирование, ТЗ",
    "marketer": "marketer — контент, посты, реклама, бренд",
    "salesman": "salesman — поиск клиентов, офферы, переговоры, CRM",
    "analyst": "analyst — аналитика, метрики, отчёты",
}

# Доп. правила маршрутизации для конкретных отделов (подмешиваются в решение лидера).
_DEPT_HINTS = {
    "tech": (
        "\n\nМАРШРУТИЗАЦИЯ TELEGRAM-БОТА (СТРОГО):\n"
        "- Бот ЗАПИСИ КЛИЕНТОВ / сбора лидов → ТОЛЬКО ИНТЕГРАТОРУ. Платформа имеет готовый "
        "движок записи. Интегратор предложит его клиенту, настроит услуги и запустит (launch_bot). "
        "НЕ нанимай developer и НЕ поручай ему код для бота записи НИКОГДА — даже если "
        "интегратор несколько циклов ждёт или не с первого раза. Жди интегратора.\n"
        "- Если integrator завершил задачу и launch_bot вернул 'ЗАПУЩЕН'/'enabled'/'polling' — "
        "цель отдела ВЫПОЛНЕНА. Можешь доложить CEO через report.\n"
        "- Бот с НЕСТАНДАРТНОЙ логикой (постинг в группу, парсинг, кастом) → разработчику, "
        "только если пользователь явно отверг готового бота записи.\n"
        "- Если все подчинённые в cooldown (выполняют задачу) — верни action=wait, не нанимай дублёров."
    ),
}


async def decide(
    dept_id: str,
    goal: str,
    objective: str,
    milestones: list[dict],
    agent_availability: Optional[dict] = None,
    publish: Optional[Callable[[dict], Awaitable[None]]] = None,
) -> dict:
    """Решение лидера отдела: кому из подчинённых что поручить (или кого нанять)."""
    avail = agent_availability or {}
    member_roles = org_module.member_roles(dept_id)
    lead_id = org_module.lead_id(dept_id)

    members = registry.members_of(dept_id)
    # Какие роли отдела уже укомплектованы
    existing_roles = {a.role for a in members}
    missing_roles = [r for r in member_roles if r not in existing_roles]

    # Сводка по подчинённым с доступностью (дайджест = видимость лидера)
    digest = org_module.department_digest(dept_id)

    ms_lines = [f"- [{m['status']}] {m['id']}: {m['title']}" for m in milestones]
    ms_text = "\n".join(ms_lines) or "этапы ещё не заданы"

    roles_desc = "; ".join(_ROLE_DESC.get(r, r) for r in member_roles)
    title = org_module.lead_title(dept_id)

    # Указания пользователя — приоритетнее цели отдела (например «запусти бота»)
    from src.office import memory as memory_module
    user_directives = memory_module.context_block() or ""
    directives_section = (
        f"\n=== УКАЗАНИЯ ПОЛЬЗОВАТЕЛЯ (ПРИОРИТЕТ) ===\n{user_directives}\n"
        if user_directives.strip() else ""
    )

    if publish and lead_id:
        await publish({"type": "thinking", "agent_id": lead_id,
                       "text": f"Распределяю работу в отделе «{org_module.catalog()[dept_id]['name']}»..."})

    user = (
        f"Цель компании: {goal}\n"
        f"Цель твоего отдела от CEO: {objective or 'двигай отдел к цели компании'}\n"
        f"{directives_section}\n"
        f"Этапы пути:\n{ms_text}\n\n"
        f"Твои подчинённые (статус и что сделали):\n{digest}\n\n"
        f"Роли отдела, которых ещё НЕТ (можно нанять): {', '.join(missing_roles) or 'все на месте'}\n\n"
        f"Прими ОДНО решение: assign (поручить свободному), hire (нанять отсутствующую роль отдела) или wait."
    )

    raw = await llm.run_agent(
        system=_LEADER_SYSTEM.format(title=title, roles_desc=roles_desc) + _DEPT_HINTS.get(dept_id, ""),
        user=user,
        model=models_module.for_agent(lead_id or "orchestrator_1"),
        max_tokens=600,
        use_search=False,
        agent_id=lead_id or "orchestrator_1",
    )
    decision = _parse_json(raw)
    if not decision:
        # Модель не вернула валидный JSON — пробуем угадать action из текста
        raw_l = (raw or "").lower()
        if "hire" in raw_l or "нанять" in raw_l or "нани" in raw_l:
            return {"action": "wait", "thought": "Нечёткий ответ лидера (hint: hire) — жду"}
        return {"action": "wait", "thought": "Лидер не смог принять решение — жду"}

    action = decision.get("action", "wait")

    if action == "hire":
        role = decision.get("role", "")
        if role not in member_roles:
            return {"action": "wait", "thought": f"Роль {role} не из этого отдела — жду"}
        if any(a.role == role for a in members):
            return {"action": "wait", "thought": f"{role} уже в отделе — жду освобождения"}

    elif action == "assign":
        aid = decision.get("agent_id", "")
        rec = registry.get(aid)
        # Работник должен принадлежать этому отделу
        if rec is None or rec.department != dept_id:
            role_hint = decision.get("role", "")
            match = next((a for a in members if a.role == role_hint), None)
            if match:
                decision["agent_id"] = match.agent_id
                rec = match
            else:
                return {"action": "wait", "thought": "Указан чужой/несуществующий работник — жду"}
        # Если выбранный занят — ищем свободного той же роли в отделе
        if rec and avail.get(rec.agent_id, {}).get("on_cooldown"):
            free = next(
                (a for a in members if a.role == rec.role
                 and not avail.get(a.agent_id, {}).get("on_cooldown")),
                None,
            )
            if free:
                decision["agent_id"] = free.agent_id
            else:
                return {"action": "wait",
                        "thought": f"{rec.role} занят — жду результат, не дублирую"}

    return decision
