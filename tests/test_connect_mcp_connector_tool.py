"""
Тесты агентских инструментов find_mcp_connectors/connect_mcp_connector
(integration_tool_handlers.py) — путь через каталог готовых рецептов вместо
ручного register_mcp_server. build() вызывается напрямую (без LLM), стиль
test_register_mcp_server_tool.py.

    python tests/test_connect_mcp_connector_tool.py
"""

import asyncio
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv()

from src.saas import context as ctx
from src.office import exec_sandbox as sbx
from src.office import mcp_tenant_servers as mts
from src.agents import integration_tool_handlers


def _fresh(name: str) -> None:
    ctx.set_tenant(name)
    ctx.wipe()
    ctx.set_tenant(name)


def _run(coro):
    return asyncio.run(coro)


def _handlers(agent_id="a1", role="integrator"):
    events = []

    async def _publish(ev):
        events.append(ev)

    return integration_tool_handlers.build(agent_id, role, _publish, _publish), events


def _sandbox_ready():
    os.environ["SANDBOX_MODE"] = "docker"
    sbx._docker_checked = True
    sbx._docker_ok = True


def _sandbox_off():
    os.environ.pop("SANDBOX_MODE", None)
    sbx._docker_checked = False
    sbx._docker_ok = False


def test_find_mcp_connectors_matches_postiz():
    handlers, _ = _handlers()
    result = _run(handlers["find_mcp_connectors"]({"query": "кроспостинг в соцсети"}))
    assert "postiz" in result.lower()


def test_find_mcp_connectors_empty_query_lists_catalog():
    handlers, _ = _handlers()
    result = _run(handlers["find_mcp_connectors"]({}))
    assert "postiz" in result.lower()


def test_connect_requires_connector_id():
    handlers, _ = _handlers()
    result = _run(handlers["connect_mcp_connector"]({"values": {}}))
    assert "connector_id" in result.lower()


def test_connect_unknown_connector_id():
    handlers, _ = _handlers()
    result = _run(handlers["connect_mcp_connector"]({"connector_id": "not_a_real_service", "values": {}}))
    assert "нет рецепта" in result.lower()


def test_connect_reports_missing_values():
    handlers, _ = _handlers()
    result = _run(handlers["connect_mcp_connector"]({
        "connector_id": "postiz", "values": {"POSTIZ_URL": "http://host:4007"},
    }))
    assert "postiz_api_key" in result.lower()


def test_connect_rejected_without_sandbox():
    _fresh("connect_mcp_no_sandbox")
    _sandbox_off()
    try:
        handlers, _ = _handlers()
        result = _run(handlers["connect_mcp_connector"]({
            "connector_id": "postiz",
            "values": {"POSTIZ_URL": "http://host:4007", "POSTIZ_API_KEY": "secret"},
        }))
        assert "не удалось" in result.lower()
        assert mts.list_all() == []
    finally:
        _sandbox_off()


def test_connect_succeeds_with_sandbox_ready():
    _fresh("connect_mcp_ready")
    _sandbox_ready()
    try:
        handlers, events = _handlers()
        result = _run(handlers["connect_mcp_connector"]({
            "connector_id": "postiz",
            "values": {"POSTIZ_URL": "http://host:4007", "POSTIZ_API_KEY": "secret123"},
        }))
        assert "подключён" in result.lower()
        servers = mts.list_all()
        assert len(servers) == 1
        assert servers[0]["command"] == "npx"
        assert "http://host:4007/mcp/secret123" in servers[0]["args"]
        assert servers[0]["allow_network"] is True
        assert any(e.get("type") == "speech" for e in events)
    finally:
        _sandbox_off()


def _cleanup_test_tenants() -> None:
    for d in ctx.ROOT.glob("connect_mcp_*"):
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)


def _run_all():
    passed = 0
    try:
        for name, fn in sorted(globals().items()):
            if name.startswith("test_") and callable(fn):
                fn()
                print(f"  ✓ {name}")
                passed += 1
    finally:
        _cleanup_test_tenants()
    print(f"ВСЕ {passed} ТЕСТОВ ПРОШЛИ")


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    _run_all()
