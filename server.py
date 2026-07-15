"""
FastAPI сервер — SSE-стрим событий + статика игры.
"""

import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

# ВАЖНО: load_dotenv() ДО импорта src.saas.auth — тот резолвит APP_SECRET
# (crypto.require_app_secret()) прямо при импорте модуля и падает, если секрет
# не задан. Если .env грузится позже импорта, переменная ещё не видна
# os.environ, и процесс падает даже при корректно заполненном .env.
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from src.office import bus, registry, loop as office_loop, bootstrap as office_bootstrap, demo, chat, brief, state, progress, connections
from src.office import memory
from src.office import threads as threads_module
from src.office import questions as questions_module
from src.office import sites as sites_module
from src.office import leads as leads_module
from src.office import results as results_module
from src.office import ui_prefs as ui_prefs_module
from src.office import costs as costs_module
from src.office import workspace as workspace_module
from src.office import milestones
from src.office import office_channel
from src.office import bot_config as bot_config_module
from src.office import bot_engine as bot_engine_module
from src.office import models as models_module
from src.office import llm_settings as llm_settings_module
from src.office import plan as plan_module
from src.agents import onboarding
from src.agents import orchestrator
from src.office import org
from src.office import intake as intake_module
from src.core import llm as llm_core
from src.integrations import registry as integrations_registry
from src.saas import db as saas_db, store as saas_store, auth as saas_auth
from src.saas import context as saas_context
from src.office import philosophy as philosophy_module
from src.office import constitution as constitution_module
from src.integrations import payments as payments_module
from src.office import domains as domains_module
from src.office import autonomy as autonomy_module
from src.office import trust as trust_module
from src.office import decisions as decisions_module
from src.office import initiatives as initiatives_module
from src.office import health as health_module
from src.office import quality_modes as quality_modes_module
from src.office import skills as skills_module
from src.office import roles as roles_module

DEMO_MODE = os.getenv("DEMO_MODE", "0") == "1"


def _with_worker_id(payload):
    """Зеркалит worker_id рядом с agent_id в исходящем JSON (BOS §12 п.4:
    agent_id → worker_id, agent_id остаётся deprecated-алиасом на переходный
    период). Работает и на одном dict, и на списке dict — тем местам ответа,
    которые НЕ идут через bus.publish (там зеркалирование уже единое, см.
    office/bus.py) и формируются server.py напрямую из registry/state/costs."""
    if isinstance(payload, dict):
        return {**payload, "worker_id": payload["agent_id"]} if "agent_id" in payload else payload
    return [{**d, "worker_id": d["agent_id"]} if isinstance(d, dict) and "agent_id" in d else d
            for d in payload]


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

# ---- Rate limiting (без внешних зависимостей) ----
# Раньше троттлинг был только у /auth/* — /api/terminal, /api/run (дорогое
# исполнение кода) и публичный /api/lead/{tenant}/{slug} (форма без авторизации)
# были ничем не ограничены: тенант с ALLOW_CODE_EXECUTION=1 мог долбить
# execute_code без остановки, а публичную форму лида — спамить с любого IP,
# засоряя CRM/Gap Analysis (docs/audit-dd-2026-07-06.md §11/§19 п.10).
# Один универсальный bucket на (namespace, key), тот же приём анти-утечки:
# чистим мёртвые ключи, только когда bucket раздулся.
_rate_buckets: dict[str, dict[str, list[float]]] = {}


def _rate_limited(namespace: str, key: str, max_per_min: int) -> bool:
    """True — лимит превышен (запрос НУЖНО отклонить). Иначе засчитывает попытку."""
    now = time.time()
    bucket = _rate_buckets.setdefault(namespace, {})
    if len(bucket) > 1000:
        for stale in [k for k, ts in bucket.items() if all(now - t >= 60 for t in ts)]:
            bucket.pop(stale, None)
    attempts = [t for t in bucket.get(key, []) if now - t < 60]
    bucket[key] = attempts
    if len(attempts) >= max_per_min:
        return True
    bucket[key].append(now)
    return False


_MAX_AUTH_PER_MIN = 10


def _check_rate_limit(ip: str) -> bool:
    """Совместимость со старыми вызовами (/auth/*): True — запрос РАЗРЕШЁН."""
    return not _rate_limited("auth", ip, _MAX_AUTH_PER_MIN)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or request.client.host or "unknown"


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
                return _serve_site_file(site, subpath)
    return await call_next(request)


@app.get("/", response_class=HTMLResponse)
async def index():
    # React SPA на /webapp/
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/webapp/", status_code=302)


# ============================================================
# АУТЕНТИФИКАЦИЯ (Phase 0): вход через GitHub + dev-вход + сессии
# ============================================================

def current_user(request: Request) -> dict | None:
    """Текущий пользователь из подписанной session-cookie (или None)."""
    uid = saas_auth.read_session(request.cookies.get(saas_auth.SESSION_COOKIE, ""))
    return saas_store.get_user(uid) if uid else None


def _set_session_cookie(resp, user_id: str) -> None:
    secure = saas_auth.APP_BASE_URL.startswith("https")
    resp.set_cookie(
        saas_auth.SESSION_COOKIE, saas_auth.make_session(user_id),
        max_age=saas_auth.SESSION_TTL, httponly=True, samesite="lax", secure=secure,
    )


@app.get("/api/me")
async def get_me(request: Request):
    """Кто вошёл + его рабочее пространство (тенант). Фронт строит интерфейс по этому."""
    user = current_user(request)
    if not user:
        from src.integrations import google_oauth as _goauth
        return {
            "authenticated":    False,
            "github_available":  saas_auth.github_configured(),
            "google_available":  _goauth.is_configured(),
            "dev_login":         saas_auth.ALLOW_DEV_LOGIN,
        }
    ws = saas_store.workspace_for_user(user["id"])
    return {
        "authenticated": True,
        "user": saas_store.public_user(user),
        "workspace": ({"id": ws["id"], "name": ws["name"], "plan": ws["plan"]} if ws else None),
    }


@app.get("/auth/github/login")
async def github_login():
    """Redirect-OAuth (опционально). Основной метод — Device Flow (/auth/github/device/start)."""
    if not saas_auth.github_configured():
        return JSONResponse({"error": "Задайте GITHUB_CLIENT_ID в .env"}, status_code=400)
    if saas_auth.GITHUB_CLIENT_SECRET:
        return RedirectResponse(saas_auth.github_login_url())
    return JSONResponse({"error": "Используйте Device Flow (/auth/github/device/start)"}, status_code=400)


@app.post("/auth/github/device/start")
async def github_device_start(request: Request):
    """Device Flow шаг 1: получить код для ввода на github.com/login/device."""
    if not _check_rate_limit(_client_ip(request)):
        return JSONResponse({"error": "Слишком много попыток — подождите минуту"}, status_code=429)
    if not saas_auth.github_configured():
        return JSONResponse({"error": "Задайте GITHUB_CLIENT_ID в .env"}, status_code=400)
    try:
        data = await saas_auth.github_device_start()
        return data
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/auth/github/device/poll")
async def github_device_poll(request: Request):
    """Device Flow шаг 2: опросить GitHub на наличие токена."""
    body = await request.json()
    device_code = body.get("device_code", "")
    result = await saas_auth.github_device_poll(device_code)
    if result.get("access_token"):
        token = result["access_token"]
        profile = await saas_auth.github_fetch_profile(token)
        if not profile:
            return JSONResponse({"error": "Не удалось получить профиль"}, status_code=400)
        existing = current_user(request)
        user = existing or saas_store.get_or_create_by_github(profile)
        ws = saas_store.workspace_for_user(user["id"])
        if ws:
            saas_context.set_tenant(ws["id"])
            connections.save({"name": "GitHub", "type": "token", "fields": {"token": token},
                              "note": "Подключено через GitHub Device Flow"})
        resp = JSONResponse({"ok": True, "user": saas_store.public_user(user)})
        _set_session_cookie(resp, user["id"])
        return resp
    return JSONResponse({"pending": True, "error": result.get("error", "")})


@app.get("/auth/github/login-redirect")
async def github_login_redirect():
    """Redirect-OAuth (только если настроен CLIENT_SECRET)."""
    if not saas_auth.GITHUB_CLIENT_SECRET:
        return JSONResponse({"error": "Задайте GITHUB_CLIENT_SECRET для redirect-OAuth"}, status_code=400)
    return RedirectResponse(saas_auth.github_login_url())


@app.get("/auth/github/callback")
async def github_callback(request: Request, code: str = "", state: str = ""):
    if not saas_auth.verify_state(state):
        return JSONResponse({"error": "неверный state"}, status_code=400)
    token = await saas_auth.github_exchange_code(code)
    if not token:
        return JSONResponse({"error": "не удалось получить токен GitHub"}, status_code=400)
    profile = await saas_auth.github_fetch_profile(token)
    if not profile:
        return JSONResponse({"error": "не удалось получить профиль GitHub"}, status_code=400)
    # Если пользователь уже вошёл (напр. dev-вход) — ПОДКЛЮЧАЕМ GitHub к его аккаунту,
    # не подменяя личность. Иначе — это вход через GitHub.
    existing = current_user(request)
    user = existing or saas_store.get_or_create_by_github(profile)
    ws = saas_store.workspace_for_user(user["id"])
    if ws:
        saas_context.set_tenant(ws["id"])
        connections.save({"name": "GitHub", "type": "token", "fields": {"token": token},
                          "note": "Подключено через вход GitHub (OAuth)"})
    resp = RedirectResponse("/")
    _set_session_cookie(resp, user["id"])
    return resp


@app.get("/auth/google/start")
async def google_oauth_start(request: Request, mode: str = "connect"):
    """
    Шаг 1: редирект на страницу согласия Google.
    mode=login   — вход в приложение (создаёт/находит пользователя, ставит сессию)
    mode=connect — только привязывает Google как интеграцию (access к Sheets/Gmail/Calendar)
    """
    from src.integrations import google_oauth
    if not google_oauth.is_configured():
        return JSONResponse(
            {"error": "Задайте GOOGLE_CLIENT_ID и GOOGLE_CLIENT_SECRET в .env"},
            status_code=400,
        )
    import jwt as _jwt
    tenant = saas_context.get_tenant()
    state = _jwt.encode(
        {"k": "google", "tid": tenant, "mode": mode, "exp": int(time.time()) + 600},
        saas_auth.APP_SECRET, algorithm="HS256",
    )
    return RedirectResponse(google_oauth.authorization_url(state))


@app.get("/auth/google/callback")
async def google_oauth_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
):
    """Шаг 2: Google вернул code → обмениваем токены, действуем по mode."""
    if error:
        return RedirectResponse("/webapp/?google_error=denied")
    if not code:
        return JSONResponse({"error": "нет code"}, status_code=400)

    import jwt as _jwt
    try:
        payload = _jwt.decode(state, saas_auth.APP_SECRET, algorithms=["HS256"])
        if payload.get("k") != "google":
            raise ValueError
        tenant_id = payload.get("tid", "default")
        mode      = payload.get("mode", "connect")
    except Exception:
        return JSONResponse({"error": "неверный state"}, status_code=400)

    from src.integrations import google_oauth
    try:
        tokens = await google_oauth.exchange_code(code)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    email = tokens.get("email", "")

    if mode == "login":
        # ── Вход в аккаунт ──────────────────────────────────────────────────
        # Создаём или находим пользователя по email, ставим сессию
        user = saas_store.get_or_create_dev_user(email or "google@unknown")
        ws   = saas_store.workspace_for_user(user["id"])
        if ws:
            saas_context.set_tenant(ws["id"])
            # Также сохраняем Google-токены как интеграцию в этом workspace
            connections.save({
                "name":   "google",
                "type":   "oauth",
                "fields": tokens,
                "note":   f"Google OAuth ({email})" if email else "Google OAuth",
            })
        resp = RedirectResponse("/webapp/")
        _set_session_cookie(resp, user["id"])
        return resp

    else:
        # ── Подключение интеграции (connect) ─────────────────────────────────
        saas_context.set_tenant(tenant_id)
        connections.save({
            "name":   "google",
            "type":   "oauth",
            "fields": tokens,
            "note":   f"Google OAuth ({email})" if email else "Google OAuth",
        })
        return RedirectResponse("/webapp/?connected=google")


@app.post("/auth/google/disconnect")
async def google_oauth_disconnect(request: Request):
    """Отозвать Google-токен и удалить подключение."""
    uid = current_user(request)
    if not uid:
        return JSONResponse({"error": "не авторизован"}, status_code=401)
    from src.integrations import google_oauth
    await google_oauth.revoke()
    return JSONResponse({"ok": True})


@app.get("/auth/figma/login")
async def figma_oauth_login(request: Request):
    """Редирект на страницу согласия Figma (по образцу /auth/google/start,
    без режима login — Figma только подключается как интеграция, не как вход)."""
    from src.integrations import figma_oauth
    if not figma_oauth.is_configured():
        return JSONResponse({"error": "Задайте FIGMA_CLIENT_ID и FIGMA_CLIENT_SECRET в .env"}, status_code=400)
    import jwt as _jwt
    tenant = saas_context.get_tenant()
    state = _jwt.encode(
        {"k": "figma", "tid": tenant, "exp": int(time.time()) + 600},
        saas_auth.APP_SECRET, algorithm="HS256",
    )
    return RedirectResponse(figma_oauth.authorization_url(state))


