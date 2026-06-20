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
}


@dataclass
class AgentRecord:
    agent_id: str
    role: str
    desk: int
    status: str = "idle"
    last_message: str = ""
    task: str = ""


def _load() -> dict:
    return ctx.read_json(_FILE, {})


def _save(d: dict) -> None:
    ctx.write_json(_FILE, d)


def _rec(d: dict) -> AgentRecord:
    return AgentRecord(agent_id=d["agent_id"], role=d.get("role", ""), desk=d.get("desk", 0),
                       status=d.get("status", "idle"), last_message=d.get("last_message", ""),
                       task=d.get("task", ""))


def register(agent_id: str, role: str, task: str = "") -> Optional[AgentRecord]:
    agents = _load()
    used = {a.get("desk", 0) for a in agents.values()}
    desk = next(i for i in range(MAX_DESKS) if i not in used)
    agents[agent_id] = {"agent_id": agent_id, "role": role, "desk": desk,
                        "status": "idle", "last_message": "", "task": task}
    _save(agents)
    return _rec(agents[agent_id])


def update_status(agent_id: str, status: str, message: str = "") -> None:
    agents = _load()
    if agent_id in agents:
        agents[agent_id]["status"] = status
        if message:
            agents[agent_id]["last_message"] = message[:200]
        _save(agents)


def get(agent_id: str) -> Optional[AgentRecord]:
    a = _load().get(agent_id)
    return _rec(a) if a else None


def all_agents() -> list[AgentRecord]:
    return [_rec(a) for a in _load().values()]


def count() -> int:
    return len(_load())


def has_role(role: str) -> bool:
    return any(a.get("role") == role for a in _load().values())


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
