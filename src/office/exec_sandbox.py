"""
Песочница для execute_code/run_command через Docker (docs/audit-dd-2026-07-06.md
§11/§19 п.2 — "Контейнеризировать execute_code/run_command").

Не путать с office/sandbox.py (BOS §9 "clone→check→merge/discard" для Decision
Engine — другая, уже существующая сущность с тем же словом в названии).
Здесь — буквальная песочница ОС для исполнения кода агентов.

До этого модуля `_safe()` в workspace.py защищал только путь ФАЙЛА, который
запускается, а не то, что делает уже запущенный процесс — Python/JS/bash-код
внутри workspace мог прочитать `../../<чужой-tenant>/connections.json`, `.env`
и т.п. с правами процесса сервера. Здесь — реальная изоляция: контейнер без
сети, с read-only корневой ФС (кроме /workspace и /tmp), без привилегий и с
лимитами CPU/памяти/числа процессов.

Режимы (SANDBOX_MODE в .env):
    direct  — (по умолчанию) исполнение НАПРЯМУЮ на хосте, БЕЗ изоляции —
              прежнее поведение workspace.py, ничего не меняется для тех, у
              кого не настроен Docker. Сохраняет обратную совместимость.
    docker  — исполнение в контейнере (см. docker/sandbox.Dockerfile). Требует
              установленный и запущенный Docker; если недоступен — ЯВНАЯ
              ошибка (не тихий fallback на незащищённое исполнение — иначе
              оператор мог бы годами думать, что песочница работает).

Интерфейс намеренно НЕ «дай мне argv, я его исполню» — интерпретатор внутри
контейнера НЕ тот же бинарник, что на хосте (`sys.executable` — путь вида
"C:/.../python.exe"/WindowsApps на Windows-хосте, внутри Linux-контейнера
такого файла нет; аналогично абсолютный путь к скрипту на хосте бессмысленен
внутри контейнера, где видно только смонтированный /workspace). Поэтому:
`run_script(lang, rel_path, ...)` сам выбирает имя интерпретатора под режим,
`run_shell(cmd_str, ...)` — для произвольной shell-команды (run_command).

⚠️ Этот модуль написан и покрыт юнит-тестами на уровне ПОСТРОЕНИЯ команды
(что именно передаётся в `docker run` — мокается сам subprocess.run), но НЕ
проверен живым запуском реального Docker (на машине разработки Docker не
установлен). Перед включением SANDBOX_MODE=docker в проде: собрать образ
(см. docker/sandbox.Dockerfile) и вручную прогнать несколько реальных задач.
"""

import os
import subprocess
import sys
import uuid
from pathlib import Path

IMAGE_NAME = os.getenv("SANDBOX_IMAGE", "ai-office-sandbox")
_MEMORY_LIMIT = os.getenv("SANDBOX_MEMORY", "512m")
_CPU_LIMIT = os.getenv("SANDBOX_CPUS", "1")
_PIDS_LIMIT = os.getenv("SANDBOX_PIDS", "128")

# Docker Engine без Desktop (WSL2 + `curl -fsSL https://get.docker.com`, см.
# handoff.md) не даёт Windows-хосту готового `docker.exe`, подключённого к
# демону (это делает проприетарная прослойка Desktop через named pipe) — сам
# демон живёт ТОЛЬКО внутри дистрибутива WSL. На Windows поэтому вызываем
# docker CLI не напрямую, а через `wsl -d <SANDBOX_WSL_DISTRO> -u root docker`.
# На Linux/macOS-хосте (реальный docker в PATH) префикс пустой.
_WSL_DISTRO = os.getenv("SANDBOX_WSL_DISTRO", "Ubuntu")
DOCKER_CMD: list[str] = (
    ["wsl", "-d", _WSL_DISTRO, "-u", "root", "docker"] if os.name == "nt" else ["docker"]
)

# Интерпретатор в контейнере (docker/sandbox.Dockerfile) — фиксированные имена
# бинарников образа. На хосте (direct-режим) — sys.executable/node/bash как раньше.
_CONTAINER_INTERPRETER = {"python": "python3", "node": "node", "bash": "bash"}

_docker_checked = False
_docker_ok = False


def mode() -> str:
    m = (os.getenv("SANDBOX_MODE", "direct") or "direct").strip().lower()
    return m if m in ("direct", "docker") else "direct"


# Через `wsl.exe` (DOCKER_CMD без Desktop) первый вызов после простоя будит
# остановленную WSL2-VM — это реально занимает больше 5с (замер: ~5.0с давал
# ложный SandboxUnavailable); при уже тёплой VM ответ приходит за доли секунды,
# так что больший таймаут не замедляет частый путь, только страхует холодный.
_DOCKER_CHECK_TIMEOUT = 5 if os.name != "nt" else 20


def docker_available() -> bool:
    """Кэшируется на успехе (Docker не исчезает посреди работы процесса), но
    перепроверяется при неудаче — оператор мог поднять Docker уже после старта."""
    global _docker_checked, _docker_ok
    if _docker_checked and _docker_ok:
        return True
    try:
        r = subprocess.run([*DOCKER_CMD, "version", "--format", "{{.Server.Version}}"],
                           capture_output=True, text=True, timeout=_DOCKER_CHECK_TIMEOUT)
        _docker_ok = r.returncode == 0
    except Exception:
        _docker_ok = False
    _docker_checked = True
    return _docker_ok


class SandboxUnavailable(Exception):
    """SANDBOX_MODE=docker, но Docker не установлен/не запущен — намеренно НЕ
    падаем обратно на незащищённое исполнение молча."""


