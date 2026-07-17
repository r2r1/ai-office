"""
Супервайзор — отдельный, ВСЕГДА работающий процесс (свой порт, по умолчанию
8001), который умеет запускать/останавливать основной сервер (`scripts/run.py`)
и удалять тенантов. Реальная причина существования: без него запуск сервера
из админ-панели (admin_panel/index.html) невозможен в принципе — если
основной сервер не запущен, ему некому ответить на HTTP-запрос «запустись».
Нужен второй процесс, который живёт НЕЗАВИСИМО от того, жив ли основной.

Отличие от routers/admin.py: тот работает ВНУТРИ основного сервера (пауза/
прокси/логи конкретных тенантов, требует, чтобы сервер уже был поднят) — этот
работает СНАРУЖИ (старт/стоп/статус самого процесса сервера + удаление
тенанта, которое не требует, чтобы сервер был жив, т.к. работает напрямую с
sqlite/файлами тенанта). Оба защищены одним и тем же ADMIN_API_KEY.

Запуск (вручную, один раз — этот процесс НЕ перезапускает сам себя):
    python scripts/supervisor.py
Порт — SUPERVISOR_PORT (.env), по умолчанию 8001. Порт основного сервера,
которым супервайзор управляет — PORT (.env), по умолчанию 8000, тот же,
что использует scripts/run.py.

⚠️ Поиск/остановка процесса на APP_PORT сейчас реализована через Windows
(PowerShell Get-NetTCPConnection + taskkill) — это Windows-машина разработки
(см. CLAUDE.md). На другой ОС потребуется свой способ найти PID, слушающий
порт, и остановить дерево процессов.
"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# `python scripts/supervisor.py` кладёт в sys.path[0] scripts/, не корень
# репозитория — без этого `from src.saas import ...` ниже падал бы
# ModuleNotFoundError (та же причина, что app_dir= в scripts/run.py).
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import Response

load_dotenv()
APP_PORT = int(os.getenv("PORT", "8000"))
SUPERVISOR_PORT = int(os.getenv("SUPERVISOR_PORT", "8001"))
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "").strip()

app = FastAPI()


def _require_admin(x_admin_key: str | None) -> None:
    if not ADMIN_API_KEY:
        raise HTTPException(503, "ADMIN_API_KEY не задан в .env — супервайзор отключён")
    if not x_admin_key or x_admin_key != ADMIN_API_KEY:
        raise HTTPException(401, "неверный или отсутствующий X-Admin-Key")


# Тот же CORS-паттерн, что у /admin/api/* в server.py: admin_panel/index.html —
# отдельный статический файл на своём URL, запросы сюда всегда кросс-доменные.
_CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "X-Admin-Key, Content-Type",
    "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
    "Access-Control-Allow-Private-Network": "true",
}


@app.middleware("http")
async def cors_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        return Response(status_code=204, headers=_CORS_HEADERS)
    response = await call_next(request)
    response.headers.update(_CORS_HEADERS)
    return response


def _pids_on_port_sync(port: int) -> list[int]:
    """PID'ы процессов, слушающих порт (Windows). Пустой список — порт свободен.

    Реальный найденный баг: изначально использовал PowerShell (Get-NetTCPConnection)
    — на этой машине холодный запуск powershell.exe занимал ~5 СЕКУНД на вызов
    (профиль/антивирус/что угодно — не важно почему, важно что это ощущалось как
    "статус завис", хотя технически asyncio.to_thread уже не блокировал event loop).
    netstat — тот же cmd.exe-инструмент без загрузки PowerShell-рантайма,
    тот же результат за ~0.1-0.2с вместо ~5с (замерено живьём)."""
    try:
        out = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True, text=True, timeout=10,
        ).stdout
        pids = set()
        for line in out.splitlines():
            parts = line.split()
            # Формат: Proto  Local-адрес  Внешний-адрес  Состояние  PID
            if len(parts) != 5 or parts[3] != "LISTENING":
                continue
            if not parts[1].endswith(f":{port}"):
                continue
            if parts[4].isdigit():
                pids.add(int(parts[4]))
        return sorted(pids)
    except Exception:
        return []


def _kill_pid_tree_sync(pid: int) -> None:
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, timeout=10)


# Реальный найденный баг (живой прогон): _pids_on_port/_kill_pid_tree раньше
# вызывались СИНХРОННО прямо внутри async-обработчиков — subprocess.run()
# блокирует ВЕСЬ event loop (uvicorn здесь однопоточный), пока PowerShell не
# ответит. Если запуск PowerShell завис/затормозил (что реально бывает —
# у процесса есть свой холодный старт, ~100-300мс и больше под нагрузкой),
# ВЕСЬ супервайзор переставал отвечать вообще на ЛЮБЫЕ запросы, включая
# /supervisor/status — то есть сам "всегда доступный" процесс переставал
# быть доступным. asyncio.to_thread уносит блокирующий вызов в отдельный
# поток — event loop остаётся живым для остальных запросов.
async def _pids_on_port(port: int) -> list[int]:
    return await asyncio.to_thread(_pids_on_port_sync, port)


async def _kill_pid_tree(pid: int) -> None:
    await asyncio.to_thread(_kill_pid_tree_sync, pid)


@app.get("/supervisor/status")
async def status(x_admin_key: str | None = Header(default=None)) -> dict:
    _require_admin(x_admin_key)
    pids = await _pids_on_port(APP_PORT)
    return {"running": bool(pids), "pids": pids, "port": APP_PORT}


@app.post("/supervisor/start")
async def start(x_admin_key: str | None = Header(default=None)) -> dict:
    _require_admin(x_admin_key)
    if await _pids_on_port(APP_PORT):
        return {"ok": True, "already_running": True}
    log_path = ROOT / "data" / "server.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_f = open(log_path, "a", encoding="utf-8")
    # DETACHED_PROCESS + CREATE_NEW_PROCESS_GROUP (Windows): переживает завершение
    # ЭТОГО запроса и не зависит от жизни супервайзора — тот же принцип, что у
    # ручного запуска `python scripts/run.py` в отдельном терминале, просто без
    # необходимости иметь терминал.
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(
        [sys.executable, "scripts/run.py"],
        cwd=str(ROOT), stdout=log_f, stderr=log_f,
        creationflags=creationflags, close_fds=True,
    )
    return {"ok": True, "already_running": False, "log": str(log_path)}


@app.post("/supervisor/stop")
async def stop(x_admin_key: str | None = Header(default=None)) -> dict:
    _require_admin(x_admin_key)
    pids = await _pids_on_port(APP_PORT)
    for pid in pids:
        await _kill_pid_tree(pid)
    return {"ok": True, "killed": pids}


@app.get("/supervisor/tenants")
async def list_tenants(x_admin_key: str | None = Header(default=None)) -> dict:
    """Работает НЕЗАВИСИМО от того, жив ли основной сервер — читает sqlite
    напрямую (тот же saas/db.py, что и сам сервер использует)."""
    _require_admin(x_admin_key)
    from src.saas import store as saas_store
    return {"tenants": [
        {"id": ws["id"], "name": ws.get("name"), "created_at": ws.get("created_at")}
        for ws in saas_store.all_workspaces()
    ]}


@app.delete("/supervisor/tenant/{tid}")
async def delete_tenant(tid: str, x_admin_key: str | None = Header(default=None)) -> dict:
    """Дублирует DELETE /admin/api/tenant/{tid} из routers/admin.py — та версия
    требует, чтобы основной сервер был жив (эндпоинт живёт внутри его процесса),
    эта работает и когда он остановлен."""
    _require_admin(x_admin_key)
    from src.saas import store as saas_store
    ok = saas_store.delete_workspace(tid)
    if not ok:
        raise HTTPException(404, "тенант не найден")
    return {"ok": True, "deleted": tid}


if __name__ == "__main__":
    import uvicorn
    # reload=False намеренно: этот процесс должен жить, что бы ни происходило
    # с кодом основного сервера — если он сам перезагрузится посреди операции
    # старт/стоп, POST-запрос из админки просто оборвётся.
    uvicorn.run(app, host="127.0.0.1", port=SUPERVISOR_PORT, reload=False)
