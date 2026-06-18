"""
Event bus — связывает агентов с SSE-потоком браузера.
Каждый подключённый браузер получает свою очередь.
"""

import asyncio
from typing import Any

_subscribers: list[asyncio.Queue] = []


async def publish(event: dict[str, Any]) -> None:
    for q in _subscribers:
        await q.put(event)


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    _subscribers.append(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    try:
        _subscribers.remove(q)
    except ValueError:
        pass
