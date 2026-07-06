"""
Юнит-тесты exec_sandbox.py (docs/audit-dd-2026-07-06.md §11/§19 п.2 —
контейнеризация execute_code/run_command).

⚠️ Docker на машине разработки НЕ установлен — тесты на docker-путь мокают
subprocess.run и проверяют ТОЛЬКО построение команды (флаги изоляции,
монтирование workdir, отсутствие сети, ресурс-лимиты) — они НЕ доказывают,
что реальный `docker run` с этими флагами действительно работает. Прямое
(direct) исполнение проверяется реальным вызовом (без моков) — оно не
изменилось по поведению, только было извлечено в отдельный модуль.

Запуск: python tests/test_exec_sandbox.py
"""

import os
import sys
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.office import exec_sandbox as sbx


def _tmp_workdir(name: str) -> Path:
    d = Path(__file__).resolve().parent / f"_sbx_tmp_{name}"
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    return d


def test_mode_defaults_to_direct_without_env():
    os.environ.pop("SANDBOX_MODE", None)
    assert sbx.mode() == "direct"


def test_mode_reads_env_and_falls_back_on_garbage():
    os.environ["SANDBOX_MODE"] = "docker"
    assert sbx.mode() == "docker"
    os.environ["SANDBOX_MODE"] = "nonsense"
    assert sbx.mode() == "direct"  # неизвестное значение → безопасный дефолт
    os.environ.pop("SANDBOX_MODE", None)


def test_run_script_direct_mode_actually_executes():
    """Direct-режим — прежнее поведение, без моков: реально запускаем python."""
    os.environ.pop("SANDBOX_MODE", None)
    d = _tmp_workdir("direct")
    (d / "hello.py").write_text("print('sandbox direct ok')", encoding="utf-8")
    try:
        result = sbx.run_script("python", "hello.py", workdir=d, timeout=10)
        assert result.returncode == 0
        assert "sandbox direct ok" in result.stdout
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_run_shell_direct_mode_respects_workdir():
    os.environ.pop("SANDBOX_MODE", None)
    d = _tmp_workdir("shell")
    (d / "marker.txt").write_text("present", encoding="utf-8")
    try:
        result = sbx.run_shell("dir" if os.name == "nt" else "ls", workdir=d, timeout=10)
        assert "marker.txt" in result.stdout
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_docker_mode_without_docker_raises_explicit_error_not_silent_fallback():
    """Ключевой инвариант: SANDBOX_MODE=docker без установленного Docker должен
    ГРОМКО упасть, а не тихо исполнить код без изоляции (см. докстринг модуля)."""
    os.environ["SANDBOX_MODE"] = "docker"
    sbx._docker_checked = True
    sbx._docker_ok = False
    d = _tmp_workdir("docker_missing")
    try:
        raised = False
        try:
            sbx.run_script("python", "x.py", workdir=d, timeout=5)
        except sbx.SandboxUnavailable:
            raised = True
        assert raised, "должен поднять SandboxUnavailable, а не исполнить код"
    finally:
        shutil.rmtree(d, ignore_errors=True)
        sbx._docker_checked = False
        os.environ.pop("SANDBOX_MODE", None)


def test_docker_command_construction_has_isolation_flags():
    """Мокаем subprocess.run — проверяем ТОЛЬКО построение команды docker run
    (реальный Docker не установлен на машине разработки)."""
    os.environ["SANDBOX_MODE"] = "docker"
    sbx._docker_checked = True
    sbx._docker_ok = True
    d = _tmp_workdir("docker_cmd")
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        m = MagicMock()
        m.returncode = 0
        m.stdout = "ok"
        m.stderr = ""
        return m

    try:
        with patch("subprocess.run", side_effect=fake_run):
            sbx.run_script("python", "script.py", workdir=d, timeout=15, stdin_input="hi")
        args = captured["args"]
        joined = " ".join(args)
        assert "--network none" in joined or ("--network" in args and "none" in args)
        assert "--read-only" in args
        assert "--cap-drop=ALL" in args
        assert "--security-opt=no-new-privileges" in args
        assert f"{str(d)}:/workspace:rw" in args
        assert "-w" in args and "/workspace" in args
        assert "python3" in args  # НЕ sys.executable (host-путь бессмыслен в контейнере)
        assert "script.py" in args  # относительный путь, не абсолютный host-путь
        assert sbx.IMAGE_NAME in args
        assert captured["kwargs"].get("input") == "hi"
    finally:
        shutil.rmtree(d, ignore_errors=True)
        sbx._docker_checked = False
        os.environ.pop("SANDBOX_MODE", None)


def test_docker_shell_command_uses_bash_lc_not_raw_shell_true():
    """run_shell в docker-режиме НЕ должен полагаться на shell=True хоста —
    команда идёт внутрь контейнера через bash -lc."""
    os.environ["SANDBOX_MODE"] = "docker"
    sbx._docker_checked = True
    sbx._docker_ok = True
    d = _tmp_workdir("docker_shell")
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        m = MagicMock()
        m.returncode = 0
        m.stdout = ""
        m.stderr = ""
        return m

    try:
        with patch("subprocess.run", side_effect=fake_run):
            sbx.run_shell("echo test && ls", workdir=d, timeout=10)
        args = captured["args"]
        assert "bash" in args and "-lc" in args
        assert "echo test && ls" in args
    finally:
        shutil.rmtree(d, ignore_errors=True)
        sbx._docker_checked = False
        os.environ.pop("SANDBOX_MODE", None)


def test_timeout_triggers_container_cleanup():
    """При таймауте docker-режим должен явно убрать контейнер (docker rm -f),
    а не оставлять его висеть (см. except TimeoutExpired в _run_docker)."""
    os.environ["SANDBOX_MODE"] = "docker"
    sbx._docker_checked = True
    sbx._docker_ok = True
    d = _tmp_workdir("docker_timeout")
    cleanup_calls = []

    import subprocess as _subprocess

    def fake_run(args, **kwargs):
        if args[:2] == ["docker", "rm"]:
            cleanup_calls.append(args)
            m = MagicMock()
            m.returncode = 0
            return m
        raise _subprocess.TimeoutExpired(cmd=args, timeout=kwargs.get("timeout", 1))

    try:
        with patch("subprocess.run", side_effect=fake_run):
            raised = False
            try:
                sbx.run_script("python", "x.py", workdir=d, timeout=1)
            except _subprocess.TimeoutExpired:
                raised = True
        assert raised
        assert len(cleanup_calls) == 1
        assert "-f" in cleanup_calls[0]
    finally:
        shutil.rmtree(d, ignore_errors=True)
        sbx._docker_checked = False
        os.environ.pop("SANDBOX_MODE", None)


def _run():
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
    _run()
