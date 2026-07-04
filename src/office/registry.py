"""
Реестр нанятых агентов (роль, статус, стол) — по тенанту.
Файл: data/tenants/<tid>/agents.json.
"""

from dataclasses import dataclass
from typing import Optional

from src.saas import context as ctx

_FILE = "agents.json"
MAX_DESKS = 200

ROLE_COLORS = {
    "orchestrator": "#ffd54f", "researcher": "#4fc3f7", "strategist": "#81c784",
    "hr": "#ffb74d", "salesman": "#f06292", "developer": "#ce93d8",
    "marketer": "#80cbc4", "analyst": "#fff176", "integrator": "#4dd0e1",
    # Лидеры отделов (C-suite)
    "cto": "#9575cd", "cmo": "#4db6ac", "sales_lead": "#ec407a",
}


@dataclass
class AgentRecord:
    agent_id: str
    role: str
    desk: int
    status: str = "idle"
    last_message: str = ""
    task: str = ""
    department: str = ""   # id отдела ('' = штаб CEO)
    manager: str = ""      # agent_id руководителя ('' = подчиняется CEO)
    paused: bool = False   # поставлен на паузу вручную (см. pause()/resume())


def _load() -> dict:
    return ctx.read_json(_FILE, {})


def _save(d: dict) -> None:
    ctx.write_json(_FILE, d)


def _rec(d: dict) -> AgentRecord:
    return AgentRecord(agent_id=d["agent_id"], role=d.get("role", ""), desk=d.get("desk", 0),
                       status=d.get("status", "idle"), last_message=d.get("last_message", ""),
                       task=d.get("task", ""), department=d.get("department", ""),
                       manager=d.get("manager", ""), paused=d.get("paused", False))


def register(agent_id: str, role: str, task: str = "",
             department: str = "", manager: str = "") -> Optional[AgentRecord]:
    agents = _load()
    used = {a.get("desk", 0) for a in agents.values()}
    desk = next(i for i in range(MAX_DESKS) if i not in used)
    agents[agent_id] = {"agent_id": agent_id, "role": role, "desk": desk,
                        "status": "idle", "last_message": "", "task": task,
                        "department": department, "manager": manager}
    _save(agents)
    return _rec(agents[agent_id])


def update_status(agent_id: str, status: str, message: str = "") -> None:
    agents = _load()
    if agent_id in agents:
        agents[agent_id]["status"] = status
        if message:
            agents[agent_id]["last_message"] = message[:200]
        _save(agents)


def pause(agent_id: str) -> bool:
    """Ставит ОДНОГО сотрудника на паузу (в отличие от office/control.py —
    это пауза всей компании). Пока агент на паузе, лидер отдела не должен
    предлагать ему новых задач (см. planning_engine.free_worker_of_role)."""
    agents = _load()
    if agent_id not in agents:
        return False
    agents[agent_id]["paused"] = True
    _save(agents)
    return True


def resume(agent_id: str) -> bool:
    agents = _load()
    if agent_id not in agents:
        return False
    agents[agent_id]["paused"] = False
    _save(agents)
    return True


def is_paused(agent_id: str) -> bool:
    return bool(_load().get(agent_id, {}).get("paused", False))


def reset_stuck_statuses() -> list[str]:
    """
    Сбрасывает в idle всех агентов, зависших в 'thinking' (их задачи убил рестарт).
    Возвращает id сброшенных — иначе лидер считает их занятыми и не переназначает.
    """
    agents = _load()
    reset = []
    for aid, a in agents.items():
        if a.get("status") == "thinking":
            a["status"] = "idle"
            reset.append(aid)
    if reset:
        _save(agents)
    return reset


def get(agent_id: str) -> Optional[AgentRecord]:
    a = _load().get(agent_id)
    return _rec(a) if a else None


def all_agents() -> list[AgentRecord]:
    return [_rec(a) for a in _load().values()]


def count() -> int:
    return len(_load())


def has_role(role: str) -> bool:
    return any(a.get("role") == role for a in _load().values())


def members_of(department: str) -> list[AgentRecord]:
    """Все агенты отдела (по полю department)."""
    return [_rec(a) for a in _load().values() if a.get("department") == department]


def by_manager(manager_id: str) -> list[AgentRecord]:
    """Все прямые подчинённые руководителя."""
    return [_rec(a) for a in _load().values() if a.get("manager") == manager_id]


def restore(saved: list[dict]) -> None:
    agents = _load()
    used = {a.get("desk", 0) for a in agents.values()}
    for a in saved:
        aid = a.get("agent_id")
        if not aid or aid in agents:
            continue
        desk = a.get("desk", 0)
        if desk in used:
            desk = next(i for i in range(MAX_DESKS) if i not in used)
        used.add(desk)
        agents[aid] = {"agent_id": aid, "role": a.get("role", ""), "desk": desk,
                       "status": "done", "last_message": "", "task": a.get("task", "")}
    _save(agents)


def reset() -> None:
    ctx.delete_file(_FILE)
