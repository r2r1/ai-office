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

# Каталог отделов (статический метаданные). Лидер открывается вместе с отделом.
# Состав отдела (кто-рабочие роли) НЕ хранится здесь списком — вычисляется из
# roles.ROLE_META (там у каждой роли уже есть "department"), иначе принадлежность
# роли к отделу задавалась бы в двух местах и могла разойтись (см. member_roles()).
DEPARTMENTS = {
    "tech": {
        "name": "Технический отдел", "lead_role": "cto", "lead_title": "CTO",
        "hint": "продукт, код, боты, сайты, дизайн, автоматизации, технические интеграции",
    },
    "marketing": {
        "name": "Отдел маркетинга", "lead_role": "cmo", "lead_title": "CMO",
        "hint": "контент, соцсети, реклама, бренд, привлечение аудитории",
    },
    "sales": {
        "name": "Отдел продаж", "lead_role": "sales_lead", "lead_title": "Head of Sales",
        "hint": "поиск клиентов, переговоры, конверсия лидов, CRM",
    },
    # Учёт/ERP — отдельный от sales класс задач (CRM ≠ бухгалтерия, см. erp_1c.py
    # docstring). Раньше модулю вроде 1С физически некуда было принадлежать —
    # любая роль могла его дёрнуть без разбора (см. Integration.department).
    "finance": {
        "name": "Финансовый отдел", "lead_role": "cfo", "lead_title": "CFO",
        "hint": "учёт, ERP/1С, юнит-экономика, финансовая отчётность",
    },
}

# Все роли-лидеры отделов
LEAD_ROLES = {d["lead_role"] for d in DEPARTMENTS.values()}

# Иерархия доступа (BOS §6.2): роли, чья зона ответственности ШИРЕ одного проекта
# и которые потому видят бизнес насквозь — CEO, лидеры отделов и надпроектные
# сервисные роли (архитектор проектирует по всем проектам, стратег/ресёрчер держат
# картину бизнеса целиком, hr нанимает под общую структуру). Рядовой воркер сюда
# НЕ входит — он заперт в своём project_dir. Единый источник правды и для гейта
# портфельных инструментов (agent_factory), и для портфельного слота промпта
# (prompt_builder) — иначе набор инструментов и текст промпта могли бы разойтись.
_PORTFOLIO_SERVICE_ROLES = {"orchestrator", "architect", "strategist", "researcher", "hr"}


def is_portfolio_role(role: str) -> bool:
    """Видит ли роль портфель целиком (все проекты тенанта на чтение)."""
    return role in _PORTFOLIO_SERVICE_ROLES or role in LEAD_ROLES


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
    """К какому отделу относится роль (рабочая или лидер), или '' для штаба CEO.
    Источник данных один — roles.department_of (было продублировано здесь)."""
    from src.office import roles as roles_module
    return roles_module.department_of(role)


def lead_role(dept_id: str) -> str:
    return DEPARTMENTS.get(dept_id, {}).get("lead_role", "")


def lead_title(dept_id: str) -> str:
    return DEPARTMENTS.get(dept_id, {}).get("lead_title", "")


def member_roles(dept_id: str) -> list[str]:
    """Рабочие роли отдела (БЕЗ лидера) — вычисляется из roles.ROLE_META."""
    from src.office import roles as roles_module
    lead = lead_role(dept_id)
    return [r for r in roles_module.roles_in_department(dept_id) if r != lead]


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
    if dept_id not in DEPARTMENTS:
        return ""
    members = set(member_roles(dept_id))
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
