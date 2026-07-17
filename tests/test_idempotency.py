"""
Юнит-тесты идемпотентности (routers/shared.py:idempotent).

Живая проверка против реального Redis и реального эндпоинта
/api/initiative/{iid}/accept сделана вручную (см. коммит) — здесь юнит-тесты
на моках, CI без реального Redis, $0.

    python tests/test_idempotency.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from src.core import redis_client
from routers import shared


def _run_async(coro):
    return asyncio.run(coro)


def test_empty_key_always_calls_compute(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    redis_client.reset_for_tests()
    calls = {"n": 0}

    async def compute():
        calls["n"] += 1
        return {"n": calls["n"]}

    async def _scenario():
        r1 = await shared.idempotent("ns", "", 5, compute)
        r2 = await shared.idempotent("ns", "", 5, compute)
        return r1, r2

    r1, r2 = _run_async(_scenario())
    assert r1 == {"n": 1}
    assert r2 == {"n": 2}  # ключа нет — дедупликации нет, compute зовётся оба раза


def test_same_key_deduplicates_without_redis(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    redis_client.reset_for_tests()
    shared._idem_memory.clear()
    calls = {"n": 0}

    async def compute():
        calls["n"] += 1
        return {"n": calls["n"]}

    async def _scenario():
        r1 = await shared.idempotent("ns_mem", "same", 5, compute)
        r2 = await shared.idempotent("ns_mem", "same", 5, compute)
        return r1, r2

    r1, r2 = _run_async(_scenario())
    assert r1 == r2 == {"n": 1}
    assert calls["n"] == 1  # второй вызов НЕ выполнил compute() снова


def test_different_keys_do_not_share_cache(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    redis_client.reset_for_tests()
    shared._idem_memory.clear()
    calls = {"n": 0}

    async def compute():
        calls["n"] += 1
        return {"n": calls["n"]}

    async def _scenario():
        r1 = await shared.idempotent("ns_diff", "key_a", 5, compute)
        r2 = await shared.idempotent("ns_diff", "key_b", 5, compute)
        return r1, r2

    r1, r2 = _run_async(_scenario())
    assert r1 != r2
    assert calls["n"] == 2


def test_non_dict_result_is_not_cached(monkeypatch):
    """Response-объекты (например JSONResponse для ветки ошибки) не кешируются —
    только сериализуемые dict/list результаты."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    redis_client.reset_for_tests()
    shared._idem_memory.clear()
    calls = {"n": 0}

    class FakeResponse:
        def __init__(self, n):
            self.n = n

    async def compute():
        calls["n"] += 1
        return FakeResponse(calls["n"])

    async def _scenario():
        r1 = await shared.idempotent("ns_resp", "same", 5, compute)
        r2 = await shared.idempotent("ns_resp", "same", 5, compute)
        return r1, r2

    r1, r2 = _run_async(_scenario())
    assert r1.n == 1
    assert r2.n == 2  # не закешировалось — compute() позвался снова
    assert calls["n"] == 2


def _run():
    import inspect
    passed = 0

    class FakeMonkeypatch:
        def __init__(self):
            self._saved_env = {}

        def delenv(self, name, raising=True):
            import os
            self._saved_env[name] = os.environ.pop(name, None)

        def undo(self):
            import os
            for k, v in self._saved_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

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
