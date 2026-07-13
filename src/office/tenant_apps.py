"""
Tenant Apps — постоянный хостинг open-source сервисов тенанта (Postiz и т.п.),
не путать с mcp_tenant_servers.py (короткоживущие MCP-серверы, живут секунды-
минуты на время задачи) или exec_sandbox.py (разовое исполнение кода задачи).

Здесь — принципиально другая модель: docker-compose СТЕК, который живёт 24/7,
хранит данные между перезапусками (volume) и должен быть достижим по HTTP —
это ближе к «мини-PaaS для тенанта», чем к разовой песочнице. Отсюда и другие
инварианты:

  - Тот же гейт, что у mcp_tenant_servers (SANDBOX_MODE=docker + реальный Docker),
    отказ ГРОМКИЙ и ДО записи, не тихая деградация.
  - Лимит числа одновременных приложений на тенанта (_MAX_APPS_PER_TENANT) —
    постоянный контейнер расходует CPU/RAM хоста непрерывно, а не разово за
    цикл, как LLM-вызов; без лимита один тенант может забить хост-машину.
  - Публичный доступ — НЕ через произвольные внешние порты хоста, а через
    reverse-proxy платформы (`GET/POST /apps/{tenant}/{app_id}/...` в server.py),
    тот же приём, что уже используется для сайтов (`/site/{tenant}/{slug}`) —
    тенант не получает сетевой доступ к хосту напрямую.
  - Регистрация (host_app) требует явного "да" от владельца тенанта через
    ask_user — агент НЕ решает автономно поднимать постоянную инфраструктуру
    (реальные деньги/ресурсы хост-машины, а не токены LLM). Сам модуль этого
    не проверяет (это ответственность вызывающего инструмента, integration_
    tool_handlers.py, как и у git push), но это единственная точка входа,
    поэтому пишем инвариант явно здесь.

Хранение: data/tenants/<tid>/apps.json (метаданные) +
          data/tenants/<tid>/apps/<app_id>/docker-compose.yml (сам стек).
"""

import subprocess
import time
import uuid
from pathlib import Path

from src.office import exec_sandbox
from src.saas import context as ctx
from src.saas import crypto

_FILE = "apps.json"
_MAX_APPS_PER_TENANT = 3
_COMPOSE_TIMEOUT = 300  # npm install/docker pull первого поднятия — тяжёлое


def _all() -> list[dict]:
    return ctx.read_json(_FILE, [])


def _save(items: list[dict]) -> None:
    ctx.write_json(_FILE, items)


def _apps_dir() -> Path:
    return ctx.tenant_dir() / "apps"


def _app_dir(app_id: str) -> Path:
    return _apps_dir() / app_id


def _require_ready(existing: list[dict]) -> None:
    if exec_sandbox.mode() != "docker":
        raise exec_sandbox.SandboxUnavailable(
            "Постоянный хостинг тенантских приложений требует SANDBOX_MODE=docker "
            "(долгоживущий стек без изоляции недопустим). Сейчас песочница выключена."
        )
    if not exec_sandbox.docker_available():
        raise exec_sandbox.SandboxUnavailable(
            "SANDBOX_MODE=docker, но Docker не отвечает — хостинг недоступен, "
            "пока песочница физически не готова."
        )
    if len(existing) >= _MAX_APPS_PER_TENANT:
        raise exec_sandbox.SandboxUnavailable(
            f"Лимит {_MAX_APPS_PER_TENANT} постоянных приложений на тенанта исчерпан — "
            "останови/удали одно из существующих (stop_hosted_app), прежде чем поднимать новое."
        )


def _compose_project(app_id: str) -> str:
    """Имя docker-compose проекта — стабильно уникально на (тенант, app), чтобы
    контейнеры/сети разных тенантов не пересекались даже при одинаковом app_id."""
    return f"aio_{ctx.get_tenant()}_{app_id}"[:63]


def _run_compose(app_id: str, *extra: str, timeout: int = 60) -> subprocess.CompletedProcess:
    """Живой прогон поймал реальный баг: stop/start/logs не проверяли готовность
    Docker вообще (только add() гейтит через _require_ready) — если бинарник
    docker отсутствует, subprocess.run бросает НЕПЕРЕХВАЧЕННЫЙ FileNotFoundError,
    роняя эндпоинт 500-й ошибкой вместо понятного статуса. Теперь ЛЮБОЙ вызов
    docker compose (не только add) ловит отсутствие Docker/таймаут единообразно —
    один источник правды для всех вызывающих (stop/start/remove/logs/add)."""
    d = _app_dir(app_id)
    cmd = [*exec_sandbox.DOCKER_CMD, "compose", "-p", _compose_project(app_id),
           "-f", exec_sandbox.wsl_path(d / "docker-compose.yml"), *extra]
    try:
        return subprocess.run(cmd, cwd=str(d), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout)
    except FileNotFoundError:
        return subprocess.CompletedProcess(cmd, 127, stdout="",
            stderr="docker не найден — Docker не установлен или недоступен в PATH.")


