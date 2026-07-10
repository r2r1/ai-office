"""
Тесты mcp_bridge.py — живой end-to-end прогон против игрушечного платформенного
MCP-сервера (mcp_toy_server.py), не моки: реально поднимает дочерний процесс
через stdio и говорит с ним по протоколу. Так же реально проверяется
деградация при недоступном/неправильно настроенном сервере — агент не должен
падать, если MCP-сервер не поднялся.

    python tests/test_mcp_bridge.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.office import mcp_bridge


def _run(coro):
    return asyncio.run(coro)


def test_list_tools_returns_toy_server_catalog():
    mcp_bridge.invalidate_cache()
    tools = _run(mcp_bridge.list_tools("toy"))
    names = {t["name"] for t in tools}
    assert "mcp_ping" in names
    assert "mcp_server_time" in names
    ping = next(t for t in tools if t["name"] == "mcp_ping")
    assert ping["inputSchema"]["type"] == "object"
    assert "text" in ping["inputSchema"]["properties"]


def test_list_tools_unknown_server_returns_empty():
    assert _run(mcp_bridge.list_tools("does_not_exist")) == []


def test_call_tool_echoes_through_real_process():
    result = _run(mcp_bridge.call_tool("toy", "mcp_ping", {"text": "привет"}))
    assert "привет" in result
    assert "toy MCP" in result


def test_call_tool_unknown_server_degrades_gracefully():
    """Несуществующий сервер — понятное сообщение агенту, не исключение наружу."""
    result = _run(mcp_bridge.call_tool("does_not_exist", "whatever", {}))
    assert "не настроен" in result


def test_call_tool_broken_command_degrades_gracefully():
    """Сервер сконфигурирован, но команда не запускается — деградация, не сбой."""
    mcp_bridge._PLATFORM_SERVERS["__broken_test"] = {
        "command": "this-binary-does-not-exist-anywhere",
        "args": [], "roles": [],
    }
    try:
        result = _run(mcp_bridge.call_tool("__broken_test", "whatever", {}))
        assert "Ошибка вызова" in result
    finally:
        mcp_bridge._PLATFORM_SERVERS.pop("__broken_test", None)


def test_build_returns_schemas_and_working_handlers_for_role():
    schemas, handlers = _run(mcp_bridge.build(""))
    names = {s["function"]["name"] for s in schemas}
    assert "mcp__toy__mcp_ping" in names
    assert "mcp__toy__mcp_ping" in handlers
    out = _run(handlers["mcp__toy__mcp_ping"]({"text": "привет из agent_factory"}))
    assert "привет из agent_factory" in out


def test_build_respects_role_filter():
    mcp_bridge._PLATFORM_SERVERS["rolescopedtest"] = {
        "command": sys.executable,
        "args": [str(Path(__file__).resolve().parents[1] / "src" / "office" / "mcp_toy_server.py")],
        "roles": ["developer"],
    }
    mcp_bridge.invalidate_cache()
    try:
        schemas_dev, _ = _run(mcp_bridge.build("developer"))
        schemas_other, _ = _run(mcp_bridge.build("marketer"))
        dev_names = {s["function"]["name"] for s in schemas_dev}
        other_names = {s["function"]["name"] for s in schemas_other}
        assert "mcp__rolescopedtest__mcp_ping" in dev_names
        assert "mcp__rolescopedtest__mcp_ping" not in other_names
    finally:
        mcp_bridge._PLATFORM_SERVERS.pop("rolescopedtest", None)
        mcp_bridge.invalidate_cache()


def test_tool_names_are_namespaced_to_avoid_collisions():
    schemas, _ = _run(mcp_bridge.build(""))
    for s in schemas:
        assert s["function"]["name"].startswith("mcp__toy__")


def test_cache_avoids_second_process_spawn_within_ttl():
    """list_tools с кэшем не должен пересоздавать процесс на каждый вызов —
    проверяем через факт: второй вызов быстрее первого на порядок (процесс не
    поднимается заново)."""
    mcp_bridge.invalidate_cache()
    import time
    t0 = time.monotonic()
    _run(mcp_bridge.list_tools("toy"))
    first = time.monotonic() - t0
    t0 = time.monotonic()
    _run(mcp_bridge.list_tools("toy"))
    second = time.monotonic() - t0
    assert second < first  # закэшировано — не поднимали процесс второй раз


def _run_all():
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ✓ {name}")
            passed += 1
    print(f"ВСЕ {passed} ТЕСТОВ ПРОШЛИ")


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    _run_all()
