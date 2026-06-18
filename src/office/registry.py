"""
Реестр всех нанятых агентов. Хранит их роль, статус и номер стола.
"""

from dataclasses import dataclass, field
from typing import Optional

MAX_DESKS = 8

ROLE_COLORS = {
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


def all_agents() -> list[AgentRecord]:
    return list(_agents.values())


def count() -> int:
    return len(_agents)


def has_role(role: str) -> bool:
    return any(a.role == role for a in _agents.values())
