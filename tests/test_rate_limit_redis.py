"""
Юнит-тесты Redis-режима rate-limit (routers/shared.py + src/core/redis_client.py).

Аудит docs/technical-due-diligence-2026-07-17.md §2.1/§5.5: in-memory rate-limit
не работает на нескольких серверах (каждый считает свой лимит независимо).
Живая двухпроцессная проверка против реального Redis сделана вручную (см.
коммит) — здесь юнит-тесты на моках, чтобы CI не требовал реального Redis
($0, без внешних зависимостей, как остальной tests/run_all.py).

    python tests/test_rate_limit_redis.py
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# routers/shared.py импортирует src.saas.auth, который резолвит APP_SECRET из
# .env при импорте модуля (см. server.py — тот же порядок: load_dotenv() ДО
# импорта чего-либо из src.saas).
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from src.core import redis_client
from routers import shared


def _fresh_memory_buckets():
    shared._rate_buckets.clear()


def test_without_redis_url_falls_back_to_memory(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    redis_client.reset_for_tests()
    assert redis_client.get_client() is None


def test_memory_branch_allows_up_to_limit_then_blocks(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    redis_client.reset_for_tests()
    _fresh_memory_buckets()
    results = [shared.rate_limited("t_mem", "k", 5) for _ in range(7)]
    assert results == [False, False, False, False, False, True, True]


def test_redis_branch_used_when_client_available(monkeypatch):
    """Мок вместо реального Redis — проверяем, что ветка ВЫБИРАЕТСЯ правильно
    (available() -> True переключает rate_limited на _rate_limited_redis),
    не саму семантику ZSET (та проверена вручную живым Redis)."""
    fake_client = MagicMock()
    fake_pipe = MagicMock()
    fake_client.pipeline.return_value = fake_pipe
    fake_pipe.execute.return_value = [0, 2]  # zremrangebyscore, zcard -> count=2

    monkeypatch.setattr(redis_client, "get_client", lambda: fake_client)

    blocked = shared.rate_limited("t_redis", "k", 5)
    assert blocked is False
    fake_client.zadd.assert_called_once()
    fake_client.expire.assert_called_once()


def test_redis_branch_blocks_when_count_at_limit(monkeypatch):
    fake_client = MagicMock()
    fake_pipe = MagicMock()
    fake_client.pipeline.return_value = fake_pipe
    fake_pipe.execute.return_value = [0, 5]  # count == max_per_min

    monkeypatch.setattr(redis_client, "get_client", lambda: fake_client)

    blocked = shared.rate_limited("t_redis2", "k", 5)
    assert blocked is True
    fake_client.zadd.assert_not_called()  # заблокированная попытка не засчитывается


def test_get_client_returns_none_without_redis_package_or_url(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    redis_client.reset_for_tests()
    assert redis_client.available() is False


def _run():
    import inspect
    passed = 0

    class FakeMonkeypatch:
        def __init__(self):
            self._saved_env = {}
            self._saved_attrs = []

        def delenv(self, name, raising=True):
            import os
            self._saved_env[name] = os.environ.pop(name, None)

        def setattr(self, obj, name, value):
            self._saved_attrs.append((obj, name, getattr(obj, name)))
            setattr(obj, name, value)

        def undo(self):
            import os
            for k, v in self._saved_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
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
