"""
Event bus — связывает агентов с SSE-потоком браузера. По тенанту:
событие публикуется только подписчикам своего тенанта.
"""

import asyncio
from collections import defaultdict
from typing import Any, Optional

from src.office import state
from src.office import trace
from src.saas import context as ctx

_subs: dict[str, list[asyncio.Queue]] = defaultdict(list)


async def publish(event: dict[str, Any]) -> None:
    tid = ctx.get_tenant()
    state.record(event)      # пользовательская лента (фильтрованные типы)
    _trace_event(event)      # детальный системный трейс (ВСЕ типы + время)
    for q in list(_subs.get(tid, [])):
        await q.put(event)


def _trace_event(event: dict[str, Any]) -> None:
    """Любое событие шины уходит в детальный трейс с временной меткой."""
    etype = event.get("type", "")
    fields: dict[str, Any] = {}
    if event.get("agent_id"):
        fields["agent"] = event["agent_id"]
    # ⚠️ Ключи НЕ должны конфликтовать с позиционным параметром trace.log(kind, ...):
    # событие несёт своё поле "kind" → кладём его как "ev_kind", иначе TypeError
    # "log() got multiple values for argument 'kind'" ронял publish и задачу агента.
    remap = {"kind": "ev_kind", "from": "sender"}
    for k in ("text", "summary", "integration", "action", "skill",
              "platform", "error", "from", "kind", "question_id"):
        v = event.get(k)
        if v not in (None, ""):
            fields[remap.get(k, k)] = v
    trace.log(f"evt:{etype}", **fields)


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
