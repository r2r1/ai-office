"""
Event bus — связывает агентов с SSE-потоком браузера. По тенанту:
событие публикуется только подписчикам своего тенанта.

Аудит docs/technical-due-diligence-2026-07-17.md §2.1: очередь подписчиков
(_subs) живёт в памяти одного процесса — на нескольких серверах браузер,
подключённый к серверу B, никогда не увидел бы событие, опубликованное
сервером A (например, офис-цикл этого тенанта в этот момент ведёт A через
office_lock, а SSE-соединение клиента обслуживает B). Если REDIS_URL задан —
publish() уходит в Redis pub/sub (канал sse:{tid}), и единственный источник
локальной доставки — фоновый listener, слушающий тот же канал (не важно,
кто опубликовал — свой процесс или чужой, путь один). Без REDIS_URL —
прежнее прямое попадание в локальные очереди, поведение не меняется.
"""

import asyncio
import json
from collections import defaultdict
from typing import Any, Optional

from src.office import state
from src.office import trace
from src.saas import context as ctx

_subs: dict[str, list[asyncio.Queue]] = defaultdict(list)
_redis_listener_task: "asyncio.Task | None" = None


async def publish(event: dict[str, Any]) -> None:
    # Терминология BOS §12 п.4 (agent_id → worker_id): «агент» — допустимый внутренний
    # код-термин (bos-architecture.md, глоссарий Worker), но НЕ должен утекать во внешний
    # контракт как единственное имя. Зеркалим worker_id здесь — в ЕДИНОЙ точке, через
    # которую проходят ВСЕ ~40 мест кода, публикующих события — вместо правки каждого
    # publish()-вызова по отдельности. agent_id остаётся deprecated-алиасом на переходный
    # период (1-2 релиза), значения идентичны.
    if event.get("agent_id") and "worker_id" not in event:
        event = {**event, "worker_id": event["agent_id"]}
    tid = ctx.get_tenant()
    state.record(event)      # пользовательская лента (фильтрованные типы) — уже с worker_id
    _trace_event(event)      # детальный системный трейс (ВСЕ типы + время)

    from src.core import redis_client
    r = await redis_client.get_async_client()
    if r is not None:
        try:
            await r.publish(f"sse:{tid}", json.dumps(event, ensure_ascii=False))
            return  # доставка локальным подписчикам — через _redis_listen_loop ниже
        except Exception:
            pass  # Redis моргнул — не теряем событие, доставляем как раньше
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
    _ensure_redis_listener()
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    tid = getattr(q, "_tid", None)
    if tid and q in _subs.get(tid, []):
        _subs[tid].remove(q)


def _ensure_redis_listener() -> None:
    """Запускает фоновый listener Redis pub/sub один раз на процесс, лениво —
    при первой реальной подписке (не при импорте модуля, когда event loop
    ещё может быть не запущен). Без REDIS_URL — no-op, publish() и так пишет
    напрямую в локальные очереди."""
    global _redis_listener_task
    if _redis_listener_task is not None and not _redis_listener_task.done():
        return
    from src.core import redis_client
    if not redis_client.available():
        return
    _redis_listener_task = asyncio.create_task(_redis_listen_loop())


async def _redis_listen_loop() -> None:
    from src.core import redis_client
    r = await redis_client.get_async_client()
    if r is None:
        return
    pubsub = r.pubsub()
    await pubsub.psubscribe("sse:*")
    try:
        async for msg in pubsub.listen():
            if msg.get("type") != "pmessage":
                continue
            channel = msg.get("channel") or ""
            if not channel.startswith("sse:"):
                continue
            tid = channel[len("sse:"):]
            try:
                event = json.loads(msg["data"])
            except (TypeError, ValueError):
                continue
            for q in list(_subs.get(tid, [])):
                await q.put(event)
    finally:
        await pubsub.aclose()
