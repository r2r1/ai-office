"""
Тесты mcp_bridge.py — живой end-to-end прогон против игрушечного платформенного
MCP-сервера (mcp_toy_server.py), не моки: реально поднимает дочерний процесс
через stdio и говорит с ним по протоколу. Так же реально проверяется
деградация при недоступном/неправильно настроенном сервере — агент не должен
падать, если MCP-сервер не поднялся.

    python tests/test_mcp_bridge.py
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
from src.office import mcp_bridge
from src.office import mcp_tenant_servers as mts
from src.office import exec_sandbox as sbx


def _fresh(name: str) -> None:
    ctx.set_tenant(name)
    ctx.wipe()
    ctx.set_tenant(name)


def _sandbox_ready():
    os.environ["SANDBOX_MODE"] = "docker"
    sbx._docker_checked = True
    sbx._docker_ok = True


def _sandbox_off():
    os.environ.pop("SANDBOX_MODE", None)
    sbx._docker_checked = False
    sbx._docker_ok = False


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


# ── Тенантские MCP-серверы: docker-обёртка (только построение команды —
# Docker на машине разработки не установлен, тот же подход, что test_exec_sandbox) ─

def test_docker_wrap_has_isolation_flags_and_no_workspace_mount():
    conf = {"command": "npx", "args": ["my-server"], "env": {}, "allow_network": False}
    wrapped = mcp_bridge._docker_wrap(conf)
    # На Windows без Docker Desktop docker CLI зовётся через `wsl ... docker`
    # (см. exec_sandbox.DOCKER_CMD) — проверяем не буквальную команду "docker",
    # а что итоговый argv совпадает с DOCKER_CMD + docker-флаги.
    assert wrapped["command"] == sbx.DOCKER_CMD[0]
    args = wrapped["args"]
    assert "--read-only" in args
    assert "--cap-drop=ALL" in args
    assert "--security-opt=no-new-privileges" in args
    assert "--network" in args and "none" in args
    assert not any(":/workspace" in a for a in args)  # НЕТ volume-mount workspace
    assert sbx.IMAGE_NAME in args
    assert "npx" in args and "my-server" in args


def test_docker_wrap_allow_network_removes_network_none():
    conf = {"command": "npx", "args": [], "env": {}, "allow_network": True}
    args = mcp_bridge._docker_wrap(conf)["args"]
    assert "--network" not in args


def test_docker_wrap_passes_env_as_dash_e_flags():
    conf = {"command": "python", "args": ["s.py"], "env": {"API_KEY": "abc123"}, "allow_network": False}
    args = mcp_bridge._docker_wrap(conf)["args"]
    assert "-e" in args
    assert "API_KEY=abc123" in args


def test_docker_wrap_reuses_exec_sandbox_resource_limits():
    conf = {"command": "python", "args": [], "env": {}, "allow_network": False}
    args = mcp_bridge._docker_wrap(conf)["args"]
    assert f"--memory={sbx._MEMORY_LIMIT}" in args
    assert f"--cpus={sbx._CPU_LIMIT}" in args
    assert f"--pids-limit={sbx._PIDS_LIMIT}" in args


def test_tenant_servers_absent_from_build_when_sandbox_off():
    """Ключевой инвариант: без готовой песочницы тенантские серверы НЕ
    участвуют в build() вообще — деградация на использовании, не только на
    регистрации (sandbox мог быть выключен ПОСЛЕ регистрации сервера)."""
    _fresh("mcpb_test_sandbox_off")
    _sandbox_ready()
    try:
        mts.add("Тестовый", sys.executable,
                [str(Path(__file__).resolve().parents[1] / "src" / "office" / "mcp_toy_server.py")])
    finally:
        pass
    _sandbox_off()
    try:
        schemas, _ = _run(mcp_bridge.build(""))
        assert not any("tenant_" in s["function"]["name"] for s in schemas)
    finally:
        _sandbox_off()
        ctx.delete_file(mts._FILE)


def test_tenant_server_reachable_through_direct_stdio_when_wrap_bypassed():
    """Сам ПУТЬ резолва тенантского сервера (id → get() → _docker_wrap →
    подключение) работает end-to-end, если временно подменить _docker_wrap так,
    будто docker-обёртка — это просто прямой запуск (эквивалент "представим,
    что докер реально поднялся и просто передал управление команде") —
    единственный способ проверить весь путь целиком без установленного Docker."""
    _fresh("mcpb_test_tenant_reachable")
    _sandbox_ready()
    orig_wrap = mcp_bridge._docker_wrap
    mcp_bridge._docker_wrap = lambda conf: {"command": conf["command"], "args": conf.get("args", []), "env": None}
    try:
        item = mts.add("Toy через тенантский путь", sys.executable,
                       [str(Path(__file__).resolve().parents[1] / "src" / "office" / "mcp_toy_server.py")])
        server_id = f"{mcp_bridge._TENANT_PREFIX}{item['id']}"
        tools = _run(mcp_bridge.list_tools(server_id, use_cache=False))
        names = {t["name"] for t in tools}
        assert "mcp_ping" in names
        result = _run(mcp_bridge.call_tool(server_id, "mcp_ping", {"text": "тенантский сервер"}))
        assert "тенантский сервер" in result
    finally:
        mcp_bridge._docker_wrap = orig_wrap
        _sandbox_off()
        ctx.delete_file(mts._FILE)
        mcp_bridge.invalidate_cache()


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
