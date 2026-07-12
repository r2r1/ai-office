"""
Тесты постоянного хостинга приложений тенанта (office/tenant_apps.py) —
мокаем subprocess.run (docker compose), как test_exec_sandbox.py мокает
`docker run` — проверяем построение команд и переходы статуса, не реальный
Docker (его нет на машине разработки).

    python tests/test_tenant_apps.py
"""

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

_COMPOSE = "services:\n  app:\n    image: some/image\n    ports:\n      - '4008:4007'\n"


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


def _fake_run_ok(*args, **kwargs):
    return subprocess.CompletedProcess(args, 0, stdout="ok", stderr="")


def _fake_run_fail(*args, **kwargs):
    return subprocess.CompletedProcess(args, 1, stdout="", stderr="boom")


def test_add_rejected_without_sandbox():
    _fresh("tapp_no_sandbox")
    _sandbox_off()
    try:
        try:
            tenant_apps.add("X", _COMPOSE, 4008, 4007)
            assert False, "должно было бросить SandboxUnavailable"
        except sbx.SandboxUnavailable:
            pass
        assert tenant_apps.list_all() == []
    finally:
        _sandbox_off()


def test_add_writes_compose_and_starts_stack():
    _fresh("tapp_ready")
    _sandbox_ready()
    try:
        with patch("subprocess.run", side_effect=_fake_run_ok):
            item = tenant_apps.add("Postiz", _COMPOSE, 4008, 4007, env={"KEY": "secret"})
        assert item["status"] == "running"
        assert item["host_port"] == 4008
        assert "_env_enc" not in item  # публичное представление без секретов
        d = tenant_apps._app_dir(item["id"])
        assert (d / "docker-compose.yml").read_text(encoding="utf-8") == _COMPOSE
        assert (d / ".env").exists()
    finally:
        _sandbox_off()


def test_add_marks_error_status_on_failed_compose_up():
    _fresh("tapp_fail")
    _sandbox_ready()
    try:
        with patch("subprocess.run", side_effect=_fake_run_fail):
            item = tenant_apps.add("X", _COMPOSE, 4009, 4007)
        assert item["status"] == "error"
    finally:
        _sandbox_off()


def test_add_rejects_duplicate_host_port():
    _fresh("tapp_dup_port")
    _sandbox_ready()
    try:
        with patch("subprocess.run", side_effect=_fake_run_ok):
            tenant_apps.add("A", _COMPOSE, 4010, 4007)
            try:
                tenant_apps.add("B", _COMPOSE, 4010, 4007)
                assert False, "должно было бросить ValueError"
            except ValueError:
                pass
    finally:
        _sandbox_off()


def test_add_enforces_max_apps_per_tenant():
    _fresh("tapp_limit")
    _sandbox_ready()
    try:
        with patch("subprocess.run", side_effect=_fake_run_ok):
            for i in range(tenant_apps._MAX_APPS_PER_TENANT):
                tenant_apps.add(f"App{i}", _COMPOSE, 5000 + i, 4007)
            try:
                tenant_apps.add("Overflow", _COMPOSE, 5999, 4007)
                assert False, "должно было бросить SandboxUnavailable (лимит)"
            except sbx.SandboxUnavailable:
                pass
    finally:
        _sandbox_off()


def test_stop_calls_compose_stop():
    _fresh("tapp_stop")
    _sandbox_ready()
    try:
        with patch("subprocess.run", side_effect=_fake_run_ok):
            item = tenant_apps.add("X", _COMPOSE, 4011, 4007)
            calls = []

            def _track(*args, **kwargs):
                calls.append(args[0])
                return _fake_run_ok(*args, **kwargs)

            with patch("subprocess.run", side_effect=_track):
                ok = tenant_apps.stop(item["id"])
            assert ok
            assert any("stop" in c for c in calls)
            assert tenant_apps.get(item["id"])["status"] == "stopped"
    finally:
        _sandbox_off()


def test_remove_calls_compose_down_and_deletes_dir():
    _fresh("tapp_remove")
    _sandbox_ready()
    try:
        with patch("subprocess.run", side_effect=_fake_run_ok):
            item = tenant_apps.add("X", _COMPOSE, 4012, 4007)
            d = tenant_apps._app_dir(item["id"])
            assert d.exists()
            ok = tenant_apps.remove(item["id"])
        assert ok
        assert not d.exists()
        assert tenant_apps.get(item["id"]) is None
    finally:
        _sandbox_off()


def _cleanup_test_tenants() -> None:
    for d in ctx.ROOT.glob("tapp_*"):
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
