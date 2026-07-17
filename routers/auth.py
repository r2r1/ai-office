"""
Аутентификация: /api/me + все /auth/* (GitHub Device Flow, Google/Figma/Bitrix24
OAuth, dev-вход, logout). Перенесено из server.py (docs/technical-due-diligence-
2026-07-17.md §3.2.1, PR-5) механически — тот же код, то же поведение.
"""

import time

from fastapi import APIRouter
from fastapi.requests import Request
from fastapi.responses import JSONResponse, RedirectResponse

from src.office import connections
from src.saas import auth as saas_auth, store as saas_store
from src.saas import context as saas_context

from routers.shared import client_ip, current_user, rate_limited, set_session_cookie

router = APIRouter()

_MAX_AUTH_PER_MIN = 10


def _check_rate_limit(ip: str) -> bool:
    """True — запрос РАЗРЕШЁН."""
    return not rate_limited("auth", ip, _MAX_AUTH_PER_MIN)


@router.get("/api/me")
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


@router.get("/auth/github/login")
async def github_login():
    """Redirect-OAuth (опционально). Основной метод — Device Flow (/auth/github/device/start)."""
    if not saas_auth.github_configured():
        return JSONResponse({"error": "Задайте GITHUB_CLIENT_ID в .env"}, status_code=400)
    if saas_auth.GITHUB_CLIENT_SECRET:
        return RedirectResponse(saas_auth.github_login_url())
    return JSONResponse({"error": "Используйте Device Flow (/auth/github/device/start)"}, status_code=400)


@router.post("/auth/github/device/start")
async def github_device_start(request: Request):
    """Device Flow шаг 1: получить код для ввода на github.com/login/device."""
    if not _check_rate_limit(client_ip(request)):
        return JSONResponse({"error": "Слишком много попыток — подождите минуту"}, status_code=429)
    if not saas_auth.github_configured():
        return JSONResponse({"error": "Задайте GITHUB_CLIENT_ID в .env"}, status_code=400)
    try:
        data = await saas_auth.github_device_start()
        return data
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/auth/github/device/poll")
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
        set_session_cookie(resp, user["id"])
        return resp
    return JSONResponse({"pending": True, "error": result.get("error", "")})


@router.get("/auth/github/login-redirect")
async def github_login_redirect():
    """Redirect-OAuth (только если настроен CLIENT_SECRET)."""
    if not saas_auth.GITHUB_CLIENT_SECRET:
        return JSONResponse({"error": "Задайте GITHUB_CLIENT_SECRET для redirect-OAuth"}, status_code=400)
    return RedirectResponse(saas_auth.github_login_url())


@router.get("/auth/github/callback")
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
    set_session_cookie(resp, user["id"])
    return resp


@router.get("/auth/google/start")
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


@router.get("/auth/google/callback")
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
        set_session_cookie(resp, user["id"])
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


@router.post("/auth/google/disconnect")
async def google_oauth_disconnect(request: Request):
    """Отозвать Google-токен и удалить подключение."""
    uid = current_user(request)
    if not uid:
        return JSONResponse({"error": "не авторизован"}, status_code=401)
    from src.integrations import google_oauth
    await google_oauth.revoke()
    return JSONResponse({"ok": True})


@router.get("/auth/figma/login")
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


@router.get("/auth/figma/callback")
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


@router.post("/auth/figma/disconnect")
async def figma_oauth_disconnect(request: Request):
    uid = current_user(request)
    if not uid:
        return JSONResponse({"error": "не авторизован"}, status_code=401)
    from src.integrations import figma_oauth
    await figma_oauth.revoke()
    return JSONResponse({"ok": True})


@router.get("/auth/bitrix24/login")
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


@router.get("/auth/bitrix24/callback")
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


@router.post("/auth/bitrix24/disconnect")
async def bitrix24_oauth_disconnect(request: Request):
    uid = current_user(request)
    if not uid:
        return JSONResponse({"error": "не авторизован"}, status_code=401)
    from src.integrations import bitrix24_oauth
    bitrix24_oauth.revoke()
    return JSONResponse({"ok": True})


@router.post("/auth/dev-login")
async def dev_login(request: Request):
    """Локальный вход без GitHub (только если ALLOW_DEV_LOGIN=1)."""
    if not _check_rate_limit(client_ip(request)):
        return JSONResponse({"error": "Слишком много попыток — подождите минуту"}, status_code=429)
    if not saas_auth.ALLOW_DEV_LOGIN:
        return JSONResponse({"error": "dev-вход отключён"}, status_code=403)
    data = await request.json()
    email = (data.get("email") or "dev@local").strip()
    if not email or "@" not in email:
        return JSONResponse({"error": "Укажите корректный email"}, status_code=400)
    user = saas_store.get_or_create_dev_user(email)
    resp = JSONResponse({"ok": True, "user": saas_store.public_user(user)})
    set_session_cookie(resp, user["id"])
    return resp


@router.post("/auth/logout")
async def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(saas_auth.SESSION_COOKIE)
    return resp