@app.get("/auth/figma/callback")
async def figma_oauth_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    if error:
        return RedirectResponse("/webapp/?figma_error=denied")
    if not code:
        return JSONResponse({"error": "нет code"}, status_code=400)

    import jwt as _jwt
    try:
        payload = _jwt.decode(state, saas_auth.APP_SECRET, algorithms=["HS256"])
        if payload.get("k") != "figma":
            raise ValueError
        tenant_id = payload.get("tid", "default")
    except Exception:
        return JSONResponse({"error": "неверный state"}, status_code=400)

    from src.integrations import figma_oauth
    try:
        tokens = await figma_oauth.exchange_code(code)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    saas_context.set_tenant(tenant_id)
    handle = tokens.get("handle", "")
    connections.save({"name": "figma", "type": "oauth", "fields": tokens,
                       "note": f"Figma OAuth ({handle})" if handle else "Figma OAuth"})
    return RedirectResponse("/webapp/?connected=figma")


@app.post("/auth/figma/disconnect")
async def figma_oauth_disconnect(request: Request):
    uid = current_user(request)
    if not uid:
        return JSONResponse({"error": "не авторизован"}, status_code=401)
    from src.integrations import figma_oauth
    await figma_oauth.revoke()
    return JSONResponse({"ok": True})


@app.get("/auth/bitrix24/login")
async def bitrix24_oauth_login(request: Request, portal: str = ""):
    """Редирект на страницу согласия Bitrix24 — В ОТЛИЧИЕ от Google/Figma нужен
    домен портала клиента (Bitrix24 multi-tenant, нет единой страницы согласия),
    поэтому фронт сначала спрашивает домен и передаёт его сюда параметром."""
    from src.integrations import bitrix24_oauth
    if not bitrix24_oauth.is_configured():
        return JSONResponse({"error": "Задайте BITRIX24_CLIENT_ID и BITRIX24_CLIENT_SECRET в .env"}, status_code=400)
    if not portal.strip():
        return JSONResponse({"error": "Нужен домен портала Bitrix24 (например my-company.bitrix24.ru)"}, status_code=400)
    import jwt as _jwt
    tenant = saas_context.get_tenant()
    state = _jwt.encode(
        {"k": "bitrix24", "tid": tenant, "portal": portal.strip(), "exp": int(time.time()) + 600},
        saas_auth.APP_SECRET, algorithm="HS256",
    )
    try:
        return RedirectResponse(bitrix24_oauth.authorization_url(portal, state))
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.get("/auth/bitrix24/callback")
async def bitrix24_oauth_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    if error:
        return RedirectResponse("/webapp/?bitrix24_error=denied")
    if not code:
        return JSONResponse({"error": "нет code"}, status_code=400)

    import jwt as _jwt
    try:
        payload = _jwt.decode(state, saas_auth.APP_SECRET, algorithms=["HS256"])
        if payload.get("k") != "bitrix24":
            raise ValueError
        tenant_id = payload.get("tid", "default")
        portal = payload.get("portal", "")
    except Exception:
        return JSONResponse({"error": "неверный state"}, status_code=400)

    from src.integrations import bitrix24_oauth
    try:
        tokens = await bitrix24_oauth.exchange_code(code, portal)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    saas_context.set_tenant(tenant_id)
    domain = tokens.get("domain", portal)
    connections.save({"name": "bitrix24", "type": "oauth", "fields": tokens,
                       "note": f"Bitrix24 OAuth ({domain})" if domain else "Bitrix24 OAuth"})
    return RedirectResponse("/webapp/?connected=bitrix24")


@app.post("/auth/bitrix24/disconnect")
async def bitrix24_oauth_disconnect(request: Request):
    uid = current_user(request)
    if not uid:
        return JSONResponse({"error": "не авторизован"}, status_code=401)
    from src.integrations import bitrix24_oauth
    bitrix24_oauth.revoke()
    return JSONResponse({"ok": True})


@app.post("/auth/dev-login")
async def dev_login(request: Request):
    """Локальный вход без GitHub (только если ALLOW_DEV_LOGIN=1)."""
    if not _check_rate_limit(_client_ip(request)):
        return JSONResponse({"error": "Слишком много попыток — подождите минуту"}, status_code=429)
    if not saas_auth.ALLOW_DEV_LOGIN:
        return JSONResponse({"error": "dev-вход отключён"}, status_code=403)
    data = await request.json()
    email = (data.get("email") or "dev@local").strip()
    if not email or "@" not in email:
        return JSONResponse({"error": "Укажите корректный email"}, status_code=400)
    user = saas_store.get_or_create_dev_user(email)
    resp = JSONResponse({"ok": True, "user": saas_store.public_user(user)})
    _set_session_cookie(resp, user["id"])
    return resp


@app.post("/auth/logout")
async def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(saas_auth.SESSION_COOKIE)
    return resp


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


@app.get("/api/workspace")
async def get_workspace(request: Request):
    """Данные текущего рабочего пространства (тенанта)."""
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "auth required"}, status_code=401)
    ws = saas_store.workspace_for_user(user["id"])
    if not ws:
        return JSONResponse({"error": "workspace not found"}, status_code=404)
    return {"id": ws["id"], "name": ws["name"], "plan": ws["plan"], "created_at": ws["created_at"]}


@app.post("/api/workspace/name")
async def rename_workspace(request: Request):
    """Переименовать рабочее пространство."""
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "auth required"}, status_code=401)
    data = await request.json()
    name = (data.get("name") or "").strip()
    if not name:
        return JSONResponse({"error": "name обязателен"}, status_code=400)
    from src.saas import db as saas_db
    saas_db.execute("UPDATE workspaces SET name=? WHERE owner_user_id=?", (name, user["id"]))
    ws = saas_store.workspace_for_user(user["id"])
    return {"ok": True, "workspace": {"id": ws["id"], "name": ws["name"], "plan": ws["plan"]}}


@app.get("/api/agents")
async def get_agents():
    return _with_worker_id([
        {
            "agent_id": a.agent_id,
            "role": a.role,
            "desk": a.desk,
            "status": a.status,
            "last_message": a.last_message,
            "task": a.task,
            "project_id": a.project_id,
        }
        for a in registry.all_agents()
    ])


@app.get("/api/brief/status")
async def brief_status():
    """Фронт проверяет: нужен ли онбординг, или офис уже работает."""
    return {"ready": brief.is_ready(), "demo": DEMO_MODE, "brief": brief.get()}


@app.post("/api/brief/questions")
async def brief_questions(request: Request):
    """Шаг 1: клиент прислал ввод → офис задаёт уточняющие вопросы."""
    data = await request.json()
    client_input = (data.get("input") or "").strip()
    if not client_input:
        return JSONResponse({"error": "пустой ввод"}, status_code=400)
    try:
        questions = await onboarding.make_questions(client_input, publish=bus.publish)
        return {"questions": questions}
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=500)


@app.post("/api/brief/start")
async def brief_start(request: Request):
    """Минимальный онбординг (BOS §5): 1 необязательное поле + необязательная
    ссылка → бриф и старт офиса. Уточняющие вопросы (make_questions) больше не
    обязательный шаг — answers пуст в большинстве случаев, build_brief() уже
    умеет работать с пустым qa_pairs (см. докстринг). Пустой client_input и url
    одновременно раньше отклонялись 400 — теперь честно "разбирайтесь сами":
    build_brief() имеет подстраховку (summary = client_input[:500]), просто
    даём ей плейсхолдер вместо ошибки — иначе кнопка "Пропустить" в UI была бы
    ложью."""
    data = await request.json()
    client_input = (data.get("input") or "").strip()
    url = (data.get("url") or "").strip()
    qa_pairs = data.get("answers", [])
    # Клиент мог уже увидеть скан на лендинге (issue #19, публичный /api/onboarding/
    # scan ДО регистрации) — если фронт прислал готовый результат, не сканируем
    # тот же сайт второй раз (лишний сетевой поход + задержка онбординга ради
    # данных, которые уже есть).
    precomputed_scan = data.get("scan") or None

    effective_input = client_input
    scan_url = ""
    from src.office import company_scan
    scan_result = precomputed_scan if (precomputed_scan and precomputed_scan.get("ok")) else None
    if scan_result is None and url:
        scan_result = await company_scan.scan(url)
    if scan_result and scan_result.get("ok"):
        scan_url = scan_result.get("url", "")
        effective_input = (effective_input + "\n\n" + company_scan.summary_line(scan_result)).strip()
    if not effective_input:
        effective_input = "Клиент не описал бизнес словами — общий старт, офис исследует сам."

    try:
        brief_data = await onboarding.build_brief(effective_input, qa_pairs, publish=bus.publish)
        # Гипотеза о стадии бизнеса (issue #21) — если владелец её видел/поправил на
        # лендинге, она уже часть scan_result.stage (ScanBox мутирует sessionStorage
        # при клике на кнопку-корректировку); не переспрашиваем и не теряем правку.
        if scan_result and scan_result.get("stage"):
            brief_data["business_stage"] = scan_result["stage"]
        if scan_url:
            brief_data["scan_url"] = scan_url
        brief.set_brief(brief_data)  # сигналит офису о старте
        return {"ok": True, "brief": brief_data}
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=500)


@app.post("/api/onboarding/scan")
async def onboarding_scan(request: Request):
    """Instant Learning: клиент даёт URL сайта → офис изучает его за секунды,
    БЕЗ единого вопроса и без LLM (company_scan.py). Вау-эффект первых секунд
    онбординга — «мы уже кое-что знаем о вас».

    Публичный эндпоинт (см. _PUBLIC_API) — доступен ДО регистрации/логина,
    иначе моат «AI уже понимает бизнес» не проявляется до формы. Именно
    поэтому здесь отдельный rate-limit по IP: без сессии/тенанта как ключа
    анонимный эндпоинт, делающий исходящий HTTP GET по любому URL, — готовый
    вектор для использования сервера как открытого прокси/сканера."""
    if _rate_limited("scan", _client_ip(request), 12):
        return JSONResponse({"error": "Слишком много запросов, попробуйте через минуту"}, status_code=429)
    data = await request.json()
    url = (data.get("url") or "").strip()
    if not url:
        return JSONResponse({"error": "пустой url"}, status_code=400)
    from src.office import company_scan
    result = await company_scan.scan(url)
    return result


@app.get("/api/onboarding/modes")
async def onboarding_modes():
    """3 сценария входа + вопросы интервью по каждому (для онбординг-флоу)."""
    out = []
    for key, meta in onboarding.MODES.items():
        out.append({
            "key": key,
            "title": meta["title"],
            "icon": meta["icon"],
            "intro": meta["intro"],
            "questions": onboarding.interview_questions(key),
        })
    return {"modes": out}


@app.post("/api/onboarding/finish")
async def onboarding_finish(request: Request):
    """Завершение интервью: {mode, answers} → детерминированный бриф → старт офиса."""
    data = await request.json()
    mode = (data.get("mode") or "business").strip()
    answers = data.get("answers", [])
    scan_result = data.get("scan") or None
    if not any((a.get("answer") or "").strip() for a in answers):
        return JSONResponse({"error": "нет ответов"}, status_code=400)
    brief_data = onboarding.build_brief_structured(mode, answers, scan_result=scan_result)
    # Сохраняем ответы интервью в память — слой USER для retrieval (knowledge.py)
    from src.office import memory as memory_module
    for a in answers:
        q, ans = (a.get("question") or "").strip(), (a.get("answer") or "").strip()
        if q and ans:
            memory_module.remember(q, ans)
    brief.set_brief(brief_data)  # сигналит офису о старте
    await bus.publish({"type": "speech", "agent_id": "orchestrator_1",
                       "text": f"Компания изучена. Запускаю офис: {brief_data.get('goal', '')[:80]}"})
    return {"ok": True, "brief": brief_data}


@app.get("/api/onboarding/result")
async def get_onboarding_result():
    """Первое впечатление клиента (BOS §5) — аналитика + точки роста +
    инициативы, сгенерированные один раз сразу после стратегии (см.
    office/loop.py, office/onboarding_result.py). ready=False, пока BOOTSTRAP
    ещё не дошёл до этого шага — фронт показывает "офис изучает..."."""
    from src.office import onboarding_result as onboarding_result_module, initiatives as initiatives_module
    d = onboarding_result_module.get()
    if not d:
        return {"ready": False, "analysis": [], "growth_points": [], "initiatives": []}
    ini_ids = set(d.get("initiative_ids") or [])
    inis = [i for i in initiatives_module.pending() if i["id"] in ini_ids]
    return {"ready": True, "analysis": d.get("analysis", []),
            "growth_points": d.get("growth_points", []), "initiatives": inis}


@app.get("/api/onboarding/suggested-integrations")
async def get_suggested_integrations():
    """Интеграции, подобранные под текст брифа — момент пиковой мотивации
    сразу после результата онбординга (см. integrations/registry.suggested_for),
    не спрятаны в «Компания → Доступы»."""
    from src.integrations import registry as integrations_registry
    b = brief.get()
    text = " ".join(str(b.get(k, "")) for k in ("summary", "goal", "niche", "audience"))
    stage_key = (b.get("business_stage") or {}).get("key", "")
    return {"integrations": integrations_registry.suggested_for(text, business_stage=stage_key)}


@app.get("/api/history")
async def get_history():
    """Лента событий из прошлых запусков — фронт показывает её при загрузке."""
    return {"events": state.history(), "results": {
        a.agent_id: state.result_for(a.agent_id) for a in registry.all_agents()
    }}


