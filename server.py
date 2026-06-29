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
from fastapi import FastAPI
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from src.office import bus, registry, loop as office_loop, demo, chat, brief, state, progress, connections
from src.office import memory
from src.office import threads as threads_module
from src.office import questions as questions_module
from src.office import sites as sites_module
from src.office import leads as leads_module
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

load_dotenv()

DEMO_MODE = os.getenv("DEMO_MODE", "0") == "1"


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

# ---- Rate limiting для /auth/* (без внешних зависимостей) ----
_auth_attempts: dict[str, list[float]] = {}
_MAX_AUTH_PER_MIN = 10


def _check_rate_limit(ip: str) -> bool:
    now = time.time()
    attempts = [t for t in _auth_attempts.get(ip, []) if now - t < 60]
    _auth_attempts[ip] = attempts
    if len(attempts) >= _MAX_AUTH_PER_MIN:
        return False
    _auth_attempts[ip].append(now)
    return True


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


# Пути /api/*, доступные без авторизации
_PUBLIC_API = {"/api/me"}

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Блокирует неавторизованные запросы к /api/* в обычном (не demo) режиме."""
    path = request.url.path
    if not DEMO_MODE and path.startswith("/api/") and path not in _PUBLIC_API \
            and not path.startswith("/api/lead/"):
        uid = saas_auth.read_session(request.cookies.get(saas_auth.SESSION_COOKIE, ""))
        if not uid:
            return JSONResponse({"error": "Требуется авторизация", "auth": False}, status_code=401)
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
async def events():
    """SSE endpoint — события только своего тенанта (из контекста запроса)."""
    tid = saas_context.get_tenant()
    q = bus.subscribe(tid)

    # Отправляем текущее состояние реестра при подключении
    async def stream():
        saas_context.set_tenant(tid)  # контекст для чтения снапшота внутри генератора
        try:
            # Снапшот текущих агентов
            for agent in registry.all_agents():
                snapshot = {
                    "type": "hired",
                    "agent_id": agent.agent_id,
                    "role": agent.role,
                    "desk": agent.desk,
                    "task": agent.task,
                    "status": agent.status,
                    "last_message": agent.last_message,
                }
                yield f"data: {json.dumps(snapshot, ensure_ascii=False)}\n\n"

            # Исторические события из прошлых сессий
            for evt in state.history()[-50:]:
                historical = dict(evt, historical=True)
                yield f"data: {json.dumps(historical, ensure_ascii=False)}\n\n"

            # Живой поток
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=30)
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
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
    return [
        {
            "agent_id": a.agent_id,
            "role": a.role,
            "desk": a.desk,
            "status": a.status,
            "last_message": a.last_message,
            "task": a.task,
        }
        for a in registry.all_agents()
    ]


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
    """Шаг 2: клиент ответил на вопросы → формируем бриф и запускаем офис."""
    data = await request.json()
    client_input = (data.get("input") or "").strip()
    qa_pairs = data.get("answers", [])
    if not client_input:
        return JSONResponse({"error": "пустой ввод"}, status_code=400)
    try:
        brief_data = await onboarding.build_brief(client_input, qa_pairs, publish=bus.publish)
        brief.set_brief(brief_data)  # сигналит офису о старте
        return {"ok": True, "brief": brief_data}
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=500)


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

    # Команда
    lines.append("\n## КОМАНДА")
    for a in registry.all_agents():
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


@app.get("/api/deliverables")
async def get_deliverables():
    """Готовые результаты работы агентов — пользователь может посмотреть и скопировать."""
    return {"deliverables": state.deliverables()}


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
        "role": rec.role,
        "status": rec.status,
        "task": rec.task,
        "current": rec.last_message or rec.task,
        "done": state.deliverables_for(agent_id),
        "activity": state.events_for(agent_id),
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


def _serve_site_file(site: dict, subpath: str):
    """Отдаёт файл из папки опубликованного сайта с корректным content-type."""
    import mimetypes
    import re as _re
    from fastapi.responses import Response
    root = (site.get("root") or "").strip("/")
    rel = (f"{root}/{subpath}").strip("/") if root else subpath
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


@app.post("/api/lead/{tenant}/{slug}")
async def capture_lead(tenant: str, slug: str, request: Request):
    """Приём заявки с формы лендинга — реальный лид для тенанта (публично)."""
    saas_context.set_tenant(tenant)
    if sites_module.get(slug) is None:
        return JSONResponse({"error": "страница не найдена"}, status_code=404)
    try:
        data = await request.json()
    except Exception:
        data = {}
    name = (data.get("name") or "").strip()
    contact = (data.get("contact") or "").strip()
    if not contact:
        return JSONResponse({"error": "нужен контакт"}, status_code=400)
    lead = leads_module.add(slug, name, contact, data.get("message", ""))
    await bus.publish({"type": "lead_captured", "slug": slug, "lead": lead,
                       "text": f"🎯 Новая заявка: {lead['name'] or 'без имени'} — {lead['contact']}"})
    return {"ok": True}


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
    try:
        data = await request.json()
    except Exception:
        data = {}
    name = (data.get("name") or data.get("имя") or "").strip()
    contact = (data.get("contact") or data.get("phone") or data.get("telefon")
               or data.get("email") or data.get("телефон") or "").strip()
    if not contact:
        return JSONResponse({"error": "нужен контакт (телефон или email)"}, status_code=400)
    msg = data.get("message") or data.get("comment") or data.get("комментарий") or ""
    lead = leads_module.add(slug, name, contact, msg)
    await bus.publish({"type": "lead_captured", "slug": slug, "lead": lead,
                       "text": f"🎯 Новая заявка: {lead['name'] or 'без имени'} — {lead['contact']}"})
    return {"ok": True}


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
    """Запустить файл из рабочей папки (.py / .js / .sh) и вернуть вывод."""
    data = await request.json()
    path = (data.get("path") or "").strip()
    stdin = data.get("stdin") or ""
    if not path:
        return JSONResponse({"ok": False, "output": "Нужен path файла."})
    output = workspace_module.execute_code(path, stdin)
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


@app.get("/api/costs")
async def get_costs():
    """Расход токенов и стоимость по агентам и суммарно (ROI-панель)."""
    return costs_module.payload()


@app.get("/api/sites")
async def get_sites():
    """Список опубликованных лендингов (с числом заявок)."""
    tid = saas_context.get_tenant()
    out = []
    for s in sites_module.all_sites():
        out.append({**s, "leads": len(leads_module.for_site(s["slug"])),
                    "url": f"/site/{tid}/{s['slug']}"})
    return {"sites": out}


@app.get("/api/leads")
async def get_leads():
    """Все собранные лиды."""
    return {"leads": leads_module.all_leads()}


@app.get("/api/office/status")
async def office_status():
    """Статус офис-цикла (работает / на паузе)."""
    from src.office import control as control_module
    return control_module.status()


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


@app.post("/api/agent/{agent_id}/model")
async def set_agent_model(agent_id: str, request: Request):
    """Назначить агенту индивидуальную модель (пустая — вернуть к общей)."""
    data = await request.json()
    model = (data.get("model") or "").strip()
    models_module.set_for_agent(agent_id, model)
    return {"ok": True, "agent_id": agent_id, "model": models_module.for_agent(agent_id)}


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
    return {"agent_id": agent_id, "messages": threads_module.recent(agent_id)}


@app.post("/api/ask")
async def ask_agent(request: Request):
    """Сообщение пользователя агенту в личном чате.

    Если у агента есть открытый вопрос — сообщение трактуется как ОТВЕТ на него
    (разблокирует ожидающую задачу). Иначе — это обычная беседа с агентом.
    """
    data = await request.json()
    agent_id = data.get("agent_id", "")
    message = (data.get("message") or "").strip()

    if not agent_id or not message:
        return JSONResponse({"error": "agent_id и message обязательны"}, status_code=400)

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
        return {"agent_id": agent_id, "answered": True}

    # 2) Иначе — обычный диалог с агентом. Сообщение пользователя агенту тоже считаем
    # директивой (например «запусти бота») — иначе автономный цикл его не увидит.
    role = registry.get(agent_id).role
    memory.remember(f"Указание пользователя ({role})", message)
    await bus.publish({"type": "agent_message", "agent_id": agent_id, "from": "user",
                       "kind": "msg", "text": message})
    try:
        reply = await chat.ask(agent_id, message, publish=bus.publish)
        threads_module.post(agent_id, "agent", reply)
        await bus.publish({"type": "agent_message", "agent_id": agent_id, "from": "agent",
                           "kind": "msg", "text": reply})
        return {"agent_id": agent_id, "reply": reply}
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
    # ── DISCOVERY: офис ещё не запущен — сначала уточняем, потом строим бриф ──
    if not brief.is_ready():
        try:
            await _intake_from_chat(text)
        except Exception:
            memory.remember("Указание пользователя офису", text)  # не теряем сообщение
        return

    try:
        goal = brief.get().get("goal", "") or brief.summary()
        strategy = office_loop._strategy_text()
        ms = milestones.all_stages()
        try:
            open_d = org.open_departments()
            depts_text = ", ".join(open_d) if open_d else "(нет открытых отделов)"
        except Exception:
            depts_text = ""
        board = plan_module.board_summary() if plan_module.is_generated() else ""
        res = await orchestrator.interpret_directive(
            goal, strategy, ms, depts_text, board, text, publish=bus.publish)
    except Exception:
        memory.remember("Указание пользователя офису", text)  # фолбэк — прежнее поведение
        return

    scope = (res.get("scope") or "steer").strip()
    reply = (res.get("reply") or "").strip()
    directive = (res.get("directive") or "").strip()
    ops = res.get("milestone_ops") or []
    new_tasks = res.get("new_tasks") or []
    changes: list[str] = []

    if scope == "steer":
        # приоритетная директива — её чтят CEO и лидеры в своих решениях
        memory.remember("Указание предпринимателя (приоритет)", directive or text)

        for op in ops if isinstance(ops, list) else []:
            try:
                kind = (op.get("op") or "").strip()
                if kind == "add" and op.get("title"):
                    milestones.insert_business_stage(op["title"], op.get("after"))
                    changes.append(f"новый этап «{op['title'][:40]}»")
                elif kind == "retitle" and op.get("id") and op.get("title") and milestones.retitle(op["id"], op["title"]):
                    changes.append(f"этап → «{op['title'][:40]}»")
                elif kind == "focus" and op.get("id"):
                    milestones.mark_active(op["id"]); changes.append("сдвинут фокус этапов")
                elif kind == "note" and op.get("id") and op.get("text"):
                    milestones.add_item(op["id"], op["text"], agent_id="orchestrator_1", role="orchestrator")
            except Exception:
                pass

        for t in new_tasks if isinstance(new_tasks, list) else []:
            role = (t.get("role") or "").strip()
            title = (t.get("title") or "").strip()
            if role in _STEER_ROLES and title:
                plan_module.add_task(title, role, t.get("done_criterion", ""), requested_by="orchestrator_1")
                changes.append(f"задача «{title[:36]}» → {role}")

        if ops or new_tasks:
            office_loop.wake_tenant()  # офис мог быть в мониторинге — пусть переоценит

    # ответ CEO в общий чат (предприниматель видит, что его услышали)
    if reply:
        cmsg = office_channel.post("orchestrator_1", "orchestrator", reply)
        await bus.publish({"type": "office_chat", "from": "orchestrator_1", "role": "orchestrator",
                           "text": reply, "id": cmsg["id"]})
    if changes:
        await bus.publish({"type": "system", "text": "📌 План обновлён: " + "; ".join(changes[:6])})


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
