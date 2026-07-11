"""
Тесты агентских инструментов discover_resource/register_external_api
(integration_tool_handlers.py) — build() вызывается напрямую (без LLM), как
и остальные *_tool_handlers.py по стилю test_agent_tool_handlers.py.

    python tests/test_discover_resource_tool.py
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


def _handlers(agent_id="a1", role="developer"):
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


def test_discover_resource_requires_url():
    handlers, _ = _handlers()
    result = _run(handlers["discover_resource"]({}))
    assert "url" in result.lower()


def test_discover_resource_classifies_github_link():
    handlers, events = _handlers()
    result = _run(handlers["discover_resource"]({"url": "https://github.com/anthropics/claude-code"}))
    assert "github_repo" in result
    assert "github" in result.lower()
    assert any(e.get("type") == "speech" for e in events)


def test_register_external_api_requires_url_and_label():
    handlers, _ = _handlers()
    result = _run(handlers["register_external_api"]({"url": "https://api.example.com"}))
    assert "label" in result.lower()


def test_register_external_api_rejected_without_sandbox():
    _fresh("disc_test_reg_no_sandbox")
    _sandbox_off()
    try:
        handlers, _ = _handlers()
        result = _run(handlers["register_external_api"]({
            "url": "https://api.example.com", "label": "Тестовый API",
        }))
        assert "не удалось" in result.lower()
        assert mts.list_all() == []
    finally:
        _sandbox_off()


def test_register_external_api_succeeds_with_sandbox_ready():
    _fresh("disc_test_reg_ready")
    _sandbox_ready()
    try:
        handlers, events = _handlers()
        result = _run(handlers["register_external_api"]({
            "url": "https://api.example.com/", "label": "Тестовый API",
            "auth_header": "Authorization", "auth_value": "Bearer secret123",
        }))
        assert "подключён" in result.lower()
        servers = mts.list_all()
        assert len(servers) == 1
        assert servers[0]["label"] == "Тестовый API"
        # BASE_URL без слэша на конце (нормализация в handler'е)
        got = mts.get(servers[0]["id"])
        assert got["env"]["BASE_URL"] == "https://api.example.com"
        assert got["env"]["AUTH_VALUE"] == "Bearer secret123"
        assert any(e.get("type") == "speech" for e in events)
    finally:
        _sandbox_off()


def test_register_external_api_without_auth_omits_auth_env():
    _fresh("disc_test_reg_noauth")
    _sandbox_ready()
    try:
        handlers, _ = _handlers()
        _run(handlers["register_external_api"]({"url": "https://api.example.com", "label": "X"}))
        got = mts.get(mts.list_all()[0]["id"])
        assert "AUTH_HEADER" not in got["env"]
        assert "AUTH_VALUE" not in got["env"]
    finally:
        _sandbox_off()


def _cleanup_test_tenants() -> None:
    for d in ctx.ROOT.glob("disc_test_*"):
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