@app.get("/api/logs")
async def get_logs():
    """Полный текстовый лог работы офиса — можно скачать и прислать на анализ."""
    from datetime import datetime
    import time as _time

    lines = []
    lines.append("=" * 60)
    lines.append("AI OFFICE — ЛОГ РАБОТЫ")
    lines.append(f"Сформирован: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
    lines.append("=" * 60)

    # Бриф
    b = brief.get()
    if b:
        lines.append("\n## БРИФ КЛИЕНТА")
        for k, v in b.items():
            lines.append(f"  {k}: {v}")

    # Модели
    lines.append("\n## МОДЕЛИ")
    lines.append(f"  по умолчанию: {models_module.get_default()}")
    for aid, m in models_module.assignments().items():
        lines.append(f"  {aid}: {m}")

    # Расход токенов и стоимость
    ct = costs_module.totals()
    lines.append("\n## РАСХОД (токены / стоимость)")
    lines.append(f"  Итого: ${ct['cost']:.4f} | токенов вход {ct['in_tokens']} / выход {ct['out_tokens']} | вызовов {ct['calls']}")
    for a in costs_module.by_agent():
        lines.append(f"  {a['agent_id']} ({a.get('model','')}): ${a['cost']:.4f} | "
                     f"вход {a['in_tokens']} / выход {a['out_tokens']} | вызовов {a['calls']}")

    # Команда — сгруппирована по проектам (реальный кейс: живой UI TeamView.tsx
    # группирует с 2026-07-06, этот текстовый экспорт — нет; клиент, скачавший
    # лог прогона с двумя параллельными проектами, видел плоский список без
    # деления и решил, что разделения по проектам не существует вовсе).
    from src.office import projects as projects_module
    lines.append("\n## КОМАНДА")
    proj_titles = {p["id"]: p["title"] for p in projects_module.all_projects()}
    by_project: dict[str, list] = {}
    for a in registry.all_agents():
        by_project.setdefault(a.project_id or "", []).append(a)
    # Штаб (без project_id) — первой секцией, дальше проекты в порядке появления.
    for pid in sorted(by_project.keys(), key=lambda p: (p != "", p)):
        label = "Штаб (без привязки к проекту)" if not pid else f"Проект «{proj_titles.get(pid, pid)}»"
        lines.append(f"  --- {label} ---")
        for a in by_project[pid]:
            lines.append(f"  [{a.status}] {a.agent_id} ({a.role}) — {a.task[:80]}")
            if a.last_message:
                lines.append(f"      последнее: {a.last_message[:120]}")

    # Этапы
    lines.append("\n## ЭТАПЫ ПУТИ")
    for s in milestones.all_stages():
        lines.append(f"  [{s['status']}] {s['title']} (id={s['id']}, записей: {len(s['items'])})")
        if s["summary"]:
            lines.append(f"      сводка: {s['summary'][:200]}")

    # Лента событий
    lines.append("\n## ЛЕНТА СОБЫТИЙ")
    for e in state.history():
        etype = e.get("type", "")
        who = e.get("agent_id", "")
        txt = e.get("text") or e.get("summary") or ""
        lines.append(f"  [{etype}] {who}: {txt[:200]}")

    # Детальный системный трейс — с временем, инструментами, длительностями, моделями,
    # токенами, публикациями, вердиктами критика. Это «всё, что произошло внутри».
    from src.office import trace as _trace
    trace_text = _trace.as_text(2000)
    if trace_text:
        lines.append("\n## ДЕТАЛЬНЫЙ ТРЕЙС (системный, с временными метками)")
        lines.append(trace_text)

    # Готовые результаты (полные)
    lines.append("\n## ГОТОВЫЕ РЕЗУЛЬТАТЫ (полный текст)")
    for d in state.deliverables():
        lines.append(f"\n  --- {d.get('role')} / {d.get('task','')[:60]} ({d.get('time','')}) ---")
        lines.append(d.get("content", ""))

    # Память (ответы пользователя)
    lines.append("\n## ПАМЯТЬ (ответы пользователя)")
    for m in memory.all_entries():
        lines.append(f"  В: {m.get('question','')}")
        lines.append(f"  О: {m.get('answer','')}")

    text = "\n".join(lines)
    fname = f"ai-office-log-{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    return StreamingResponse(
        iter([text]),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.get("/api/trace")
async def get_trace(limit: int = 400):
    """Детальный системный трейс (JSON): время, инструменты, длительности, публикации."""
    from src.office import trace as _trace
    return {"trace": _trace.tail(max(1, min(limit, 4000)))}


@app.get("/api/observability/timeline")
async def get_observability_timeline(limit: int = 400, since: float | None = None,
                                     until: float | None = None):
    """Единая временная шкала офиса: trace + промпты + решения + срезы мира,
    слитые по времени с перекрёстными ссылками (Phase 0.5)."""
    from src.office import observability
    return {"timeline": observability.timeline(since=since, until=until,
                                               limit=max(1, min(limit, 2000)))}


@app.get("/api/observability/decision/{decision_id}")
async def get_observability_decision(decision_id: str):
    """Полная цепочка одного решения: промпт → исполнение (trace) → world.diff
    до/после (Phase 0.5 DoD)."""
    from src.office import observability
    return observability.decision_chain(decision_id)


@app.get("/api/deliverables")
async def get_deliverables():
    """Готовые результаты работы агентов — пользователь может посмотреть и скопировать."""
    return {"deliverables": _with_worker_id(state.deliverables())}


@app.get("/api/progress")
async def get_progress():
    """Текущий этап развития офиса для индикатора прогресса (динамические этапы)."""
    return milestones.progress_payload()


@app.get("/api/milestones")
async def get_milestones():
    """Полный список этапов со сводками и записями проделанной работы."""
    return {"stages": milestones.all_stages()}


@app.get("/api/milestone/{stage_id}")
async def get_milestone(stage_id: str):
    """Детали одного этапа: сводка + что уже сделано."""
    m = milestones.get(stage_id)
    if m is None:
        return JSONResponse({"error": "этап не найден"}, status_code=404)
    return m


@app.get("/api/agent/{agent_id}")
async def get_agent_detail(agent_id: str):
    """Карточка агента: что делает сейчас и что уже сделал."""
    rec = registry.get(agent_id)
    if rec is None:
        return JSONResponse({"error": "агент не найден"}, status_code=404)
    return {
        "agent_id": rec.agent_id,
        "worker_id": rec.agent_id,  # BOS §12 п.4: agent_id deprecated-алиас
        "role": rec.role,
        "status": rec.status,
        "task": rec.task,
        "current": rec.last_message or rec.task,
        "done": _with_worker_id(state.deliverables_for(agent_id)),
        "activity": _with_worker_id(state.events_for(agent_id)),
        "model": models_module.for_agent(agent_id),
        "model_custom": agent_id in models_module.assignments(),
        "cost": costs_module.for_agent(agent_id),
    }


@app.get("/api/connections")
async def get_connections():
    return {"connections": connections.list_all()}


@app.post("/api/connections")
async def save_connection(request: Request):
    data = await request.json()
    if not (data.get("name") or "").strip():
        return JSONResponse({"error": "название обязательно"}, status_code=400)
    item = connections.save(data)
    return {"ok": True, "connection": item}


@app.delete("/api/connections/{cid}")
async def delete_connection(cid: str):
    ok = connections.delete(cid)
    return {"ok": ok}


@app.get("/api/apps")
async def get_hosted_apps():
    """Постоянные приложения тенанта (office/tenant_apps.py) — вкладка «Приложения»."""
    from src.office import tenant_apps
    return {"apps": tenant_apps.list_all()}


@app.get("/api/apps/{app_id}")
async def get_hosted_app_detail(app_id: str):
    """Детали приложения — включая РАСШИФРОВАННЫЕ env (владелец их сам и вводил,
    показать ему обратно — не утечка, тот же принцип, что connections.py) и
    docker-compose.yml для просмотра, что реально поднято."""
    from src.office import tenant_apps
    item = tenant_apps.get(app_id)
    if item is None:
        return JSONResponse({"error": "не найдено"}, status_code=404)
    return {**item, "env_values": tenant_apps.env_values(app_id), "compose_yaml": tenant_apps.compose_yaml(app_id)}


@app.get("/api/apps/{app_id}/logs")
async def get_hosted_app_logs(app_id: str, tail: int = 100):
    from src.office import tenant_apps
    if tenant_apps.get(app_id) is None:
        return JSONResponse({"error": "не найдено"}, status_code=404)
    return {"logs": tenant_apps.logs(app_id, tail=tail)}


@app.post("/api/apps/{app_id}/pause")
async def pause_hosted_app(app_id: str):
    from src.office import tenant_apps
    ok = tenant_apps.stop(app_id)
    return {"ok": ok, "app": tenant_apps.get(app_id)}


@app.post("/api/apps/{app_id}/resume")
async def resume_hosted_app(app_id: str):
    from src.office import tenant_apps
    ok = tenant_apps.start(app_id)
    return {"ok": ok, "app": tenant_apps.get(app_id)}


@app.delete("/api/apps/{app_id}")
async def delete_hosted_app(app_id: str):
    from src.office import tenant_apps
    ok = tenant_apps.remove(app_id)
    return {"ok": ok}


@app.get("/api/mcp-servers")
async def get_mcp_servers():
    """Тенантские MCP-серверы (office/mcp_tenant_servers.py) — подключает их
    агент (register_external_api/discover_resource), владелец здесь только
    просматривает и может отключить, симметрично /api/apps."""
    from src.office import mcp_tenant_servers
    return {"servers": mcp_tenant_servers.list_all()}


@app.get("/api/mcp-servers/{server_id}")
async def get_mcp_server_detail(server_id: str):
    from src.office import mcp_tenant_servers
    servers = mcp_tenant_servers.list_all()
    item = next((s for s in servers if s["id"] == server_id), None)
    if item is None:
        return JSONResponse({"error": "не найдено"}, status_code=404)
    return {**item, "env_values": mcp_tenant_servers.env_values(server_id)}


@app.delete("/api/mcp-servers/{server_id}")
async def delete_mcp_server(server_id: str):
    from src.office import mcp_tenant_servers
    ok = mcp_tenant_servers.remove(server_id)
    return {"ok": ok}


@app.get("/api/integrations")
async def get_integrations():
    """Каталог поддерживаемых интеграций со статусом подключения."""
    return {"integrations": integrations_registry.catalog_payload()}


@app.post("/api/integrations/{name}/test")
async def test_integration(name: str):
    """Проверяет подключение: запускает безопасное действие без обязательных параметров."""
    integ = integrations_registry.get(name)
    if integ is None:
        return JSONResponse({"error": "интеграция не найдена"}, status_code=404)
    if not integrations_registry.is_connected(integ):
        return JSONResponse({"error": "нет учётных данных — добавьте подключение"}, status_code=400)
    # Берём действие-пинг: первое без обязательных параметров
    ping = next((a for a in integ.actions.values() if not a.required), None)
    if ping is None:
        return JSONResponse({"error": "у интеграции нет проверочного действия"}, status_code=400)
    creds = integrations_registry.credentials_for(integ)
    try:
        result = await ping.handler(creds, {})
        await bus.publish({"type": "integration_used", "agent_id": "user",
                           "integration": integ.name, "action": ping.name,
                           "text": f"⚙️ Проверка {integ.title}: {result[:120]}"})
        return {"ok": True, "result": result}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)[:200]}, status_code=200)


@app.get("/api/integrations/telegram_personal/config")
async def telegram_personal_config():
    """Заданы ли ключи ПРИЛОЖЕНИЯ оператором (.env) — если да, форма входа не
    просит пользователя искать api_id/api_hash на my.telegram.org самому."""
    from src.office import telegram_login
    return {"has_default_creds": telegram_login.has_default_creds()}


@app.post("/api/integrations/telegram_personal/login/start")
async def telegram_personal_login_start(request: Request):
    """Шаг 1 входа в личный Telegram: запросить код на телефон. Body: {phone,
    api_id?, api_hash?} — последние два нужны, только если оператор не задал
    TELEGRAM_API_ID/TELEGRAM_API_HASH в .env (см. office/telegram_login.py)."""
    from src.office import telegram_login
    data = await request.json()
    phone = (data.get("phone") or "").strip()
    if not phone:
        return JSONResponse({"error": "нужен phone"}, status_code=400)
    api_id = 0
    if data.get("api_id"):
        try:
            api_id = int(data["api_id"])
        except (TypeError, ValueError):
            return JSONResponse({"error": "api_id должен быть числом"}, status_code=400)
    api_hash = (data.get("api_hash") or "").strip()
    if not telegram_login.has_default_creds() and (not api_id or not api_hash):
        return JSONResponse({"error": "нужны api_id и api_hash (оператор не задал их в .env)"},
                            status_code=400)
    tid = saas_context.get_tenant()
    result = await telegram_login.start(tid, phone, api_id, api_hash)
    return result


@app.post("/api/integrations/telegram_personal/login/confirm")
async def telegram_personal_login_confirm(request: Request):
    """Шаг 2: подтвердить код (+ 2FA-пароль при need_password). Body: {code, password?}."""
    from src.office import telegram_login
    data = await request.json()
    tid = saas_context.get_tenant()
    result = await telegram_login.confirm(tid, data.get("code", ""), data.get("password", ""))
    return result


@app.post("/api/integrations/telegram_personal/login/cancel")
async def telegram_personal_login_cancel():
    from src.office import telegram_login
    telegram_login.cancel(saas_context.get_tenant())
    return {"ok": True}


