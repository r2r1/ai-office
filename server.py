"""
FastAPI сервер — SSE-стрим событий + статика игры.
"""

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

# ВАЖНО: load_dotenv() ДО импорта src.saas.auth — тот резолвит APP_SECRET
# (crypto.require_app_secret()) прямо при импорте модуля и падает, если секрет
# не задан. Если .env грузится позже импорта, переменная ещё не видна
# os.environ, и процесс падает даже при корректно заполненном .env.
load_dotenv()

from fastapi import FastAPI
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from src.office import bus, registry, loop as office_loop, demo, state
from src.office import sites as sites_module
from src.saas import db as saas_db, store as saas_store, auth as saas_auth
from src.saas import context as saas_context
from src.office import domains as domains_module

from routers.auth import router as auth_router
from routers.resources import router as resources_router
from routers.public import router as public_router
from routers.team import router as team_router
from routers.dashboard import router as dashboard_router
from routers.work import router as work_router
from routers.settings import router as settings_router
from routers.results import router as results_router
from routers.comms import router as comms_router
from routers.admin import router as admin_router
from routers.shared import serve_site_file, DEMO_MODE


def _warn_if_unsandboxed_execution_in_prod() -> None:
    """Аудит docs/technical-due-diligence-2026-07-17.md §5.2: ALLOW_CODE_EXECUTION=1
    + SANDBOX_MODE=direct даёт любому тенанту шелл на хосте с правами процесса
    (path traversal через `cat ../../<tenant>/.env` — читает APP_SECRET, которым
    зашифрованы секреты ВСЕХ тенантов). Опасно только вне localhost-разработки —
    APP_BASE_URL, похожий на прод (https, не localhost/127.0.0.1), с этой
    комбинацией флагов не должен уехать в прод молча. Не hard-fail: staging может
    осознанно держать direct-режим на переходный период до готового Docker-образа
    (docs §5.2 п.2) — но это должно быть громко видно в логе при каждом старте,
    не тихим дефолтом.
    """
    import logging
    allow_exec = os.getenv("ALLOW_CODE_EXECUTION", "0") == "1"
    sandbox_direct = os.getenv("SANDBOX_MODE", "direct") == "direct"
    base_url = os.getenv("APP_BASE_URL", "")
    looks_like_prod = base_url.startswith("https") and "localhost" not in base_url \
        and "127.0.0.1" not in base_url
    if allow_exec and sandbox_direct and looks_like_prod:
        logging.critical(
            "⚠️ НЕБЕЗОПАСНАЯ КОНФИГУРАЦИЯ: ALLOW_CODE_EXECUTION=1 и SANDBOX_MODE=direct "
            "с прод-подобным APP_BASE_URL=%s — /api/terminal и /api/run исполняют "
            "команды тенанта БЕЗ изоляции от файловой системы хоста, включая .env "
            "с APP_SECRET (шифрует секреты ВСЕХ тенантов). Собери docker/sandbox."
            "Dockerfile и выставь SANDBOX_MODE=docker до реального трафика — "
            "см. docs/technical-due-diligence-2026-07-17.md §5.2.", base_url)


_warn_if_unsandboxed_execution_in_prod()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # БД SaaS-слоя (пользователи/тенанты). Данные офиса теперь per-tenant (ленивые,
    # загружаются из data/tenants/<tid>/ при обращении) — глобальная загрузка не нужна.
    saas_db.init_db()
    # Менеджер офисов по тенантам (демо — отдельный сценарий под тенантом default)
    runner = demo.run if DEMO_MODE else office_loop.run
    task = asyncio.create_task(runner())
    # Polling Telegram: запускаем всегда — bot_runtime сам решит, нужно ли слушать
    # (на localhost без APP_BASE_URL — всегда, в проде с HTTPS — только если BOT_POLLING=1).
    from src.office import bot_runtime
    poll_task = asyncio.create_task(bot_runtime.run())
    yield
    task.cancel()
    poll_task.cancel()


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Новый React-фронт (миграция, Ф0): собирается Vite в static/webapp, отдаётся на /webapp.
# Старый фронт на / остаётся рабочим до завершения переезда. html=True → отдаёт index.html.
_WEBAPP_DIR = Path("static/webapp")
if _WEBAPP_DIR.is_dir():
    app.mount("/webapp", StaticFiles(directory=str(_WEBAPP_DIR), html=True), name="webapp")