def add(label: str, compose_yaml: str, host_port: int, container_port: int,
        env: dict[str, str] | None = None) -> dict:
    """Регистрирует и ПОДНИМАЕТ (docker compose up -d) новое приложение тенанта.
    Бросает SandboxUnavailable, если песочница не готова или лимит исчерпан —
    ДО записи файлов, не после."""
    items = _all()
    _require_ready(items)
    used_ports = {i["host_port"] for i in items}
    if host_port in used_ports:
        raise ValueError(f"Порт {host_port} уже занят другим приложением этого тенанта.")

    app_id = uuid.uuid4().hex[:8]
    d = _app_dir(app_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "docker-compose.yml").write_text(compose_yaml, encoding="utf-8")
    if env:
        env_lines = "\n".join(f"{k}={v}" for k, v in env.items())
        (d / ".env").write_text(env_lines + "\n", encoding="utf-8")

    item = {
        "id": app_id, "label": (label or "").strip()[:100] or app_id,
        "host_port": host_port, "container_port": container_port,
        "env_keys": list((env or {}).keys()),
        "status": "starting", "created_ts": time.time(),
    }
    # env-значения хранятся ТОЛЬКО в .env файле стека (нужны docker compose при
    # каждом up), в метаданных — зашифрованно, только для восстановления/показа.
    item["_env_enc"] = {k: crypto.encrypt(v) for k, v in (env or {}).items()}
    items.append(item)
    _save(items)

    try:
        r = _run_compose(app_id, "up", "-d", timeout=_COMPOSE_TIMEOUT)
    except subprocess.TimeoutExpired:
        item["status"] = "error"
        _save(items)
        raise exec_sandbox.SandboxUnavailable(f"«{label}»: превышено время поднятия стека ({_COMPOSE_TIMEOUT}с).")
    item["status"] = "running" if r.returncode == 0 else "error"
    item["last_log"] = (r.stdout or "")[-2000:] + (r.stderr or "")[-2000:]
    _save(items)
    return _public(item)


def _public(item: dict) -> dict:
    return {k: v for k, v in item.items() if k != "_env_enc"}


def list_all() -> list[dict]:
    return [_public(i) for i in _all()]


def get(app_id: str) -> dict | None:
    for i in _all():
        if i["id"] == app_id:
            return _public(i)
    return None


def stop(app_id: str) -> bool:
    items = _all()
    for i in items:
        if i["id"] == app_id:
            r = _run_compose(app_id, "stop", timeout=60)
            i["status"] = "stopped" if r.returncode == 0 else "error"
            _save(items)
            return r.returncode == 0
    return False


def start(app_id: str) -> bool:
    """Возобновляет ранее остановленное (stop) приложение — docker compose
    start, не up: контейнеры/сеть уже созданы, поднимаем те же, не пересоздаём."""
    items = _all()
    for i in items:
        if i["id"] == app_id:
            r = _run_compose(app_id, "start", timeout=_COMPOSE_TIMEOUT)
            i["status"] = "running" if r.returncode == 0 else "error"
            _save(items)
            return r.returncode == 0
    return False


def env_values(app_id: str) -> dict[str, str]:
    """Расшифрованные значения env — только для владельца тенанта (UI «Приложения»),
    не для агента/API общего назначения (тот же принцип, что connections.py:
    ключи, которые сам владелец и вводил, показать ему обратно — не утечка)."""
    for i in _all():
        if i["id"] == app_id:
            return {k: crypto.decrypt(v) for k, v in i.get("_env_enc", {}).items()}
    return {}


def compose_yaml(app_id: str) -> str:
    f = _app_dir(app_id) / "docker-compose.yml"
    return f.read_text(encoding="utf-8") if f.exists() else ""


def remove(app_id: str) -> bool:
    items = _all()
    match = next((i for i in items if i["id"] == app_id), None)
    if not match:
        return False
    try:
        _run_compose(app_id, "down", "-v", timeout=120)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    import shutil
    shutil.rmtree(_app_dir(app_id), ignore_errors=True)
    _save([i for i in items if i["id"] != app_id])
    return True


def logs(app_id: str, tail: int = 50) -> str:
    r = _run_compose(app_id, "logs", f"--tail={max(1, min(tail, 500))}", timeout=30)
    return (r.stdout or "") + (r.stderr or "")


def reset() -> None:
    for i in _all():
        try:
            _run_compose(i["id"], "down", "-v", timeout=60)
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
    ctx.delete_file(_FILE)