@app.post("/api/leads/{lead_id}/followup")
async def send_lead_followup(lead_id: str, request: Request):
    """Отправить follow-up лиду напрямую в Telegram-ЛС (личный аккаунт) и записать
    в историю лида. Body: {text}. Target берётся из contact лида — если это не
    @username/телефон, интеграция сама вернёт понятную причину отказа."""
    data = await request.json()
    text = (data.get("text") or "").strip()
    if not text:
        return JSONResponse({"error": "text обязателен"}, status_code=400)
    lead = leads_module.get(lead_id)
    if not lead:
        return JSONResponse({"error": "лид не найден"}, status_code=404)
    integ = integrations_registry.get("telegram_personal")
    if not integrations_registry.is_connected(integ):
        return JSONResponse({"error": "нет активной сессии личного Telegram — подключите в «Доступы»"},
                            status_code=400)
    creds = integrations_registry.credentials_for(integ)
    result = await integ.actions["send_dm"].handler(creds, {"target": lead["contact"], "text": text})
    sent = "отправлено" in result.lower()
    leads_module.add_note(lead_id, f"Telegram: {text[:80]}" if sent else f"⚠ Не отправлено: {result[:150]}",
                          by="owner")
    return {"ok": sent, "result": result}


@app.get("/site/{tenant}/{slug}", response_class=HTMLResponse)
async def serve_site(tenant: str, slug: str):
    """Отдаёт опубликованный сайт тенанта (публично). Инлайн-лендинг или папка с файлами."""
    saas_context.set_tenant(tenant)
    site = sites_module.get(slug)
    if site is None:
        return HTMLResponse("<h1>Страница не найдена</h1>", status_code=404)
    if site.get("html") is not None:
        return HTMLResponse(site["html"])  # шаблонный лендинг (publish_landing)
    return _serve_site_file(site, "index.html")  # многофайловый сайт (publish_site)


@app.get("/site/{tenant}/{slug}/{path:path}")
async def serve_site_asset(tenant: str, slug: str, path: str):
    """Отдаёт ресурс многофайлового сайта (css/js/картинки/доп. страницы)."""
    saas_context.set_tenant(tenant)
    site = sites_module.get(slug)
    if site is None or site.get("html") is not None:
        return HTMLResponse("<h1>Не найдено</h1>", status_code=404)
    return _serve_site_file(site, path or "index.html")


