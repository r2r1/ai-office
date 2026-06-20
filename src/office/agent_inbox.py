"""Сообщения между агентами — по тенанту (в памяти)."""

from collections import defaultdict

from src.saas import context as ctx

_inboxes: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))


def send(to_agent_id: str, from_agent_id: str, message: str):
    _inboxes[ctx.get_tenant()][to_agent_id].append({"from": from_agent_id, "text": message})


def read(agent_id: str) -> list[dict]:
    box = _inboxes[ctx.get_tenant()][agent_id]
    msgs = list(box)
    box.clear()
    return msgs
