"""
Тесты агентского инструмента register_mcp_server (integration_tool_handlers.py) —
Путь B из обсуждения Postiz: подключить РОДНОЙ MCP-сервер стороннего сервиса
(произвольный command/args), в отличие от register_external_api, который
всегда хардкодит command на mcp_generic_rest_server.py. build() вызывается
напрямую (без LLM), как test_discover_resource_tool.py.

    python tests/test_register_mcp_server_tool.py
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


def test_requires_label_and_command():
    handlers, _ = _handlers()
    result = _run(handlers["register_mcp_server"]({"label": "Postiz"}))
    assert "command" in result.lower()


def test_rejected_without_sandbox():
    _fresh("mcp_reg_no_sandbox")
    _sandbox_off()
    try:
        handlers, _ = _handlers()
        result = _run(handlers["register_mcp_server"]({
            "label": "Postiz", "command": "npx", "args": ["-y", "@gitroom/postiz-mcp"],
        }))
        assert "не удалось" in result.lower()
        assert mts.list_all() == []
    finally:
        _sandbox_off()


def test_registers_native_server_with_sandbox_ready():
    _fresh("mcp_reg_ready")
    _sandbox_ready()
    try:
        handlers, events = _handlers()
        result = _run(handlers["register_mcp_server"]({
            "label": "Postiz", "command": "npx", "args": ["-y", "@gitroom/postiz-mcp"],
            "env": {"POSTIZ_API_KEY": "secret123"}, "allow_network": True,
        }))
        assert "подключён" in result.lower()
        servers = mts.list_all()
        assert len(servers) == 1
        assert servers[0]["label"] == "Postiz"
        assert servers[0]["command"] == "npx"
        assert servers[0]["args"] == ["-y", "@gitroom/postiz-mcp"]
        assert servers[0]["allow_network"] is True
        got = mts.get(servers[0]["id"])
        assert got["env"]["POSTIZ_API_KEY"] == "secret123"
        assert any(e.get("type") == "speech" for e in events)
    finally:
        _sandbox_off()


def test_allow_network_defaults_to_false():
    _fresh("mcp_reg_default_net")
    _sandbox_ready()
    try:
        handlers, _ = _handlers()
        _run(handlers["register_mcp_server"]({"label": "X", "command": "node", "args": ["server.js"]}))
        servers = mts.list_all()
        assert servers[0]["allow_network"] is False
    finally:
        _sandbox_off()


def test_args_must_be_list():
    handlers, _ = _handlers()
    result = _run(handlers["register_mcp_server"]({"label": "X", "command": "npx", "args": "not-a-list"}))
    assert "списк" in result.lower()


def test_env_must_be_object():
    handlers, _ = _handlers()
    result = _run(handlers["register_mcp_server"]({"label": "X", "command": "npx", "env": "not-a-dict"}))
    assert "env" in result.lower()


def _cleanup_test_tenants() -> None:
    for d in ctx.ROOT.glob("mcp_reg_*"):
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
