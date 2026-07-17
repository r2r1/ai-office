"""
Юнит-тесты SSE-шины через Redis pub/sub (src/office/bus.py).

Межпроцессная проверка против реального Redis (два независимых python-
процесса — один публикует, другой подписан и получает через pub/sub)
сделана вручную (см. коммит) — здесь юнит-тесты на моках, CI без реального
Redis, $0.

    python tests/test_bus_redis.py
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from src.core import redis_client
from src.saas import context as ctx
from src.office import bus


def _run_async(coro):
    return asyncio.run(coro)


def test_publish_without_redis_delivers_to_local_queue(monkeypatch):
    async def _no_redis():
        return None
    monkeypatch.setattr(redis_client, "get_async_client", _no_redis)
    ctx.set_tenant("bus_test_local")
    bus._subs.pop("bus_test_local", None)

    async def _scenario():
        q = bus.subscribe()
        await bus.publish({"type": "probe", "text": "local"})
        ev = await asyncio.wait_for(q.get(), timeout=2)
        bus.unsubscribe(q)
        return ev

    ev = _run_async(_scenario())
    assert ev["type"] == "probe"
    assert ev["text"] == "local"


def test_publish_with_redis_calls_publish_not_local_queue(monkeypatch):
    """При доступном Redis publish() уходит в r.publish(), а НЕ напрямую в
    локальную очередь — доставка только через _redis_listen_loop."""
    fake_redis = MagicMock()
    fake_redis.publish = AsyncMock()

    async def _fake_get_async_client():
        return fake_redis
    monkeypatch.setattr(redis_client, "get_async_client", _fake_get_async_client)

    ctx.set_tenant("bus_test_redis")
    bus._subs.pop("bus_test_redis", None)

    async def _scenario():
        # напрямую добавляем очередь в _subs, минуя subscribe() — тот запускает
        # реальный _ensure_redis_listener(), который в юнит-тесте не нужен
        # (проверяем только publish(), не полный listener-цикл)
        import asyncio as _a
        q = _a.Queue()
        q._tid = "bus_test_redis"
        bus._subs["bus_test_redis"].append(q)
        await bus.publish({"type": "probe", "text": "via redis"})
        return q

    q = _run_async(_scenario())
    fake_redis.publish.assert_called_once()
    channel, payload = fake_redis.publish.call_args[0]
    assert channel == "sse:bus_test_redis"
    assert "via redis" in payload
    assert q.empty()  # НЕ попало напрямую в очередь — только через publish() в Redis
    bus._subs.pop("bus_test_redis", None)


def test_publish_falls_back_to_local_when_redis_publish_fails(monkeypatch):
    """Redis моргнул на самой публикации — событие не должно теряться."""
    fake_redis = MagicMock()
    fake_redis.publish = AsyncMock(side_effect=ConnectionError("boom"))

    async def _fake_get_async_client():
        return fake_redis
    monkeypatch.setattr(redis_client, "get_async_client", _fake_get_async_client)

    ctx.set_tenant("bus_test_fallback")
    bus._subs.pop("bus_test_fallback", None)

    async def _scenario():
        import asyncio as _a
        q = _a.Queue()
        q._tid = "bus_test_fallback"
        bus._subs["bus_test_fallback"].append(q)
        await bus.publish({"type": "probe", "text": "fallback"})
        return await asyncio.wait_for(q.get(), timeout=2)

    ev = _run_async(_scenario())
    assert ev["text"] == "fallback"
    bus._subs.pop("bus_test_fallback", None)


def _run():
    import inspect
    passed = 0

    class FakeMonkeypatch:
        def __init__(self):
            self._saved_attrs = []

        def setattr(self, obj, name, value):
            self._saved_attrs.append((obj, name, getattr(obj, name)))
            setattr(obj, name, value)

        def undo(self):
            for obj, name, old in reversed(self._saved_attrs):
                setattr(obj, name, old)

    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            mp = FakeMonkeypatch()
            try:
                sig = inspect.signature(fn)
                if "monkeypatch" in sig.parameters:
                    fn(mp)
                else:
                    fn()
                print(f"  ✓ {name}")
                passed += 1
            finally:
                mp.undo()
                redis_client.reset_for_tests()
    print(f"ВСЕ {passed} ТЕСТОВ ПРОШЛИ")


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    _run()
