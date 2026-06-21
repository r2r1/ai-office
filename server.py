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
from src.office import models as models_module
from src.office import llm_settings as llm_settings_module
from src.agents import onboarding
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
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")

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
    return Path("static/index.html").read_text(encoding="utf-8")


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
        return {
            "authenticated": False,
            "github_available": saas_auth.github_configured(),
            "dev_login": saas_auth.ALLOW_DEV_LOGIN,
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
    """Отдаёт опубликованный лендинг конкретного тенанта (публично)."""
    saas_context.set_tenant(tenant)
    site = sites_module.get(slug)
    if site is None:
        return HTMLResponse("<h1>Страница не найдена</h1>", status_code=404)
    return HTMLResponse(site["html"])


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


@app.get("/api/files")
async def get_files():
    """Список файлов кода, написанных агентами в рабочей папке проекта."""
    return {"files": workspace_module.list_files()}


@app.get("/api/file")
async def get_file(path: str):
    """Содержимое одного файла из рабочей папки (для вкладки «Код»)."""
    from fastapi.responses import PlainTextResponse
    content = workspace_module.read_file(path)
    return PlainTextResponse(content)


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

    # 2) Иначе — обычный диалог с агентом
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


@app.post("/api/chat")
async def post_chat(request: Request):
    """Пользователь пишет сообщение всем агентам в общий канал офиса."""
    data = await request.json()
    text = (data.get("text") or "").strip()
    if not text:
        return JSONResponse({"error": "text обязателен"}, status_code=400)
    msg = office_channel.post("user", "user", text)
    await bus.publish({"type": "office_chat", "from": "user", "role": "user",
                       "text": text, "id": msg["id"]})
    return {"ok": True, "message": msg}
