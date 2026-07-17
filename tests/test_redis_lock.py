"""
Юнит-тесты примитивов распределённого лока (src/core/redis_client.py).

Двухпроцессная проверка против реального Redis (два независимых python-
процесса, борющихся за один лок) сделана вручную (см. коммит) — здесь
юнит-тесты на моках, CI без реального Redis, $0.

    python tests/test_redis_lock.py
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from src.core import redis_client


def test_try_acquire_without_redis_returns_empty_token(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    redis_client.reset_for_tests()
    token = redis_client.try_acquire_lock("k", 5)
    assert token == ""  # "" — не None: значит "локов нет, работай как раньше"


def test_renew_without_redis_always_true():
    assert redis_client.renew_lock("k", "", 5) is True


def test_release_without_redis_does_not_raise():
    redis_client.release_lock("k", "")  # не должно бросить исключение


def test_try_acquire_uses_set_nx_px(monkeypatch):
    fake_client = MagicMock()
    fake_client.set.return_value = True
    monkeypatch.setattr(redis_client, "get_client", lambda: fake_client)

    token = redis_client.try_acquire_lock("mylock", 10)
    assert token != "" and token is not None
    args, kwargs = fake_client.set.call_args
    assert kwargs.get("nx") is True
    assert kwargs.get("px") == 10000


def test_try_acquire_returns_none_when_key_taken(monkeypatch):
    fake_client = MagicMock()
    fake_client.set.return_value = False  # NX не сработал — уже занято
    monkeypatch.setattr(redis_client, "get_client", lambda: fake_client)

    token = redis_client.try_acquire_lock("mylock", 10)
    assert token is None


def test_renew_calls_lua_with_token(monkeypatch):
    fake_client = MagicMock()
    fake_client.eval.return_value = 1
    monkeypatch.setattr(redis_client, "get_client", lambda: fake_client)

    ok = redis_client.renew_lock("mylock", "tok123", 10)
    assert ok is True
    fake_client.eval.assert_called_once()
    args = fake_client.eval.call_args[0]
    assert "mylock" in args
    assert "tok123" in args


def test_release_calls_lua_with_token(monkeypatch):
    fake_client = MagicMock()
    monkeypatch.setattr(redis_client, "get_client", lambda: fake_client)

    redis_client.release_lock("mylock", "tok123")
    fake_client.eval.assert_called_once()
    args = fake_client.eval.call_args[0]
    assert "mylock" in args
    assert "tok123" in args


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
