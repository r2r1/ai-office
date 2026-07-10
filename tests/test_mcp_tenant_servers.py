"""
Тесты mcp_tenant_servers.py — тенантский MCP-сервер это исполнение
произвольного кода от имени тенанта, поэтому add() ОБЯЗАН отказывать сразу,
если песочница (SANDBOX_MODE=docker + реально доступный Docker) не готова —
не принимать регистрацию и не деградировать молча при первом использовании.

Docker на машине разработки НЕ установлен (как и в test_exec_sandbox.py) —
докер-путь мокается через exec_sandbox._docker_checked/_docker_ok, реальный
`docker run` этими тестами не проверяется.

    python tests/test_mcp_tenant_servers.py
"""

import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv()

from src.saas import context as ctx
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


def test_add_rejected_when_sandbox_mode_is_direct():
    _fresh("mts_test_direct_mode")
    _sandbox_off()
    try:
        raised = False
        try:
            mts.add("Мой сервер", "npx", ["my-mcp-server"])
        except sbx.SandboxUnavailable:
            raised = True
        assert raised
        assert mts.list_all() == []
    finally:
        _sandbox_off()


def test_add_rejected_when_docker_mode_but_docker_unavailable():
    _fresh("mts_test_docker_down")
    os.environ["SANDBOX_MODE"] = "docker"
    sbx._docker_checked = True
    sbx._docker_ok = False
    try:
        raised = False
        try:
            mts.add("Мой сервер", "npx", ["my-mcp-server"])
        except sbx.SandboxUnavailable:
            raised = True
        assert raised
    finally:
        _sandbox_off()


def test_add_succeeds_when_sandbox_ready():
    _fresh("mts_test_ready")
    _sandbox_ready()
    try:
        item = mts.add("Мой сервер", "npx", ["my-mcp-server"], env={"API_KEY": "secret123"})
        assert item["label"] == "Мой сервер"
        assert item["command"] == "npx"
        assert "API_KEY" in item["env_keys"]
        assert "secret123" not in str(item)  # публичный вид не содержит значение
    finally:
        _sandbox_off()


def test_env_values_are_encrypted_at_rest():
    _fresh("mts_test_encrypted")
    _sandbox_ready()
    try:
        item = mts.add("Сервер", "python", ["server.py"], env={"TOKEN": "top-secret-value"})
        raw = ctx.read_json(mts._FILE, [])
        stored_env_value = raw[0]["env"]["TOKEN"]
        assert stored_env_value != "top-secret-value"  # не хранится в открытом виде
        got = mts.get(item["id"])
        assert got["env"]["TOKEN"] == "top-secret-value"  # но расшифровывается обратно
    finally:
        _sandbox_off()


def test_remove_deletes_server():
    _fresh("mts_test_remove")
    _sandbox_ready()
    try:
        item = mts.add("Временный", "python", ["s.py"])
        assert len(mts.list_all()) == 1
        assert mts.remove(item["id"]) is True
        assert mts.list_all() == []
        assert mts.remove(item["id"]) is False
    finally:
        _sandbox_off()


def test_list_for_use_decrypts_env_for_internal_consumer():
    _fresh("mts_test_list_for_use")
    _sandbox_ready()
    try:
        mts.add("Сервер", "python", ["s.py"], env={"X": "yvalue"})
        servers = mts.list_for_use()
        assert servers[0]["env"]["X"] == "yvalue"
    finally:
        _sandbox_off()


def _cleanup_test_tenants() -> None:
    for d in ctx.ROOT.glob("mts_test_*"):
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)


def _run():
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
    _run()
