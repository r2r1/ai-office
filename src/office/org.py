"""
Оргструктура офиса — отделы и их лидеры (C-suite), по тенанту.
Файл: data/tenants/<tid>/departments.json.

Модель реальной компании:
    CEO (orchestrator) управляет ОТДЕЛАМИ (не людьми напрямую).
    Каждый отдел открывается ПО НЕОБХОДИМОСТИ и имеет лидера (CTO/CMO/Head of Sales),
    который управляет своими работниками и видит всё, что они сделали (department_digest).

Штаб стратегии (researcher/strategist/analyst) подчиняется CEO напрямую — это НЕ отдел.
"""

import time

from src.saas import context as ctx
from src.office import registry, state

_FILE = "departments.json"

# Каталог отделов (статический). Лидер открывается вместе с отделом.
DEPARTMENTS = {
    "tech": {
        "name": "Технический отдел", "lead_role": "cto", "lead_title": "CTO",
        "members": ["developer", "integrator", "designer"],
        "hint": "продукт, код, боты, сайты, дизайн, автоматизации, технические интеграции",
    },
    "marketing": {
        "name": "Отдел маркетинга", "lead_role": "cmo", "lead_title": "CMO",
        "members": ["marketer"],
        "hint": "контент, соцсети, реклама, бренд, привлечение аудитории",
    },
    "sales": {
        "name": "Отдел продаж", "lead_role": "sales_lead", "lead_title": "Head of Sales",
        "members": ["salesman"],
        "hint": "поиск клиентов, переговоры, конверсия лидов, CRM",
    },
}

# Все роли-лидеры отделов
LEAD_ROLES = {d["lead_role"] for d in DEPARTMENTS.values()}


def _load() -> dict:
    return ctx.read_json(_FILE, {})


def _save(d: dict) -> None:
    ctx.write_json(_FILE, d)


def catalog() -> dict:
    """Статический каталог отделов."""
    return DEPARTMENTS


def open_department(dept_id: str, reason: str = "", objective: str = "") -> bool:
    """Открывает отдел (или обновляет его цель). Возвращает True, если отдел был открыт впервые."""
    if dept_id not in DEPARTMENTS:
        return False
    d = _load()
    was_open = d.get(dept_id, {}).get("status") == "open"
    d[dept_id] = {
        "status": "open",
        "reason": reason or d.get(dept_id, {}).get("reason", ""),
        "objective": objective or d.get(dept_id, {}).get("objective", ""),
        "opened_ts": d.get(dept_id, {}).get("opened_ts") or time.time(),
    }
    _save(d)
    return not was_open


def set_objective(dept_id: str, objective: str) -> None:
    d = _load()
    if dept_id in d:
        d[dept_id]["objective"] = objective
        _save(d)


def close_department(dept_id: str) -> None:
    d = _load()
    if dept_id in d:
        d[dept_id]["status"] = "closed"
        _save(d)


def is_open(dept_id: str) -> bool:
    return _load().get(dept_id, {}).get("status") == "open"


def open_departments() -> list[str]:
    """ID всех открытых отделов."""
    return [did for did, st in _load().items() if st.get("status") == "open"]


def state_of(dept_id: str) -> dict:
    """Состояние отдела: {status, reason, objective, opened_ts} или пусто."""
    return _load().get(dept_id, {})


def department_of_role(role: str) -> str:
    """К какому отделу относится рабочая роль (или '' для штаба CEO)."""
    for did, info in DEPARTMENTS.items():
        if role in info["members"] or role == info["lead_role"]:
            return did
    return ""


def lead_role(dept_id: str) -> str:
    return DEPARTMENTS.get(dept_id, {}).get("lead_role", "")


def lead_title(dept_id: str) -> str:
    return DEPARTMENTS.get(dept_id, {}).get("lead_title", "")


def member_roles(dept_id: str) -> list[str]:
    return list(DEPARTMENTS.get(dept_id, {}).get("members", []))


def lead_id(dept_id: str) -> str:
    """agent_id лидера отдела, если он нанят, иначе ''."""
    role = lead_role(dept_id)
    for a in registry.all_agents():
        if a.role == role:
            return a.agent_id
    return ""


def department_digest(dept_id: str) -> str:
    """
    Дайджест всего, что сделали члены отдела — «видимость лидера».
    Строки вида: «- developer_1 [🟢свободен/🔴думает]: <последний результат>».
    """
    info = DEPARTMENTS.get(dept_id)
    if not info:
        return ""
    members = set(info["members"])
    lines = []
    for a in registry.all_agents():
        if a.role not in members:
            continue
        status_mark = "🔴думает" if a.status == "thinking" else "🟢свободен"
        last = state.result_for(a.agent_id)
        last_short = (last[:120] + "…") if last and len(last) > 120 else (last or "ещё не сдавал")
        lines.append(f"- {a.agent_id} ({a.role}) [{status_mark}]: {last_short}")
    return "\n".join(lines) or "в отделе пока нет работников"


def reset() -> None:
    ctx.delete_file(_FILE)
