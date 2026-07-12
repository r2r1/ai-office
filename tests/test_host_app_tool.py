"""
Тесты агентских инструментов host_app/list_hosted_apps/stop_hosted_app
(integration_tool_handlers.py) — build() вызывается напрямую (без LLM),
subprocess.run мокается (см. test_tenant_apps.py), стиль
test_register_mcp_server_tool.py.

    python tests/test_host_app_tool.py
"""

import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv()

from src.saas import context as ctx
from src.office import exec_sandbox as sbx
from src.office import tenant_apps
from src.agents import integration_tool_handlers

_COMPOSE = "services:\n  app:\n    image: some/image\n    ports:\n      - '4008:4007'\n"


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


def _fake_run_ok(*args, **kwargs):
    return subprocess.CompletedProcess(args, 0, stdout="ok", stderr="")


def test_host_app_requires_fields():
    handlers, _ = _handlers()
    result = _run(handlers["host_app"]({"label": "X"}))
    assert "host_port" in result.lower() or "compose_yaml" in result.lower()


def test_host_app_rejected_without_sandbox():
    _fresh("host_tool_no_sandbox")
    _sandbox_off()
    try:
        handlers, _ = _handlers()
        result = _run(handlers["host_app"]({
            "label": "Postiz", "compose_yaml": _COMPOSE, "host_port": 4008, "container_port": 4007,
        }))
        assert "не удалось" in result.lower()
        assert tenant_apps.list_all() == []
    finally:
        _sandbox_off()


def test_host_app_succeeds_with_sandbox_ready():
    _fresh("host_tool_ready")
    _sandbox_ready()
    try:
        with patch("subprocess.run", side_effect=_fake_run_ok):
            handlers, events = _handlers()
            result = _run(handlers["host_app"]({
                "label": "Postiz", "compose_yaml": _COMPOSE, "host_port": 4008, "container_port": 4007,
                "env": {"KEY": "secret"},
            }))
        assert "поднят" in result.lower()
        apps = tenant_apps.list_all()
        assert len(apps) == 1
        assert apps[0]["status"] == "running"
        assert any(e.get("type") == "speech" for e in events)
    finally:
        _sandbox_off()


def test_list_hosted_apps_empty():
    _fresh("host_tool_empty")
    _sandbox_off()
    handlers, _ = _handlers()
    result = _run(handlers["list_hosted_apps"]({}))
    assert "пока не поднято" in result.lower()


def test_list_hosted_apps_shows_entries():
    _fresh("host_tool_list")
    _sandbox_ready()
    try:
        with patch("subprocess.run", side_effect=_fake_run_ok):
            handlers, _ = _handlers()
            _run(handlers["host_app"]({
                "label": "Postiz", "compose_yaml": _COMPOSE, "host_port": 4008, "container_port": 4007,
            }))
            result = _run(handlers["list_hosted_apps"]({}))
        assert "Postiz" in result
    finally:
        _sandbox_off()


def test_stop_hosted_app_requires_app_id():
    handlers, _ = _handlers()
    result = _run(handlers["stop_hosted_app"]({}))
    assert "app_id" in result.lower()


def test_stop_hosted_app_unknown_id():
    handlers, _ = _handlers()
    result = _run(handlers["stop_hosted_app"]({"app_id": "nonexistent"}))
    assert "не найдено" in result.lower()


def test_stop_hosted_app_stops_running_app():
    _fresh("host_tool_stop")
    _sandbox_ready()
    try:
        with patch("subprocess.run", side_effect=_fake_run_ok):
            handlers, events = _handlers()
            _run(handlers["host_app"]({
                "label": "Postiz", "compose_yaml": _COMPOSE, "host_port": 4008, "container_port": 4007,
            }))
            app_id = tenant_apps.list_all()[0]["id"]
            result = _run(handlers["stop_hosted_app"]({"app_id": app_id}))
        assert "остановлено" in result.lower()
        assert tenant_apps.get(app_id)["status"] == "stopped"
    finally:
        _sandbox_off()


def _cleanup_test_tenants() -> None:
    for d in ctx.ROOT.glob("host_tool_*"):
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