def _require_docker_if_needed() -> None:
    if mode() == "docker" and not docker_available():
        raise SandboxUnavailable(
            "SANDBOX_MODE=docker, но `docker version` не отвечает — Docker не "
            "установлен или не запущен. Не исполняю код БЕЗ песочницы молча: "
            "либо поднимите Docker, либо явно переключите SANDBOX_MODE=direct "
            "(небезопасно, только для доверенного одиночного деплоя)."
        )


def run_script(lang: str, rel_path: str, *, workdir: Path, timeout: int = 30,
              stdin_input: str = "") -> subprocess.CompletedProcess:
    """Запускает файл `rel_path` (путь ОТНОСИТЕЛЬНО workdir) интерпретатором
    `lang` ("python"|"node"|"bash"). `workdir` — АБСОЛЮТНЫЙ путь рабочей папки
    ТЕНАНТА на хосте — в docker-режиме монтируется целиком как /workspace, так
    что интерпретатор внутри контейнера физически не видит соседние
    `data/tenants/<other>/` директории на хосте."""
    _require_docker_if_needed()
    if mode() == "docker":
        interp = _CONTAINER_INTERPRETER[lang]
        return _run_docker([interp, rel_path], workdir=workdir, timeout=timeout,
                           stdin_input=stdin_input)
    host_interp = {"python": sys.executable, "node": "node", "bash": "bash"}[lang]
    return _run_direct([host_interp, str(Path(workdir) / rel_path)],
                       workdir=workdir, timeout=timeout, stdin_input=stdin_input,
                       shell=False)


def run_shell(cmd_str: str, *, workdir: Path, timeout: int = 30,
             stdin_input: str = "") -> subprocess.CompletedProcess:
    """Запускает произвольную shell-команду (run_command/терминал)."""
    _require_docker_if_needed()
    if mode() == "docker":
        return _run_docker(cmd_str, workdir=workdir, timeout=timeout,
                           stdin_input=stdin_input, shell_cmd=True)
    return _run_direct(cmd_str, workdir=workdir, timeout=timeout,
                       stdin_input=stdin_input, shell=True)


def _run_direct(cmd, *, workdir: Path, timeout: int, stdin_input: str,
                shell: bool) -> subprocess.CompletedProcess:
    """Прежнее поведение (до контейнеризации) — прямое исполнение на хосте.
    env — allowlist, не полный os.environ (см. workspace._utf8_env)."""
    from src.office import workspace as _ws
    return subprocess.run(
        cmd, shell=shell, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout,
        cwd=str(workdir), input=stdin_input or None, env=_ws._utf8_env(),
    )


def wsl_path(p: Path | str) -> str:
    """Любой Windows-путь (том `-v`, файл `-f docker-compose.yml`...), который
    передаётся docker CLI, выполняющемуся ВНУТРИ WSL (см. DOCKER_CMD) — нужно
    перевести в путь ЕГО файловой системы. `C:\\Users\\x` → `/mnt/c/Users/x`
    (стандартный маппинг WSL2 дисков), иначе путь молча указывает в никуда.

    Живой баг: вызывающие часто передают ОТНОСИТЕЛЬНЫЙ путь (например,
    `ctx.tenant_dir()` — относительно рабочей директории процесса) — без
    приведения к абсолютному условие `s[1] == ":"` не срабатывает, путь
    уходит В WSL как есть (`data\\tenants\\...`, обратные слэши), а `wsl.exe`
    сам по себе домешивает его к переведённому cwd — куски слипаются в одну
    строку без разделителей. `os.path.abspath` — тот же приём, что уже
    защищает от этого в `workspace.py`."""
    s = os.path.abspath(str(p))
    if os.name == "nt" and len(s) >= 2 and s[1] == ":":
        drive = s[0].lower()
        rest = s[2:].replace("\\", "/")
        return f"/mnt/{drive}{rest}"
    return s.replace("\\", "/")




def _run_docker(cmd, *, workdir: Path, timeout: int, stdin_input: str,
                shell_cmd: bool = False) -> subprocess.CompletedProcess:
    name = f"ai-office-sbx-{uuid.uuid4().hex[:12]}"
    docker_args = [
        *DOCKER_CMD, "run", "--rm", "--name", name,
        "--network", "none",              # без сети: агенту не нужно ничего скачивать
        "--read-only",                    # корневая ФС только для чтения
        "--tmpfs", "/tmp:rw,size=64m,noexec",  # писать можно только в /tmp и /workspace
        f"--memory={_MEMORY_LIMIT}",
        f"--cpus={_CPU_LIMIT}",
        f"--pids-limit={_PIDS_LIMIT}",
        "--security-opt=no-new-privileges",
        "--cap-drop=ALL",
        "-v", f"{wsl_path(workdir)}:/workspace:rw",
        "-w", "/workspace",
        "-i",                             # держим stdin открытым (для stdin_input)
        IMAGE_NAME,
    ]
    if shell_cmd:
        docker_args += ["bash", "-lc", cmd]
    else:
        docker_args += list(cmd)

    try:
        return subprocess.run(
            docker_args, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
            input=stdin_input or None,
        )
    except subprocess.TimeoutExpired:
        # --rm не подчищает контейнер, если клиент (docker run) убит по таймауту
        # раньше, чем сам процесс внутри завершился — явно убираем, чтобы
        # зависшие/тяжёлые скрипты агентов не копили контейнеры на хосте.
        try:
            subprocess.run([*DOCKER_CMD, "rm", "-f", name], capture_output=True, timeout=10)
        except Exception:
            pass
        raise
