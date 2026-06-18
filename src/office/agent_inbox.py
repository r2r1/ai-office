import asyncio
from collections import defaultdict

_inboxes: dict[str, list[dict]] = defaultdict(list)
_waiters: dict[str, list[asyncio.Future]] = defaultdict(list)

def send(to_agent_id: str, from_agent_id: str, message: str):
    msg = {"from": from_agent_id, "text": message}
    _inboxes[to_agent_id].append(msg)
    for fut in _waiters.pop(to_agent_id, []):
        if not fut.done():
            fut.set_result(msg)

def read(agent_id: str) -> list[dict]:
    msgs = list(_inboxes[agent_id])
    _inboxes[agent_id].clear()
    return msgs
