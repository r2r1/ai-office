"""
Реестр всех нанятых агентов. Хранит их роль, статус и номер стола.
"""

from dataclasses import dataclass, field
from typing import Optional

MAX_DESKS = 8

ROLE_COLORS = {
    "orchestrator": "#ffd54f",
    "researcher": "#4fc3f7",
    "strategist": "#81c784",
    "hr": "#ffb74d",
    "salesman": "#f06292",
    "developer": "#ce93d8",
    "marketer": "#80cbc4",
    "analyst": "#fff176",
}


@dataclass
class AgentRecord:
    agent_id: str
    role: str
    desk: int
    status: str = "idle"   # idle | thinking | done
    last_message: str = ""
    task: str = ""


_agents: dict[str, AgentRecord] = {}
_used_desks: set[int] = set()


def register(agent_id: str, role: str, task: str = "") -> Optional[AgentRecord]:
    if len(_used_desks) >= MAX_DESKS:
        return None
    desk = next(i for i in range(MAX_DESKS) if i not in _used_desks)
    _used_desks.add(desk)
    rec = AgentRecord(agent_id=agent_id, role=role, desk=desk, task=task)
    _agents[agent_id] = rec
    return rec


def update_status(agent_id: str, status: str, message: str = "") -> None:
    if agent_id in _agents:
        _agents[agent_id].status = status
        if message:
            _agents[agent_id].last_message = message[:200]


def get(agent_id: str) -> Optional[AgentRecord]:
    return _agents.get(agent_id)


def all_agents() -> list[AgentRecord]:
    return list(_agents.values())


def count() -> int:
    return len(_agents)


def has_role(role: str) -> bool:
    return any(a.role == role for a in _agents.values())


def restore(saved: list[dict]) -> None:
    """Восстанавливает нанятых ранее агентов после перезапуска сервера."""
    for a in saved:
        aid = a.get("agent_id")
        if not aid or aid in _agents:
            continue
        desk = a.get("desk", 0)
        if desk in _used_desks:
            desk = next((i for i in range(MAX_DESKS) if i not in _used_desks), desk)
        _used_desks.add(desk)
        _agents[aid] = AgentRecord(
            agent_id=aid, role=a.get("role", ""), desk=desk,
            status="done", task=a.get("task", ""),
        )


def reset() -> None:
    _agents.clear()
    _used_desks.clear()
