"""
Event bus — связывает агентов с SSE-потоком браузера. По тенанту:
событие публикуется только подписчикам своего тенанта.
"""

import asyncio
from collections import defaultdict
from typing import Any, Optional

from src.office import state
from src.saas import context as ctx

_subs: dict[str, list[asyncio.Queue]] = defaultdict(list)


async def publish(event: dict[str, Any]) -> None:
    tid = ctx.get_tenant()
    state.record(event)  # история текущего тенанта
    for q in list(_subs.get(tid, [])):
        await q.put(event)


def subscribe(tid: Optional[str] = None) -> asyncio.Queue:
    tid = tid or ctx.get_tenant()
    q: asyncio.Queue = asyncio.Queue()
    q._tid = tid  # type: ignore[attr-defined]
    _subs[tid].append(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    tid = getattr(q, "_tid", None)
    if tid and q in _subs.get(tid, []):
        _subs[tid].remove(q)