@app.api_route("/apps/{tenant}/{app_id}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
@app.api_route("/apps/{tenant}/{app_id}/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_tenant_app(request: Request, tenant: str, app_id: str, path: str = ""):
    """Reverse-proxy к постоянному приложению тенанта (office/tenant_apps.py —
    например self-hosted Postiz). Тенант НЕ получает прямой сетевой доступ к
    порту хоста — платформа проксирует запрос сама, тот же приём, что уже есть
    у /site/{tenant}/{slug} для лендингов, только двусторонний (методы+тело)."""
    saas_context.set_tenant(tenant)
    from src.office import tenant_apps
    app_item = tenant_apps.get(app_id)
    if app_item is None or app_item.get("status") != "running":
        return HTMLResponse("<h1>Приложение не найдено или не запущено</h1>", status_code=404)
    import httpx
    url = f"http://127.0.0.1:{app_item['host_port']}/{path}"
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")}
    body = await request.body()
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            upstream = await client.request(request.method, url, params=request.query_params,
                                             headers=headers, content=body)
    except httpx.ConnectError:
        return HTMLResponse("<h1>Приложение не отвечает</h1>", status_code=502)
    resp_headers = {k: v for k, v in upstream.headers.items()
                    if k.lower() not in ("content-encoding", "transfer-encoding", "connection")}
    return Response(content=upstream.content, status_code=upstream.status_code,
                    headers=resp_headers, media_type=upstream.headers.get("content-type"))


@app.get("/pay/{tenant}/{payment_id}", response_class=HTMLResponse)
async def serve_test_checkout(tenant: str, payment_id: str):
    """Публичная TEST-страница оплаты (см. src/integrations/payments.py) — пока нет
    реального провайдера, ссылка ведёт сюда и позволяет вручную «оплатить» для
    проверки сценария целиком (форма → лид → ссылка на оплату → статус paid)."""
    saas_context.set_tenant(tenant)
    p = payments_module.get(payment_id)
    if p is None:
        return HTMLResponse("<h1>Платёж не найден</h1>", status_code=404)
    paid = p["status"] == "paid"
    action = ("<p style='color:#1a7a4a;font-weight:600'>✅ Оплачено (тест)</p>" if paid else
              f"<form method='post' action='/api/payments/{tenant}/{payment_id}/mark-paid'>"
              f"<button style='padding:12px 20px;font-size:16px;border-radius:8px;border:none;"
              f"background:#1a7a4a;color:#fff;cursor:pointer'>Оплатить (тест)</button></form>")
    return HTMLResponse(f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<title>Тестовая оплата</title></head>
<body style="font-family:system-ui,sans-serif;max-width:420px;margin:60px auto;text-align:center">
<h2>{p['description']}</h2>
<p style="font-size:28px;font-weight:700">{p['amount']} {p['currency']}</p>
<p style="color:#888;font-size:13px">⚠️ Тестовый режим — реальный платёжный провайдер не подключён,
деньги не списываются.</p>
{action}
</body></html>""")


@app.post("/api/payments/{tenant}/{payment_id}/mark-paid")
async def mark_payment_paid(tenant: str, payment_id: str):
    """Имитация вебхука провайдера — единственный способ перевести тестовый платёж
    в paid, пока реального провайдера нет (см. payments.py::mark_paid)."""
    saas_context.set_tenant(tenant)
    p = payments_module.mark_paid(payment_id)
    if p is None:
        return JSONResponse({"error": "платёж не найден или уже обработан"}, status_code=404)
    return RedirectResponse(url=f"/pay/{tenant}/{payment_id}", status_code=303)


# Публично отдаём только веб-ресурсы. Если сайт опубликован из КОРНЯ workspace
# (root==""), без этого фильтра были бы доступны bot.py с токенами, docs/*, .env и т.п.
_WEB_ASSET_EXT = {
    ".html", ".htm", ".css", ".js", ".mjs", ".map", ".json", ".svg", ".png", ".jpg",
    ".jpeg", ".gif", ".webp", ".avif", ".ico", ".woff", ".woff2", ".ttf", ".otf",
    ".mp4", ".webm", ".mp3", ".txt", ".xml", ".webmanifest",
}
# Явно приватное — никогда не отдаём, даже если попало в веб-папку.
_FORBIDDEN_NAMES = {".env", "requirements.txt", "config.py", "bot.py", "main.py"}


def _serve_site_file(site: dict, subpath: str):
    """Отдаёт файл из папки опубликованного сайта с корректным content-type.

    Резолвит путь ВНУТРИ project_dir этого сайта (Фаза 3, параллельные проекты —
    у каждого проекта своя подпапка workspace/{project_dir}/). Реальный кейс:
    без этого HTTP-обработчик резолвил "site/index.html" от КОРНЯ workspace
    тенанта (там, где такой папки физически нет для проектных сайтов) — публикация
    отчитывалась об успехе, но публичный адрес отдавал 404 для ЛЮБОГО из
    параллельных проектов. site["project_dir"] пишет sites.save_dir/save на
    момент публикации (workspace.get_project_dir() ТОГДА, не сейчас — HTTP-запрос
    не имеет собственного project-скоупа)."""
    import mimetypes
    import re as _re
    from pathlib import PurePosixPath
    from fastapi.responses import Response
    root = (site.get("root") or "").strip("/")
    rel = (f"{root}/{subpath}").strip("/") if root else subpath
    # Защита от отдачи исходников/секретов при публикации из корня workspace.
    name = PurePosixPath(rel).name.lower()
    ext = PurePosixPath(rel).suffix.lower()
    if name in _FORBIDDEN_NAMES or (ext and ext not in _WEB_ASSET_EXT):
        return HTMLResponse("<h1>Не найдено</h1>", status_code=404)
    with workspace_module.project_scope(site.get("project_dir", "")):
        full = workspace_module.resolve(rel)
        if full is None or not full.is_file():
            idx = (f"{root}/index.html").strip("/") if root else "index.html"
            full = workspace_module.resolve(idx)
    if full is None or not full.is_file():
        return HTMLResponse("<h1>Страница не найдена</h1>", status_code=404)
    ctype = mimetypes.guess_type(str(full))[0] or "application/octet-stream"
    if ctype == "text/html":
        # Внедряем <base>, чтобы относительные пути (css/js/картинки/ссылки между
        # страницами) резолвились от /site/{tenant}/{slug}/, а не от /site/{tenant}/.
        tid = saas_context.get_tenant()
        base = f'<base href="/site/{tid}/{site["slug"]}/">'
        html = full.read_text(encoding="utf-8", errors="replace")
        if "<base" not in html.lower():
            if _re.search(r"<head[^>]*>", html, _re.IGNORECASE):
                html = _re.sub(r"(<head[^>]*>)", r"\1" + base, html, count=1, flags=_re.IGNORECASE)
            else:
                html = base + html
        return HTMLResponse(html)
    return Response(content=full.read_bytes(), media_type=ctype)


async def _notify_lead(lead: dict) -> None:
    """
    Заметное уведомление о новой заявке: событие в ленту + сообщение в личный чат CEO,
    чтобы сработал бейдж непрочитанного (раньше лид был только строкой в SSE-ленте и
    легко терялся — для лид-ген продукта это ключевое событие).
    """
    text = f"🎯 Новая заявка с сайта: {lead.get('name') or 'без имени'} — {lead.get('contact','')}"
    if (lead.get("message") or "").strip():
        text += f'\n«{lead["message"][:160]}»'
    await bus.publish({"type": "lead_captured", "slug": lead.get("slug", ""), "lead": lead, "text": text})
    try:
        threads_module.post("orchestrator_1", "agent", text, kind="msg")
        await bus.publish({"type": "agent_message", "agent_id": "orchestrator_1",
                           "from": "agent", "kind": "msg", "text": text})
    except Exception:
        pass


async def _lead_payload(request: Request) -> tuple[dict, bool]:
    """
    Данные заявки из запроса: JSON ИЛИ обычная HTML-форма (form-urlencoded/multipart).
    Агенты иногда делают <form method=POST action=...> без fetch — раньше такой POST
    падал на request.json() → data={} → 400 «нужен контакт», и ЛИД ТЕРЯЛСЯ (реальный
    кейс из прода). Возвращает (data, is_native_form) — для нативной формы отвечаем
    HTML-страницей «Спасибо», а не JSON.
    """
    ctype = (request.headers.get("content-type") or "").lower()
    if "json" in ctype:
        try:
            return dict(await request.json()), False
        except Exception:
            return {}, False
    if "form" in ctype:  # application/x-www-form-urlencoded или multipart/form-data
        try:
            form = await request.form()
            return {k: str(v) for k, v in form.items()}, True
        except Exception:
            return {}, True
    try:  # content-type не выставлен — пробуем JSON, затем форму
        return dict(await request.json()), False
    except Exception:
        try:
            form = await request.form()
            return {k: str(v) for k, v in form.items()}, True
        except Exception:
            return {}, False


_LEAD_THANKS_HTML = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Заявка отправлена</title>
<style>body{margin:0;min-height:100svh;display:grid;place-items:center;font-family:Inter,system-ui,Arial,sans-serif;background:#0d1220;color:#ecf2ff}.card{max-width:440px;padding:40px 36px;text-align:center;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.12);border-radius:22px}.ok{font-size:44px}h1{font-size:22px;margin:14px 0 8px}p{color:#a9b5d1;line-height:1.6;margin:0 0 22px}a{display:inline-block;padding:12px 22px;border-radius:12px;background:linear-gradient(135deg,#8dd3ff,#6f8cff);color:#08111f;font-weight:700;text-decoration:none}</style>
</head><body><div class="card"><div class="ok">✅</div><h1>Заявка отправлена</h1>
<p>Спасибо! Мы получили вашу заявку и свяжемся с вами в ближайшее время.</p>
<a href="javascript:history.back()">← Вернуться на сайт</a></div></body></html>"""

# Нативная HTML-форма без контакта: посетитель должен увидеть страницу с просьбой
# вернуться и заполнить поле, а не сырой JSON {"error": ...} (реальный UX публичного сайта).
_LEAD_NO_CONTACT_HTML = _LEAD_THANKS_HTML \
    .replace('<title>Заявка отправлена</title>', '<title>Не хватает контакта</title>') \
    .replace('<div class="ok">✅</div>', '<div class="ok">✍️</div>') \
    .replace('<h1>Заявка отправлена</h1>', '<h1>Не хватает контакта</h1>') \
    .replace('Спасибо! Мы получили вашу заявку и свяжемся с вами в ближайшее время.',
             'Укажите, пожалуйста, телефон или email — иначе мы не сможем с вами связаться.')


def _extract_lead_fields(data: dict) -> tuple[str, str, str]:
    """Имя/контакт/сообщение из полей формы с учётом всех вариантов имён полей агентов."""
    name = (data.get("name") or data.get("имя") or "").strip()
    contact = (data.get("contact") or data.get("phone") or data.get("tel")
               or data.get("telefon") or data.get("email") or data.get("телефон") or "").strip()
    msg = (data.get("message") or data.get("comment") or data.get("комментарий") or "").strip()
    # Служебные поля (utm_*, quiz-выбор) — в хвост сообщения, чтобы не терять контекст лида.
    extra = "; ".join(f"{k}={v}" for k, v in data.items()
                      if v and k not in ("name", "имя", "contact", "phone", "tel", "telefon",
                                         "email", "телефон", "message", "comment", "комментарий"))
    if extra:
        msg = (msg + " | " + extra) if msg else extra
    return name, contact, msg[:600]


@app.post("/api/lead/{tenant}/{slug}")
async def capture_lead(tenant: str, slug: str, request: Request):
    """Приём заявки с формы лендинга — реальный лид для тенанта (публично)."""
    if _rate_limited("lead", _client_ip(request), 20):
        return JSONResponse({"error": "слишком много заявок, попробуйте позже"}, status_code=429)
    saas_context.set_tenant(tenant)
    if sites_module.get(slug) is None:
        return JSONResponse({"error": "страница не найдена"}, status_code=404)
    data, native = await _lead_payload(request)
    name, contact, msg = _extract_lead_fields(data)
    if not contact:
        if native:
            return HTMLResponse(_LEAD_NO_CONTACT_HTML, status_code=400)
        return JSONResponse({"error": "нужен контакт"}, status_code=400)
    lead = leads_module.add(slug, name, contact, msg)
    _record_lead_metrics()
    await _notify_lead(dict(lead, slug=slug))
    return HTMLResponse(_LEAD_THANKS_HTML) if native else {"ok": True}


def _record_lead_metrics() -> None:
    """Снимок метрик при новом лиде — тренд «заявки/выручка» пополняется фактом
    (Measurement, Phase 3b). Не роняет приём лида, если что-то пошло не так."""
    try:
        from src.office import metrics as metrics_module
        metrics_module.collect()
    except Exception:
        pass


@app.post("/api/site-lead")
async def capture_site_lead(request: Request):
    """
    Приём заявки с многофайлового сайта. Тенант и slug берутся из Referer
    (страница хостится по /site/{tenant}/{slug}/...), поэтому форма может слать
    POST на стабильный /api/site-lead, не зная slug заранее.
    """
    import re as _re
    ref = request.headers.get("referer") or request.headers.get("origin") or ""
    m = _re.search(r"/site/([^/]+)/([^/?#]+)", ref)
    if not m:
        return JSONResponse({"error": "не удалось определить сайт"}, status_code=400)
    tenant, slug = m.group(1), m.group(2)
    saas_context.set_tenant(tenant)
    if sites_module.get(slug) is None:
        return JSONResponse({"error": "сайт не найден"}, status_code=404)
    data, native = await _lead_payload(request)
    name, contact, msg = _extract_lead_fields(data)
    if not contact:
        if native:
            return HTMLResponse(_LEAD_NO_CONTACT_HTML, status_code=400)
        return JSONResponse({"error": "нужен контакт (телефон или email)"}, status_code=400)
    lead = leads_module.add(slug, name, contact, msg)
    _record_lead_metrics()
    await _notify_lead(dict(lead, slug=slug))
    return HTMLResponse(_LEAD_THANKS_HTML) if native else {"ok": True}


@app.post("/tg/{tenant}/{secret}")
async def telegram_webhook(tenant: str, secret: str, request: Request):
    """Вебхук Telegram: апдейты бота клиента (публично — вызывает Telegram).

    Безопасность: secret в URL должен совпадать с конфигом тенанта. Движок один
    (bot_engine), поведение бота определяется конфигом этого тенанта.
    """
    saas_context.set_tenant(tenant)
    cfg = bot_config_module.get()
    if not cfg.get("enabled") or secret != cfg.get("webhook_secret"):
        return {"ok": True}  # тихо игнорируем чужие/выключенные
    try:
        update = await request.json()
    except Exception:
        return {"ok": True}
    try:
        await bot_engine_module.handle_update(update)
    except Exception:
        pass  # не отдаём Telegram ошибку, чтобы он не ретраил бесконечно
    return {"ok": True}


@app.get("/api/bot")
async def get_bot_config():
    """Текущий конфиг Telegram-бота тенанта (для UI/агентов)."""
    cfg = bot_config_module.get()
    cfg["has_token"] = bool(bot_config_module.resolve_token())
    cfg.pop("webhook_secret", None)  # секрет наружу не отдаём
    return cfg


@app.post("/api/bot")
async def set_bot_config(request: Request):
    """Обновить конфиг бота (услуги, приветствие, поля и т.д.)."""
    data = await request.json()
    return bot_config_module.update(data)


@app.get("/api/files")
async def get_files():
    """Список файлов кода, написанных агентами в рабочей папке проекта."""
    return {"files": workspace_module.list_files()}


@app.get("/api/storage/usage")
async def get_storage_usage():
    """Разбивка использования диска тенантом (вкладка «Хранилище») — сколько
    занимают файлы проектов (по папке), системные данные и Docker-ресурсы
    (постоянные приложения/MCP-серверы), не только сырой список файлов."""
    from src.office import storage_usage
    return storage_usage.summary()


@app.get("/api/plan")
async def get_plan():
    """Доска задач офиса: todo/doing/done + прогресс. Для вкладки «Задачи»."""
    tasks = plan_module.all_tasks()
    # имя исполнителя через роль (developer_1 → Разработчик) делаем на фронте
    return {
        "generated": plan_module.is_generated(),
        "tasks": tasks,
        "progress": plan_module.progress(),
    }


@app.get("/api/file")
async def get_file(path: str):
    """Содержимое одного файла из рабочей папки (для вкладки «Папки»)."""
    from fastapi.responses import PlainTextResponse
    content = workspace_module.read_file(path)
    return PlainTextResponse(content)


@app.get("/api/raw/{path:path}")
async def get_raw_file(path: str):
    """
    Сырой файл рабочей папки с корректным content-type и по path-адресу
    (а не query). Нужно для превью многофайлового сайта во вкладке «Папки»:
    при загрузке index.html через src относительные css/js/картинки резолвятся
    от /api/raw/<dir>/ и подтягиваются автоматически.
    """
    import mimetypes
    from fastapi.responses import Response
    data = workspace_module.read_bytes(path)
    if data is None:
        return Response(content=b"not found", status_code=404)
    ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
    return Response(content=data, media_type=ctype)


@app.post("/api/run")
async def run_file(request: Request):
    """Запустить файл из рабочей папки (.py / .js / .sh) и вернуть вывод.

    ⚠️ Исполнение процесса не изолировано от файловой системы хоста
    (docs/audit-dd-2026-07.md §17) — выключено по умолчанию оператором.
    """
    if not workspace_module.code_execution_allowed():
        return JSONResponse(
            {"ok": False, "error": "code_execution_disabled",
             "output": workspace_module._DISABLED_MSG}, status_code=403)
    if _rate_limited("run", saas_context.get_tenant(), 15):
        return JSONResponse({"ok": False, "output": "Слишком много запусков подряд — подождите минуту."},
                            status_code=429)
    data = await request.json()
    path = (data.get("path") or "").strip()
    stdin = data.get("stdin") or ""
    if not path:
        return JSONResponse({"ok": False, "output": "Нужен path файла."})
    output = workspace_module.execute_code(path, stdin)
    ok = not output.startswith("❌")
    return JSONResponse({"ok": ok, "output": output})


@app.post("/api/terminal")
async def terminal(request: Request):
    """Терминал рабочей папки: выполняет команду в workspace тенанта (cwd — подпапка).

    ⚠️ shell=True не ограничивает саму команду (path traversal через `cat ../../
    <tenant>/...`, чтение .env и т.п.) — docs/audit-dd-2026-07.md §17. Выключено
    по умолчанию оператором до появления реальной песочницы исполнения.
    """
    if not workspace_module.code_execution_allowed():
        return JSONResponse(
            {"ok": False, "error": "code_execution_disabled",
             "output": workspace_module._DISABLED_MSG}, status_code=403)
    if _rate_limited("terminal", saas_context.get_tenant(), 15):
        return JSONResponse({"ok": False, "output": "Слишком много команд подряд — подождите минуту."},
                            status_code=429)
    data = await request.json()
    cmd = (data.get("cmd") or "").strip()
    cwd = (data.get("cwd") or "").strip()
    if not cmd:
        return JSONResponse({"ok": False, "output": "Введите команду."})
    output = workspace_module.run_command(cmd, cwd)
    ok = not output.startswith("❌")
    return JSONResponse({"ok": ok, "output": output})


@app.get("/api/digest")
async def get_digest():
    """Morning Digest — что офис сделал с последнего визита. Обновляет метку визита."""
    from src.office import digest as digest_module
    return digest_module.get_and_mark_seen()


@app.get("/api/understanding")
async def get_understanding():
    """Индикатор «Понимание компании»: score 0–100, что есть и чего не хватает."""
    from src.office import understanding as understanding_module
    return understanding_module.payload()


@app.get("/api/digital-infrastructure")
async def get_digital_infrastructure():
    """Уровень 2 Instant Learning: единый список источников данных о компании —
    подключённые интеграции платформы + сигналы, увиденные на сайте клиента
    (CRM/аналитика/соцсети), к которым платформа пока не подключена напрямую."""
    from src.office import digital_infrastructure
    return digital_infrastructure.payload()


@app.get("/api/costs")
async def get_costs():
    """Расход токенов и стоимость по агентам и суммарно (ROI-панель)."""
    payload = costs_module.payload()
    return {**payload, "agents": _with_worker_id(payload.get("agents", []))}


@app.get("/api/apinet/balance")
async def apinet_balance():
    """Реальный баланс/расход аккаунта apinet (точные цифры из их API).
    Работает только если заданы APINET_ACCESS_TOKEN/USER_ID."""
    from src.saas import apinet
    if not apinet.is_configured():
        return {"configured": False}
    return {"configured": True, **apinet.balance()}


@app.get("/api/sites")
async def get_sites():
    """Список опубликованных лендингов (с числом заявок)."""
    tid = saas_context.get_tenant()
    domains_by_slug: dict[str, list[str]] = {}
    for d in domains_module.for_tenant(tid):
        domains_by_slug.setdefault(d["slug"], []).append(d["domain"])
    out = []
    for s in sites_module.all_sites():
        out.append({**s, "leads": len(leads_module.for_site(s["slug"])),
                    "url": f"/site/{tid}/{s['slug']}",
                    "domains": domains_by_slug.get(s["slug"], [])})
    return {"sites": out}


@app.post("/api/sites/{slug}/domain")
async def add_site_domain(slug: str, request: Request):
    """Привязать кастомный домен к опубликованному сайту (docs/product-capability-gaps.md
    п.5). Клиент сам направляет DNS домена (A/CNAME) на платформу — это вне нашего
    контроля; здесь только серверное сопоставление Host → тенант/сайт."""
    tid = saas_context.get_tenant()
    if sites_module.get(slug) is None:
        return JSONResponse({"error": "сайт с таким адресом не найден"}, status_code=404)
    body = await request.json()
    domain = (body.get("domain") or "").strip()
    result = domains_module.register(domain, tid, slug)
    if "error" in result:
        return JSONResponse(result, status_code=400)
    return {"domain": result, "instructions": (
        f"Направьте DNS домена {result['domain']} на этот сервер (A-запись на IP сервера "
        f"или CNAME, в зависимости от вашего DNS-провайдера) — платформа не регистрирует "
        f"домены и не управляет DNS сама.")}


@app.delete("/api/sites/{slug}/domain/{domain}")
async def remove_site_domain(slug: str, domain: str):
    tid = saas_context.get_tenant()
    ok = domains_module.unregister(domain, tid)
    return {"ok": ok}


@app.get("/api/leads")
async def get_leads():
    """Все собранные лиды (мини-CRM: статус + история)."""
    return {"leads": leads_module.all_leads(), "statuses": leads_module.STATUSES,
            "labels": leads_module.STATUS_LABELS}


@app.post("/api/leads/{lead_id}/status")
async def set_lead_status(lead_id: str, request: Request):
    """Сменить статус лида (мини-CRM). Body: {status, note?}.
    ⚠️ Путь ОБЯЗАН быть /api/leads/... (множественное число), не /api/lead/... —
    последний уже занят публичным приёмом заявок POST /api/lead/{tenant}/{slug}
    (без авторизации, для форм лендингов). Оба двухсегментные, FastAPI матчит по
    порядку регистрации — /api/lead/{lead_id}/status ловился ТЕМ роутом (tenant=
    lead_id, slug="status") и не долистывал до этого хендлера (нашли по 404 в реальном тесте)."""
    data = await request.json()
    status = (data.get("status") or "").strip()
    note = data.get("note") or ""
    lead = leads_module.set_status(lead_id, status, note)
    if not lead:
        return JSONResponse({"error": "лид не найден или статус некорректен"}, status_code=404)
    return {"ok": True, "lead": lead}


@app.post("/api/leads/{lead_id}/note")
async def add_lead_note(lead_id: str, request: Request):
    """Добавить заметку к лиду. Body: {text}."""
    data = await request.json()
    text = (data.get("text") or "").strip()
    if not text:
        return JSONResponse({"error": "text обязателен"}, status_code=400)
    lead = leads_module.add_note(lead_id, text, by="owner")
    if not lead:
        return JSONResponse({"error": "лид не найден"}, status_code=404)
    return {"ok": True, "lead": lead}


@app.get("/api/results")
async def get_results():
    """Реестр типов результата работы команды (лиды/сайты и в будущем другие) —
    метаданные вкладок «Результаты» (id/label/count), см. results.py."""
    return results_module.snapshot()


@app.get("/api/ui-prefs/{section}")
async def get_ui_prefs(section: str):
    """Персональные предпочтения владельца по видимости/порядку под-вкладок раздела."""
    return ui_prefs_module.get_section(section)


@app.post("/api/ui-prefs/{section}")
async def set_ui_prefs(section: str, request: Request):
    """Body: {order?: string[], hidden?: string[]}."""
    data = await request.json()
    return ui_prefs_module.set_section(section, data.get("order"), data.get("hidden"))


@app.get("/api/office/status")
async def office_status():
    """Статус офис-цикла (работает / на паузе)."""
    from src.office import control as control_module
    return control_module.status()


@app.get("/api/knowledge")
async def get_knowledge():
    """Трёхслойная память офиса: что он знает о клиенте и отделах."""
    from src.office import knowledge as knowledge_module
    facts = knowledge_module.all_facts()
    layers = {"global": 0, "user": 0, "department": 0}
    for f in facts:
        k = f.get("layer", "department")
        layers[k] = layers.get(k, 0) + 1
    return {"facts": facts, "count": len(facts), "layers": layers}


@app.get("/api/department-events")
async def get_department_events():
    """Доменные события офиса (Event Layer): сигналы отделов и их статус."""
    from src.office import events as events_module
    evs = events_module.recent(40)
    return {"events": evs, "pending": sum(1 for e in evs if not e.get("processed"))}


@app.post("/api/office/pause")
async def office_pause():
    """Поставить офис на паузу (агенты доделают текущие задачи, новые не начнут)."""
    from src.office import control as control_module, bus as bus_module
    control_module.pause("Пауза по запросу пользователя")
    await bus_module.publish({"type": "system", "text": "⏸ Офис поставлен на паузу пользователем"})
    return {"ok": True}


@app.post("/api/office/resume")
async def office_resume():
    """Возобновить работу офиса."""
    from src.office import control as control_module, bus as bus_module
    control_module.resume()
    await bus_module.publish({"type": "system", "text": "▶ Офис возобновил работу"})
    return {"ok": True}


@app.post("/api/brief/reset")
async def brief_reset():
    """Полный сброс ТЕКУЩЕГО тенанта: новый клиент с чистого листа."""
    # СНАЧАЛА гасим живой офис-цикл: иначе его задача переживала wipe и продолжала
    # работать со старым состоянием в RAM — реанимировала план/стратегию и жгла токены.
    office_loop.forget_tenant(saas_context.get_tenant())
    models_module.reset()      # сбрасываем индивидуальные модели, глобальную оставляем
    saas_context.wipe()        # удаляет все файлы данных тенанта (бриф, состояние, код, стратегия, ТЗ…)
    return {"ok": True}


@app.get("/api/memory")
async def get_memory():
    """Все сохранённые ответы пользователя."""
    return {"entries": memory.all_entries()}


@app.get("/api/models")
async def get_models():
    """Текущая глобальная модель, индивидуальные назначения и подсказки."""
    return {
        "default": models_module.get_default(),
        "per_agent": models_module.assignments(),
        "per_role": models_module.role_assignments(),
        "roles": models_module.role_catalog(),
        "presets": models_module.PRESETS,
    }


@app.get("/api/llm-settings")
async def get_llm_settings():
    """Персональные настройки доступа к LLM (свой ключ клиента)."""
    return llm_settings_module.public()


@app.post("/api/llm-settings")
async def set_llm_settings(request: Request):
    """Сохранить свой API-ключ и base_url. Ключ шифруется на диске."""
    data = await request.json()
    llm_settings_module.set_settings(
        base_url=(data.get("base_url") or "").strip(),
        api_key=(data.get("api_key") or "").strip(),
    )
    return {"ok": True, **llm_settings_module.public()}


@app.post("/api/llm-settings/clear")
async def clear_llm_key():
    """Удалить свой ключ — вернуться на общий ключ оператора."""
    llm_settings_module.clear_key()
    return {"ok": True, **llm_settings_module.public()}


@app.get("/api/model")
async def get_model():
    return {"model": models_module.get_default()}


@app.post("/api/model")
async def set_model(request: Request):
    """Сменить глобальную модель офиса."""
    data = await request.json()
    model = (data.get("model") or "").strip()
    if not model:
        return JSONResponse({"error": "model обязателен"}, status_code=400)
    models_module.set_default(model)
    return {"ok": True, "model": model}


@app.get("/api/org-graph")
async def get_org_graph():
    """Узлы и рёбра для вкладки «Сценарии» (см. docs/scenario-graph-tab-spec.md)."""
    from src.office import org_graph
    return org_graph.build()


@app.post("/api/agent/{agent_id}/pause")
async def pause_agent(agent_id: str):
    """Ставит ОДНОГО сотрудника на паузу — в отличие от /api/office/pause,
    не трогает остальную компанию. Лидер отдела перестаёт предлагать ему задачи."""
    ok = registry.pause(agent_id)
    if not ok:
        return JSONResponse({"error": "агент не найден"}, status_code=404)
    return {"ok": True, "agent_id": agent_id, "paused": True}


@app.post("/api/agent/{agent_id}/resume")
async def resume_agent(agent_id: str):
    ok = registry.resume(agent_id)
    if not ok:
        return JSONResponse({"error": "агент не найден"}, status_code=404)
    office_loop.wake_tenant()
    return {"ok": True, "agent_id": agent_id, "paused": False}


@app.post("/api/task/{task_id}/reassign")
async def reassign_task(task_id: str, request: Request):
    """Переназначить задачу другому исполнителю (вкладка «Сценарии»). Body: {agent_id}."""
    from src.office import plan as plan_mod
    data = await request.json()
    agent_id = (data.get("agent_id") or "").strip()
    if not agent_id:
        return JSONResponse({"error": "agent_id обязателен"}, status_code=400)
    target = registry.get(agent_id)
    if not target:
        return JSONResponse({"error": "агент не найден"}, status_code=404)
    task = plan_mod.get_task(task_id)
    if not task:
        return JSONResponse({"error": "задача не найдена"}, status_code=404)
    if task.get("role") != target.role:
        return JSONResponse(
            {"error": f"агент {agent_id} — роль {target.role}, задаче нужна роль {task.get('role')}"},
            status_code=409)
    if not plan_mod.reassign(task_id, agent_id):
        return JSONResponse({"error": "задачу нельзя переназначить в её текущем статусе"}, status_code=409)
    office_loop.wake_tenant()
    return {"ok": True, "task_id": task_id, "agent_id": agent_id}


@app.post("/api/agent/{agent_id}/model")
async def set_agent_model(agent_id: str, request: Request):
    """Назначить агенту индивидуальную модель (пустая — вернуть к общей)."""
    data = await request.json()
    model = (data.get("model") or "").strip()
    models_module.set_for_agent(agent_id, model)
    return {"ok": True, "agent_id": agent_id, "worker_id": agent_id,
            "model": models_module.for_agent(agent_id)}


@app.post("/api/role/{role}/model")
async def set_role_model(role: str, request: Request):
    """Назначить модель для роли (пустая — вернуть к глобальной). По умолчанию не задано."""
    data = await request.json()
    model = (data.get("model") or "").strip()
    models_module.set_for_role(role, model)
    return {"ok": True, "role": role, "model": models_module.for_role(role)}


@app.get("/api/questions")
async def get_questions():
    """Список всех ожидающих ответа вопросов от агентов."""
    from src.office import questions as q_module
    return {"questions": q_module.list_pending()}


@app.post("/api/answer")
async def answer_question(request: Request):
    data = await request.json()
    qid = data.get("question_id", "")
    ans = data.get("answer", "").strip()
    from src.office import questions as q_module
    ok = q_module.answer(qid, ans)
    if ok:
        await bus.publish({"type": "question_answered", "question_id": qid})
    return {"ok": ok}


@app.get("/api/threads")
async def get_threads():
    """Сводка по личным чатам с агентами (для боковой панели вкладки «Чаты»)."""
    return {"threads": threads_module.summaries()}


@app.get("/api/thread/{agent_id}")
async def get_thread(agent_id: str):
    """Полная переписка пользователя с конкретным агентом."""
    return {"agent_id": agent_id, "worker_id": agent_id,
            "messages": threads_module.recent(agent_id)}


@app.post("/api/ask")
async def ask_agent(request: Request):
    """Сообщение пользователя агенту в личном чате.

    Если у агента есть открытый вопрос — сообщение трактуется как ОТВЕТ на него
    (разблокирует ожидающую задачу). Иначе — это обычная беседа с агентом.
    """
    data = await request.json()
    # worker_id — предпочтительное имя (BOS §12 п.4); agent_id принимается как
    # deprecated-алиас на переходный период, чтобы старые клиенты не сломались.
    agent_id = data.get("worker_id") or data.get("agent_id", "")
    message = (data.get("message") or "").strip()

    if not agent_id or not message:
        return JSONResponse({"error": "worker_id и message обязательны"}, status_code=400)

    if registry.get(agent_id) is None:
        return JSONResponse({"error": "агент не найден"}, status_code=404)

    # Сообщение пользователя всегда попадает в ленту чата
    threads_module.post(agent_id, "user", message)

    # 1) Есть ожидающий вопрос от этого агента → это ответ на него
    qid = questions_module.pending_for(agent_id)
    if qid:
        questions_module.answer(qid, message)
        threads_module.mark_answered(qid)
        await bus.publish({"type": "question_answered", "question_id": qid, "agent_id": agent_id})
        await bus.publish({"type": "agent_message", "agent_id": agent_id, "from": "user",
                           "kind": "msg", "text": message})
        return {"agent_id": agent_id, "worker_id": agent_id, "answered": True}

    # 2) Иначе — обычный диалог с агентом. Сообщение пользователя агенту тоже считаем
    # директивой (например «запусти бота») — иначе автономный цикл его не увидит.
    role = registry.get(agent_id).role
    memory.remember(f"Указание пользователя ({role})", message)
    # Intent Layer (BOS §1): ЕДИНЫЙ вход намерений владельца — личный чат тоже
    # фиксируется в журнале, а не только общий канал (/api/chat).
    from src.office import intent as intent_module
    _it = intent_module.capture(message, source="owner")
    if _it:
        intent_module.set_interpretation(_it["id"], scope="personal_chat",
                                         directive=f"диалог с {agent_id} → память офиса")
    await bus.publish({"type": "agent_message", "agent_id": agent_id, "from": "user",
                       "kind": "msg", "text": message})
    # ⚠️ Реальный найденный баг (живой pre-release аудит): DEMO_MODE обещает
    # "демо без расхода токенов" (CLAUDE.md §2), но личный чат с агентом ДО этой
    # правки безусловно вызывал chat.ask() → настоящий LLM-запрос → реальный
    # расход, даже когда demo.run() (весь остальной офис-цикл) работает по
    # сценарию без единого обращения к сети. Посетитель демо мог случайно
    # потратить реальный баланс оператора, просто написав агенту.
    if DEMO_MODE:
        reply = ("Сейчас я в демо-режиме и работаю по сценарию, а не отвечаю на "
                 "произвольные вопросы — зарегистрируйтесь, чтобы говорить с реальным офисом.")
        threads_module.post(agent_id, "agent", reply)
        await bus.publish({"type": "agent_message", "agent_id": agent_id, "from": "agent",
                           "kind": "msg", "text": reply})
        return {"agent_id": agent_id, "worker_id": agent_id, "reply": reply}
    try:
        reply = await chat.ask(agent_id, message, publish=bus.publish)
        threads_module.post(agent_id, "agent", reply)
        await bus.publish({"type": "agent_message", "agent_id": agent_id, "from": "agent",
                           "kind": "msg", "text": reply})
        return {"agent_id": agent_id, "worker_id": agent_id, "reply": reply}
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=500)


@app.get("/api/chat")
async def get_chat():
    """Последние сообщения общего канала офиса."""
    return {"messages": office_channel.recent(100)}


_STEER_ROLES = {"developer", "designer", "integrator", "marketer", "salesman"}


async def _post_ceo(text: str) -> None:
    """CEO пишет в общий чат (и в SSE)."""
    cmsg = office_channel.post("orchestrator_1", "orchestrator", text)
    await bus.publish({"type": "office_chat", "from": "orchestrator_1", "role": "orchestrator",
                       "text": text, "id": cmsg["id"]})


async def _intake_from_chat(text: str) -> None:
    """Discovery ПЕРЕД запуском офиса: сначала уточняем задачу, потом строим бриф и стартуем.
    Глупый офис строил бы вслепую; умный — задаёт вопросы и понимает бизнес клиента."""
    if not intake_module.active():
        # немедленно сигнализируем — пользователь видит реакцию, пока LLM думает
        await bus.publish({"type": "thinking", "agent_id": "orchestrator_1",
                           "text": "Уточняю задачу перед стартом…"})
        await _post_ceo("Читаю вашу идею, сейчас сформулирую уточняющие вопросы... ⏳")
        try:
            qs = await asyncio.wait_for(
                onboarding.make_questions(text, publish=bus.publish),
                timeout=20.0,
            )
        except Exception:
            qs = ["Какой результат вы считаете успехом?",
                  "Кто ваша целевая аудитория и в какой нише?",
                  "Что уже есть — продукт, бюджет, наработки, команда?"]
        intake_module.start(text, qs)
        reply = ("Класс, что хотите это запустить 🚀 Чтобы сделать по делу, а не строить вслепую, "
                 "уточню несколько вещей:\n\n" + "\n".join(f"• {q}" for q in qs) +
                 "\n\nОтветьте одним сообщением — и команда сразу приступит: исследование рынка → "
                 "стратегия → план. Это не «лендинг за 5 минут», а настоящая работа.")
        await _post_ceo(reply)
        return

    # это ответы на вопросы → собираем бриф и запускаем офис
    st = intake_module.add_answer(text)
    await bus.publish({"type": "thinking", "agent_id": "orchestrator_1",
                       "text": "Формирую бриф по вашим ответам…"})
    qa = [{"q": "; ".join(st.get("questions", [])), "a": "\n".join(st.get("answers", []))}]
    try:
        brief_data = await asyncio.wait_for(
            onboarding.build_brief(st.get("idea", ""), qa, publish=bus.publish),
            timeout=25.0,
        )
    except Exception:
        joined = (st.get("idea", "") + " — " + " ".join(st.get("answers", []))).strip()
        brief_data = {"summary": joined[:600], "goal": st.get("idea", "")[:300], "niche": ""}
    brief.set_brief(brief_data)
    memory.remember("Бриф клиента (приоритет)", brief_data.get("summary", ""))
    intake_module.clear()
    reply = (f"Принял ✅ Вот как я понял задачу:\n\n{brief_data.get('summary', '')}\n\n"
             "Команда приступает: ресёрчер изучает рынок, стратег считает модель, дальше — "
             "стратегия и план. Это займёт время — делаем по-настоящему. Пишите сюда в любой "
             "момент, чтобы направлять или уточнять.")
    await _post_ceo(reply)


async def _steer_from_chat(text: str) -> None:
    """Сообщение предпринимателя из чата. Если офис ещё не запущен (нет брифа) — ведём
    discovery (уточняющие вопросы → бриф → старт). Если офис работает — CEO-триаж: понять
    и органично вписать в работу. В фоне, чтобы POST отвечал мгновенно.
    """
    # Intent: единый вход намерений владельца (BOS §1) — каждое сообщение фиксируется
    # в журнале ДО интерпретации, с результатом триажа после.
    from src.office import intent as intent_module
    _intent = intent_module.capture(text, source="owner" if brief.is_ready() else "onboarding")

    # ── DISCOVERY: офис ещё не запущен — сначала уточняем, потом строим бриф ──
    if not brief.is_ready():
        try:
            await _intake_from_chat(text)
            if _intent:
                intent_module.set_interpretation(_intent["id"], scope="discovery")
        except Exception:
            memory.remember("Указание пользователя офису", text)  # не теряем сообщение
        return

    try:
        b = brief.get()
        goal = b.get("goal", "") or brief.summary()
        niche = b.get("niche", "")
        audience = b.get("audience", "")
        strategy = office_bootstrap.strategy_text()
        ms = milestones.all_stages()
        try:
            open_d = org.open_departments()
            depts_text = ", ".join(open_d) if open_d else "(нет открытых отделов)"
        except Exception:
            depts_text = ""
        board = plan_module.board_summary() if plan_module.is_generated() else ""
        res = await orchestrator.interpret_directive(
            goal, strategy, ms, depts_text, board, text, publish=bus.publish,
            niche=niche, audience=audience)
    except Exception:
        memory.remember("Указание пользователя офису", text)  # фолбэк — прежнее поведение
        return

    scope = (res.get("scope") or "steer").strip()
    reply = (res.get("reply") or "").strip()
    directive = (res.get("directive") or "").strip()
    ops = res.get("milestone_ops") or []
    new_tasks = res.get("new_tasks") or []
    changes: list[str] = []
    if _intent:
        intent_module.set_interpretation(_intent["id"], scope=scope, directive=directive,
                                         tasks_added=len(new_tasks))

    rejected_reason = ""
    if scope == "steer":
        # приоритетная директива — её чтят CEO и лидеры в своих решениях
        memory.remember("Указание предпринимателя (приоритет)", directive or text)

        # Решение как ТРАНЗАКЦИЯ (BOS §14 п.3, Phase 5): директива → PlanDiff →
        # Sandbox-проверки (бюджет/конфликт артефактов/вето Конституции) → apply|reject.
        # Больше НЕ мутируем план/вехи напрямую — только через прошедший проверки diff.
        from src.office import decision_engine
        plan_diff = {
            "add_tasks": new_tasks if isinstance(new_tasks, list) else [],
            "milestone_ops": ops if isinstance(ops, list) else [],
        }
        outcome = decision_engine.decide(plan_diff, made_by="orchestrator_1",
                                         thought=directive or text[:120])
        changes = outcome["changes"]
        if outcome["applied"]:
            office_loop.wake_tenant()  # офис мог быть в мониторинге — пусть переоценит
        elif outcome["reason"] and not decision_engine.is_empty(plan_diff):
            rejected_reason = outcome["reason"]

    # ответ CEO в общий чат (предприниматель видит, что его услышали)
    if reply:
        cmsg = office_channel.post("orchestrator_1", "orchestrator", reply)
        await bus.publish({"type": "office_chat", "from": "orchestrator_1", "role": "orchestrator",
                           "text": reply, "id": cmsg["id"]})
    if changes:
        await bus.publish({"type": "system", "text": "📌 План обновлён: " + "; ".join(changes[:6])})
    if rejected_reason:
        # Автономность — торговля, не молчаливый саботаж (BOS §2): показываем цену отказа.
        await bus.publish({"type": "system",
                           "text": f"⚖️ Решение по вашему запросу отклонено проверками: {rejected_reason}. "
                                   f"Смотрите «Решения» — там причина. Уточните или снимите ограничение."})


@app.get("/api/world")
async def get_world():
    """World Model: единый срез мира компании (Business State + Objectives + DNA)."""
    from src.office import world as world_module
    return world_module.snapshot()


@app.get("/api/metrics")
async def get_metrics():
    """Measurement (Phase 3): текущие показания метрик (факт|оценка) + история."""
    from src.office import metrics as metrics_module
    cur = metrics_module.current()
    return {"current": cur,
            "series": {r["metric_id"]: metrics_module.series(r["metric_id"]) for r in cur}}


@app.get("/api/gap")
async def get_gap():
    """Gap Analysis (Phase 4): разрывы между желаемым (Objective) и метрикой."""
    from src.office import gap as gap_module
    return {"gaps": gap_module.compute()}


@app.get("/api/dashboard")
async def get_dashboard():
    """Бизнес-дашборд (вкладка "Бизнес"): системные карточки (пересчитываются
    каждый раз из живых источников) + кастомные графики, добавленные по запросу
    клиента, в сохранённом порядке (перестановка — POST /api/dashboard/reorder)."""
    from src.office import dashboard as dashboard_module
    widgets = dashboard_module.all_widgets()
    for w in widgets:
        if w.get("kind") == "chart":
            w["series"] = dashboard_module.resolve_series(w)
    return {"widgets": widgets}


@app.post("/api/dashboard/request")
async def post_dashboard_request(request: Request):
    """Ручная кастомизация дашборда словами ("построй график выручки по месяцам
    за 12 месяцев"). CEO выбирает метрику из реально измеримых или честно
    отказывает — отказ с suggest_integration заводит инициативу (та же логика,
    что "не выдумываем KPI без данных", см. dashboard.py)."""
    from src.agents import orchestrator
    from src.office import initiatives as initiatives_module, dashboard as dashboard_module
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Опиши, что добавить на дашборд")
    result = await orchestrator.interpret_dashboard_request(text)
    if not result.get("ok"):
        iid = ""
        if result.get("suggest_integration"):
            # tasks (BOS §4 гибкость сервиса): не просто текст-заглушка, а
            # готовый план — скрипт + повторяющийся процесс + запись метрики
            # (см. dashboard_widget.md) — принятие инициативы сразу заводит
            # проект с этими задачами (существующий accept_initiative).
            iid = initiatives_module.add(
                result["suggest_integration"], result.get("reason", ""),
                "На дашборде появится реальная метрика вместо отказа",
                tasks=result.get("tasks") or [], source="user", needs_research=False)
        return {"ok": False, "reason": result.get("reason", ""), "initiative_id": iid}
    widget = dashboard_module.add_custom({
        "metric_id": result["metric_id"], "chart_type": result["chart_type"],
        "group_by": result["group_by"], "range_days": result["range_days"],
        "title": result["title"],
    })
    widget["series"] = dashboard_module.resolve_series(widget)
    return {"ok": True, "widget": widget}


@app.post("/api/dashboard/layout")
async def post_dashboard_layout(request: Request):
    """Свободное перетаскивание/ресайз виджета "как иконки на рабочем столе" —
    позиция и размер, любые оба (не только вертикальный порядок списком)."""
    from src.office import dashboard as dashboard_module
    body = await request.json()
    wid = (body.get("id") or "").strip()
    if not wid:
        raise HTTPException(status_code=400, detail="Нужен id виджета")
    dashboard_module.set_layout(wid, body.get("x", 0), body.get("y", 0),
                                body.get("w", 240), body.get("h", 140))
    return {"ok": True}


@app.post("/api/dashboard/remove")
async def post_dashboard_remove(request: Request):
    from src.office import dashboard as dashboard_module
    body = await request.json()
    return {"ok": dashboard_module.remove_custom(body.get("id", ""))}


@app.get("/api/objectives")
async def get_objectives():
    """Objectives — измеримые цели компании (desired state)."""
    from src.office import objectives as objectives_module
    return {"objectives": objectives_module.all_objectives()}


@app.post("/api/objectives")
async def post_objective(request: Request):
    """Создать/обновить Objective. Body: {title, desired?, measured_by?, priority?}
    или {id, ...patch} для обновления."""
    from src.office import objectives as objectives_module
    data = await request.json()
    if data.get("id"):
        obj = objectives_module.update(data["id"], **data)
        return {"ok": bool(obj), "objective": obj}
    if not (data.get("title") or "").strip():
        return {"ok": False, "message": "Нужен title"}
    obj = objectives_module.add(
        data["title"], desired=data.get("desired", ""),
        measured_by=data.get("measured_by", ""),
        priority=int(data.get("priority", 50)), source="owner",
        project_id=data.get("project_id", ""))
    return {"ok": True, "objective": obj}


@app.get("/api/intents")
async def get_intents():
    """Журнал намерений владельца и их интерпретаций (Intent Layer)."""
    from src.office import intent as intent_module
    return {"intents": intent_module.recent(50)}


@app.get("/api/projects")
async def get_projects():
    """Проекты компании: активные (может быть несколько параллельно, см.
    project_limits) + очередь + история с «что оставил после себя»."""
    from src.office import projects as projects_module
    return {"projects": projects_module.all_projects(),
            "active": projects_module.active(),
            "active_count": projects_module.active_project_count(),
            "max_active": projects_module.get_limit()}


@app.post("/api/projects/limit")
async def set_project_limit(request: Request):
    """Сколько проектов офис ведёт ОДНОВРЕМЕННО — владелец настраивает сам
    (по умолчанию 3, см. projects.DEFAULT_MAX_ACTIVE)."""
    from src.office import projects as projects_module
    body = await request.json()
    n = int(body.get("max_active", projects_module.DEFAULT_MAX_ACTIVE))
    projects_module.set_limit(n)
    return {"ok": True, "max_active": projects_module.get_limit()}


@app.post("/api/project/{project_id}/pause")
async def post_project_pause(project_id: str):
    """Ставит проект на паузу — освобождает слот параллельности для очереди,
    не закрывая Work (см. src/office/projects.py:pause)."""
    from src.office import projects as projects_module
    proj = projects_module.pause(project_id)
    if not proj:
        raise HTTPException(status_code=400, detail="Проект не найден или не активен")
    return {"ok": True, "project": proj}


@app.post("/api/project/{project_id}/resume")
async def post_project_resume(project_id: str):
    from src.office import projects as projects_module
    proj = projects_module.resume(project_id)
    if not proj:
        raise HTTPException(status_code=400, detail="Проект не найден или не на паузе")
    return {"ok": True, "project": proj}


@app.post("/api/projects/reorder")
async def post_projects_reorder(request: Request):
    """Приоритет очереди проектов — владелец решает, кто из ожидающих
    активируется раньше при освобождении слота (см. projects.reorder_queue)."""
    from src.office import projects as projects_module
    body = await request.json()
    projects_module.reorder_queue(body.get("order") or [])
    return {"ok": True}


@app.get("/api/processes")
async def get_processes():
    """Повторяющиеся процессы (BOS §5: Process — recurring action, не только
    поток Instance вроде продаж) — «контент-завод», «ежедневная аналитика»."""
    from src.office import processes as processes_module
    return {"processes": processes_module.all_processes()}


@app.post("/api/processes")
async def create_process(request: Request):
    from src.office import processes as processes_module
    body = await request.json()
    title = (body.get("title") or "").strip()
    role = (body.get("role") or "").strip()
    instruction = (body.get("instruction") or "").strip()
    if not title or not role or not instruction:
        raise HTTPException(status_code=400, detail="Нужны title, role и instruction")
    proc = processes_module.create(title, role, instruction, body.get("cadence", "every_cycle"))
    office_loop.wake_tenant()
    return {"ok": True, "process": proc}


@app.post("/api/process/{process_id}/pause")
async def pause_process(process_id: str):
    from src.office import processes as processes_module
    proc = processes_module.set_status(process_id, "paused")
    if not proc:
        raise HTTPException(status_code=404, detail="Процесс не найден")
    return {"ok": True, "process": proc}


@app.post("/api/process/{process_id}/resume")
async def resume_process(process_id: str):
    from src.office import processes as processes_module
    proc = processes_module.set_status(process_id, "active")
    if not proc:
        raise HTTPException(status_code=404, detail="Процесс не найден")
    return {"ok": True, "process": proc}


@app.post("/api/process/{process_id}/delete")
async def delete_process(process_id: str):
    from src.office import processes as processes_module
    ok = processes_module.delete(process_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Процесс не найден")
    return {"ok": True}


@app.get("/api/project/{project_id}")
async def get_project_detail(project_id: str):
    """Карточка одного проекта: сам проект + его задачи, прогресс, СВОИ этапы
    (Stage теперь привязаны к Work — BOS §5/§14 п.6) и СВОИ артефакты (сайты +
    готовые материалы) — «Итоги» были общим котлом на всю компанию, теперь это
    выдача конкретного Work (карта сайта, рефакторинг сессии 2026-07-05)."""
    from src.office import projects as projects_module
    proj = projects_module.get(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Проект не найден")
    tasks = plan_module.for_project(project_id)
    tid = saas_context.get_tenant()
    proj_sites = [{**s, "url": f"/site/{tid}/{s['slug']}"} for s in sites_module.for_project(project_id)]
    return {
        "project": proj,
        "tasks": tasks,
        "progress": plan_module.progress(project_id),
        "milestones": milestones.progress_payload(project_id),
        "sites": proj_sites,
        "deliverables": state.deliverables_for_project(project_id),
    }


@app.get("/api/specification")
async def get_specification(project_id: str = ""):
    """Спецификация работы — контракт приёмки (Acceptance L1). per-project
    (см. specification.py): без project_id — контракт активного проекта по
    умолчанию, как раньше; с project_id — контракт конкретного параллельного Work."""
    from src.office import specification as spec_module
    return spec_module.get(project_id) or {"status": "none"}


@app.get("/api/specifications")
async def get_all_specifications():
    """Контракты приёмки ВСЕХ проектов тенанта разом — вкладка «Проект» может
    показать спецификацию каждого параллельного Work, не только активного."""
    from src.office import specification as spec_module
    return {"items": spec_module.all_specs()}


@app.post("/api/specification/confirm")
async def confirm_specification(request: Request):
    """Владелец подтверждает спецификацию. Body: {note?, project_id?}."""
    from src.office import specification as spec_module
    data = await request.json() if (await request.body()) else {}
    spec = spec_module.confirm(data.get("note", ""), data.get("project_id", ""))
    return {"ok": True, "specification": spec}


@app.post("/api/task/{task_id}/unblock")
async def unblock_task(task_id: str):
    """Вернуть заблокированную задачу в очередь (решение владельца/CEO)."""
    from src.office import plan as plan_mod
    from src.office import events as events_module
    if not plan_mod.unblock(task_id):
        return {"ok": False, "message": "Задача не найдена или не заблокирована"}
    # kind-контракт BOS §10: разблокировка задачи закрывает её blocker-событие,
    # иначе оно вечно висело в pending и в World Model.
    events_module.resolve_for_task(task_id)
    office_loop.wake_tenant()
    return {"ok": True}


@app.get("/api/philosophy")
async def get_philosophy(request: Request):

    return philosophy_module.load()


@app.post("/api/philosophy")
async def post_philosophy(request: Request):

    data = await request.json()
    philosophy_module.save(data)
    return {"ok": True}


@app.get("/api/constitution")
async def get_constitution(request: Request):

    return constitution_module.payload()


@app.post("/api/constitution")
async def post_constitution(request: Request):

    data = await request.json()
    constitution_module.save(data)
    return {"ok": True}


@app.get("/api/autonomy")
async def get_autonomy(request: Request):

    return autonomy_module.payload()


@app.post("/api/autonomy")
async def post_autonomy(request: Request):

    data = await request.json()
    level = data.get("level", "")
    if level not in autonomy_module.LEVELS:
        return JSONResponse({"error": f"Уровень должен быть одним из: {autonomy_module.LEVELS}"}, status_code=400)
    autonomy_module.set_level(level)
    return {"ok": True, "level": level}


@app.post("/api/autonomy/upgrade")
async def post_autonomy_upgrade(request: Request):
    """Повысить автономию на один уровень — приём предложения офиса одним нажатием (B3)."""
    new_level = autonomy_module.upgrade()
    return {"ok": True, "level": new_level}


@app.get("/api/trust")
async def get_trust(request: Request):

    return trust_module.payload()


@app.get("/api/decisions")
async def get_decisions(request: Request):

    return decisions_module.payload()


@app.get("/api/initiatives")
async def get_initiatives(request: Request):

    return initiatives_module.payload()


@app.post("/api/initiatives")
async def propose_initiative(request: Request):
    """Предприниматель сам предлагает инициативу (BOS §5: Intent не обязан идти
    только от AI-наблюдения) — минимальный ввод, глубокий анализ офис делает
    сам в фоне (не блокируем HTTP-ответ длинным LLM-вызовом с поиском)."""
    import asyncio
    from src.office import initiative_research
    from src.saas import context as ctx
    body = await request.json()
    title = (body.get("title") or "").strip()
    idea = (body.get("idea") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Нужно название инициативы")
    iid = initiatives_module.propose(title, idea)

    tid = ctx.get_tenant()

    async def _bg():
        ctx.set_tenant(tid)
        await initiative_research.run(iid, title, idea, bus.publish)

    asyncio.create_task(_bg())
    return {"ok": True, "id": iid}


@app.post("/api/initiative/{iid}/accept")
async def accept_initiative(iid: str, request: Request):
    """Принятая инициатива — BOS §5: decision spawn_project. Каждая принятая
    инициатива — СВОЙ Work, а не дозапись в первый попавшийся активный проект
    (раньше вторая инициатива молча растворялась в задачах первой, если та
    была активна и непуста). Если слоты параллельных проектов заняты
    (projects.get_limit(), по умолчанию 3) — новый Work встаёт в очередь
    (status="queued") и активируется сам, когда что-то закроется."""
    from src.office import projects as projects_module
    initiative = next((i for i in initiatives_module.pending() if i["id"] == iid), None)

    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    override = bool(body.get("override"))

    # Явный гейт вердикта (docs/product-capability-gaps.md п.6): если анализ
    # сказал "не стоит", принять инициативу всё ещё можно (последнее слово у
    # владельца, BOS §2), но НЕ тихо мимо рекомендации — фронт должен явно
    # переспросить и прислать override=true вторым запросом.
    try:
        tasks = initiatives_module.accept(iid, override=override)
    except initiatives_module.InitiativeBlocked as e:
        return JSONResponse({
            "error": "initiative_blocked",
            "recommendation": e.recommendation,
            "research": e.research,
            "message": "Исследование рекомендует НЕ делать эту инициативу. "
                       "Чтобы принять вопреки рекомендации, повторите запрос с override=true.",
        }, status_code=409)

    proj = projects_module.create((initiative or {}).get("title", ""),
                                   (initiative or {}).get("rationale", ""))
    added = 0
    skipped_roles: list[str] = []
    # Двухпроходное построение графа: LLM отдаёт зависимости через СВОИ
    # временные id (t1, t2, ...) — реальные id задача получает только внутри
    # add_task(). Первый проход создаёт задачи и запоминает temp→real;
    # второй патчит deps через plan.set_deps (BOS §5: сценарий составлен ДО
    # начала работы, а не придумывается на ходу).
    temp_to_real: dict[str, str] = {}
    created: list[tuple[str, list[str]]] = []
    for t in tasks:
        role = (t.get("role") or "").strip()
        title = (t.get("title") or "").strip()
        # Реальный кейс (лог прогона 2026-07-09): CEO придумал роли "copywriter"/
        # "product analyst" для задач инициативы — такой роли в офисе нет, задача
        # молча осиротела бы (planning_engine.has_orphan_tasks её просто скипнет
        # позже), а отдел вместо неё изобрёл СОВСЕМ ДРУГОЙ план с нуля: клиент
        # принял одну инициативу, а по факту получил другую. Отсекаем на входе,
        # а не даём тихо разъехаться утверждённому плану и реально исполненному.
        if role and role not in roles_module.known_roles():
            skipped_roles.append(f"{title} (роль «{role}» не существует)")
            continue
        if role and title:
            real = plan_module.add_task(title, role, t.get("done_criterion", ""),
                                        requested_by="user", project_id=proj["id"])
            added += 1
            temp_id = (t.get("id") or "").strip()
            if temp_id:
                temp_to_real[temp_id] = real["id"]
            deps = [d for d in (t.get("deps") or []) if isinstance(d, str)]
            if deps:
                created.append((real["id"], deps))
    for real_id, temp_deps in created:
        resolved = [temp_to_real[d] for d in temp_deps if d in temp_to_real]
        if resolved:
            plan_module.set_deps(real_id, resolved)

    proj_after = projects_module.get(proj["id"]) if added else proj

    # Своя спецификация для ЭТОГО проекта сразу, не когда-нибудь позже в цикле
    # BOOTSTRAP (тот вызов покрывает только проект, созданный из брифа при
    # старте офиса) — без этого 100% задач второго параллельного Work сверялись
    # бы с чужим контрактом (реальный кейс, см. specification.py докстринг).
    from src.office import specification as spec_module
    spec_module.ensure(proj["id"])

    # Раньше принятие инициативы не оставляло НИ ОДНОГО следа в ленте событий —
    # новый проект с командой и бюджетом появлялся молча, владелец узнавал о нём
    # только случайно наткнувшись на вкладку «Проект». Теперь видно явно, что
    # именно произошло и почему тратится бюджет.
    await bus.publish({"type": "system",
                       "text": f"💡 Инициатива «{(initiative or {}).get('title', '')}» принята — "
                               f"открыт проект «{proj_after['title'] if proj_after else proj['title']}» "
                               f"({added} задач(и))"})
    if skipped_roles:
        await bus.publish({"type": "system",
                           "text": f"⚠️ {len(skipped_roles)} задач(и) инициативы пропущено "
                                   f"(несуществующая роль): {'; '.join(skipped_roles[:3])}"})

    office_loop.wake_tenant()
    return {
        "ok": True, "tasks_added": added, "tasks_skipped": len(skipped_roles),
        "project_id": proj_after["id"] if proj_after else "",
        "project_title": proj_after["title"] if proj_after else "",
    }


@app.post("/api/initiative/{iid}/reject")
async def reject_initiative(iid: str, request: Request):

    initiatives_module.reject(iid)
    return {"ok": True}


@app.get("/api/health")
async def get_health(request: Request):

    return health_module.payload()


@app.get("/api/capabilities")
async def get_capabilities(request: Request):
    """Реестр способностей компании (BOS §5): что умеем / чего не хватает под план /
    что можно подключить. НЕ режимы качества моделей — те на /api/quality-modes."""
    from src.office import capability
    return capability.registry()


@app.get("/api/quality-modes")
async def get_quality_modes(request: Request):
    """Режимы качества выбора модели (🟣 Экономия → ⚫ Эксперт)."""
    return quality_modes_module.payload()


@app.post("/api/quality-modes")
async def post_quality_modes(request: Request):
    data = await request.json()
    mode = data.get("mode")
    if mode:
        if mode not in quality_modes_module.QUALITY_MODES:
            return JSONResponse({"error": "Неизвестный режим"}, status_code=400)
        quality_modes_module.set_mode(mode)
    # Эксперт-режим: точечные оверрайды по типу задачи (capability-типу модели).
    for cap, model in (data.get("expert") or {}).items():
        quality_modes_module.set_expert(cap, model)
    return {"ok": True, **quality_modes_module.payload()}


@app.get("/api/skills")
async def get_skills(request: Request):

    return {"skills": skills_module.catalog_payload()}


@app.post("/api/skills/install")
async def install_skill(request: Request):
    """Установка скилла-файла (аналог npx skills add) — ЯВНОЕ действие пользователя.
    source: markdown | url | github. Скилл = инструкция агентам; ставь из доверенных источников."""
    data = await request.json()
    src = (data.get("source") or "markdown").strip()
    res = skills_module.install(
        src,
        content=data.get("content", ""),
        url=data.get("url", ""),
        ref=data.get("ref", ""),
    )
    if not res.get("ok"):
        return JSONResponse(res, status_code=400)
    return res


@app.delete("/api/skills/{skill_id}")
async def delete_skill(skill_id: str, request: Request):

    res = skills_module.remove(skill_id)
    if not res.get("ok"):
        return JSONResponse(res, status_code=400)
    return res


@app.get("/api/roles")
async def get_roles(request: Request):

    return roles_module.payload()


@app.get("/api/limits")
async def get_limits(request: Request):

    return costs_module.limit_payload()


@app.post("/api/limits")
async def post_limits(request: Request):

    data = await request.json()
    costs_module.set_limits(
        total_usd=data.get("total_usd", 0),
        daily_usd=data.get("daily_usd", 0),
    )
    return {"ok": True, **costs_module.limit_payload()}


@app.post("/api/chat")
async def post_chat(request: Request):
    """Предприниматель пишет в общий канал офиса. Сообщение сохраняется и сразу
    отдаётся, а CEO в фоне осмысливает его и вписывает в работу (ответ + правки этапов/доски)."""
    data = await request.json()
    text = (data.get("text") or "").strip()
    if not text:
        return JSONResponse({"error": "text обязателен"}, status_code=400)
    msg = office_channel.post("user", "user", text)
    await bus.publish({"type": "office_chat", "from": "user", "role": "user",
                       "text": text, "id": msg["id"]})
    # CEO-триаж в фоне (контекст тенанта копируется в задачу автоматически)
    asyncio.create_task(_steer_from_chat(text))
    return {"ok": True, "message": msg}