# ---- Rate limiting: routers/shared.py (единый _rate_buckets — /auth/* через
# routers/auth.py и /api/terminal, /api/run, /api/lead/*, /api/onboarding/scan
# здесь используют ОДИН и тот же bucket-механизм, не два раздельных). ----


@app.middleware("http")
async def tenant_middleware(request: Request, call_next):
    """Ставит контекст тенанта из сессии (аноним → 'default')."""
    uid = saas_auth.read_session(request.cookies.get(saas_auth.SESSION_COOKIE, ""))
    tid = "default"
    if uid:
        ws = saas_store.workspace_for_user(uid)
        if ws:
            tid = ws["id"]
    saas_context.set_tenant(tid)
    return await call_next(request)


# Пути /api/*, доступные без авторизации.
# ⚠️ /api/site-lead — публичный приём заявок с опубликованных сайтов: посетитель
# лендинга НЕ авторизован в SaaS, а формы многофайловых сайтов шлют именно сюда
# (critic.check_site это требует). Без исключения посетитель получал 401 и лид терялся.
# ⚠️ /api/onboarding/scan — Instant Learning ДО регистрации (докс/company-
# understanding-vision): моат продукта — «AI уже понимает бизнес» — теряет
# смысл, если сканировать сайт можно только ПОСЛЕ логина. company_scan.scan()
# не пишет ничего в тенант (чистая функция, только httpx GET + regex), так что
# публичный доступ не течёт данные между тенантами; SSRF на внутреннюю сеть
# закрыт отдельно в company_scan._is_private_host (см. её докстринг).
_PUBLIC_API = {"/api/me", "/api/site-lead", "/api/onboarding/scan"}

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Блокирует неавторизованные запросы к /api/* в обычном (не demo) режиме."""
    path = request.url.path
    if not DEMO_MODE and path.startswith("/api/") and path not in _PUBLIC_API \
            and not path.startswith("/api/lead/") and not path.startswith("/api/payments/"):
        uid = saas_auth.read_session(request.cookies.get(saas_auth.SESSION_COOKIE, ""))
        if not uid:
            return JSONResponse({"error": "Требуется авторизация", "auth": False}, status_code=401)
    return await call_next(request)


# Пути, которые кастомный домен НИКОГДА не должен перехватывать — иначе клиент,
# указавший DNS на платформу, случайно закрыл бы себе доступ к API/SPA/другим
# опубликованным сайтам через /site/*.
_RESERVED_PREFIXES = ("/api/", "/auth/", "/webapp/", "/static/", "/site/", "/pay/")


@app.middleware("http")
async def custom_domain_middleware(request: Request, call_next):
    """Отдаёт опубликованный сайт напрямую на кастомном домене клиента
    (docs/product-capability-gaps.md п.5) — outermost middleware (регистрируется
    последним = выполняется первым): для распознанного домена запрос вообще не
    доходит до tenant_middleware/auth_middleware/роутов SPA."""
    host = (request.headers.get("host") or "").split(":")[0].lower()
    path = request.url.path
    if host and not path.startswith(_RESERVED_PREFIXES):
        mapped = domains_module.resolve(host)
        if mapped is not None:
            saas_context.set_tenant(mapped["tenant"])
            site = sites_module.get(mapped["slug"])
            if site is not None:
                domains_module.mark_verified(host)
                subpath = path.lstrip("/") or "index.html"
                if site.get("html") is not None:
                    if subpath in ("", "index.html"):
                        return HTMLResponse(site["html"])
                    return HTMLResponse("<h1>Не найдено</h1>", status_code=404)
                return serve_site_file(site, subpath)
    return await call_next(request)


# admin_panel/index.html — намеренно ОТДЕЛЬНЫЙ статический файл, разворачиваемый
# на изолированном сервере/URL (см. routers/admin.py), поэтому его запросы к
# /admin/api/* кросс-доменные — без явного CORS браузер их заблокирует. Открыто
# для любого origin намеренно: реальная граница доступа — bearer-токен
# ADMIN_API_KEY в заголовке (не куки), так что широкий CORS не ослабляет
# защиту — как и у большинства bearer-token API.
@app.middleware("http")
async def admin_cors_middleware(request: Request, call_next):
    if not request.url.path.startswith("/admin/api/"):
        return await call_next(request)
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "X-Admin-Key, Content-Type",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    }
    if request.method == "OPTIONS":
        return Response(status_code=204, headers=headers)
    response = await call_next(request)
    response.headers.update(headers)
    return response


@app.get("/", response_class=HTMLResponse)
async def index():
    # React SPA на /webapp/
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/webapp/", status_code=302)


# ============================================================
# АУТЕНТИФИКАЦИЯ: вынесена в routers/auth.py (docs/technical-due-diligence-
# 2026-07-17.md §3.2.1, PR-5) — /api/me + все /auth/* (GitHub Device Flow,
# Google/Figma/Bitrix24 OAuth, dev-вход, logout). Тот же код, то же поведение,
# просто не в этом файле — server.py остаётся тонкой точкой сборки.
# ============================================================
app.include_router(auth_router)


@app.get("/events")
async def events(request: Request):
    """SSE endpoint — события только своего тенанта (из контекста запроса)."""
    tid = saas_context.get_tenant()
    q = bus.subscribe(tid)
    # Реконнект браузера: EventSource присылает Last-Event-ID. Тогда снапшот+историю
    # НЕ повторяем (клиент их уже получил) — иначе на каждый разрыв прилетали дубли.
    is_reconnect = bool(request.headers.get("last-event-id"))

    async def stream():
        saas_context.set_tenant(tid)  # контекст для чтения снапшота внутри генератора
        seq = 0
        try:
            if not is_reconnect:
                # Снапшот текущих агентов
                for agent in registry.all_agents():
                    snapshot = {
                        "type": "hired",
                        "agent_id": agent.agent_id,
                        "worker_id": agent.agent_id,  # BOS §12 п.4: agent_id deprecated-алиас
                        "role": agent.role,
                        "desk": agent.desk,
                        "task": agent.task,
                        "status": agent.status,
                        "last_message": agent.last_message,
                    }
                    seq += 1
                    yield f"id: {seq}\ndata: {json.dumps(snapshot, ensure_ascii=False)}\n\n"

                # Исторические события из прошлых сессий
                for evt in state.history()[-50:]:
                    historical = dict(evt, historical=True)
                    seq += 1
                    yield f"id: {seq}\ndata: {json.dumps(historical, ensure_ascii=False)}\n\n"

            # Живой поток — каждому событию свой id, чтобы браузер отслеживал Last-Event-ID
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=30)
                    seq += 1
                    yield f"id: {seq}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            bus.unsubscribe(q)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ============================================================
# Остальные домены вынесены в routers/*.py (docs/technical-due-diligence-
# 2026-07-17.md §3.2.1, PR-5) — весь HTTP-контракт (164 маршрута в одном
# файле → набор роутеров по доменам). Тот же код, то же поведение —
# server.py остаётся точкой сборки, домен ищется по имени файла.
# ============================================================
app.include_router(resources_router)  # Доступы, приложения, MCP-серверы, интеграции
app.include_router(public_router)     # Опубликованные сайты, оплата, приём лидов, боты
app.include_router(team_router)       # Агенты, оргструктура, онбординг, история/трейс
app.include_router(dashboard_router)  # Обзор компании: дайджест, мир, метрики, дашборд
app.include_router(work_router)       # Файлы, план, проекты, процессы, инициативы
app.include_router(settings_router)   # Модели, философия, конституция, автономность
app.include_router(results_router)    # Лиды, сайты, реестр результатов
app.include_router(comms_router)      # Знания, память, вопросы, чаты, чат с CEO
app.include_router(admin_router)      # Админка оператора (ADMIN_API_KEY): тенанты, паузы, прокси, ошибки


