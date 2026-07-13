"""
OAuth 2.0 для Figma (по образцу google_oauth.py — тот же приём: отдельный
модуль плоскости OAuth-механики, интеграция сама (figma.py) только берёт
готовый токен через get_valid_token()).

Переменные окружения (.env):
    FIGMA_CLIENT_ID      — OAuth app Client ID
    FIGMA_CLIENT_SECRET  — OAuth app Client Secret
    APP_BASE_URL         — базовый URL сервиса (для redirect_uri)

Как создать OAuth-приложение в Figma:
  1. figma.com/developers/apps → Create new app
  2. Callback URL: {APP_BASE_URL}/auth/figma/callback
  3. Скопируй Client ID и Client Secret в .env
"""

import os
import time
from urllib.parse import urlencode

import httpx

from src.office import connections

FIGMA_CLIENT_ID     = os.getenv("FIGMA_CLIENT_ID", "")
FIGMA_CLIENT_SECRET = os.getenv("FIGMA_CLIENT_SECRET", "")
APP_BASE_URL        = os.getenv("APP_BASE_URL", "http://localhost:8000").rstrip("/")

_AUTH_URL  = "https://www.figma.com/oauth"
_TOKEN_URL = "https://api.figma.com/v1/oauth/token"
_REFRESH_URL = "https://api.figma.com/v1/oauth/refresh"
_ME_URL    = "https://api.figma.com/v1/me"

CONN_NAME = "figma"
SCOPES = "file_read"


def is_configured() -> bool:
    return bool(FIGMA_CLIENT_ID and FIGMA_CLIENT_SECRET)


def redirect_uri() -> str:
    return f"{APP_BASE_URL}/auth/figma/callback"


def authorization_url(state: str) -> str:
    params = {
        "client_id":     FIGMA_CLIENT_ID,
        "redirect_uri":  redirect_uri(),
        "scope":         SCOPES,
        "state":         state,
        "response_type": "code",
    }
    return f"{_AUTH_URL}?{urlencode(params)}"


async def exchange_code(code: str) -> dict:
    """Обменивает authorization code на access_token + refresh_token."""
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(_TOKEN_URL, data={
            "client_id":     FIGMA_CLIENT_ID,
            "client_secret": FIGMA_CLIENT_SECRET,
            "redirect_uri":  redirect_uri(),
            "code":          code,
            "grant_type":    "authorization_code",
        })
    data = r.json()
    if "error" in data:
        raise RuntimeError(f"Figma OAuth: {data.get('message', data['error'])}")

    access  = data.get("access_token", "")
    refresh = data.get("refresh_token", "")
    exp     = int(time.time()) + int(data.get("expires_in", 3600))

    handle = ""
    if access:
        async with httpx.AsyncClient(timeout=10) as client:
            u = await client.get(_ME_URL, headers={"Authorization": f"Bearer {access}"})
            if u.status_code == 200:
                handle = u.json().get("email") or u.json().get("handle", "")

    return {"access_token": access, "refresh_token": refresh, "expires_at": str(exp), "handle": handle}


async def _do_refresh(refresh_token: str) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(_REFRESH_URL, data={
            "client_id":     FIGMA_CLIENT_ID,
            "client_secret": FIGMA_CLIENT_SECRET,
            "refresh_token": refresh_token,
        })
    data = r.json()
    if "error" in data:
        raise RuntimeError(f"Не удалось обновить токен Figma: {data.get('message', data['error'])}")
    return {
        "access_token": data.get("access_token", ""),
        "expires_at":   str(int(time.time()) + int(data.get("expires_in", 3600))),
    }


async def get_valid_token() -> str:
    conn = connections.get_exact_by_name(CONN_NAME)
    if not conn:
        raise RuntimeError("Figma не подключена. Нажми «Войти через Figma» в разделе Доступы.")

    fields      = conn.get("fields", {})
    access_tok  = fields.get("access_token", "")
    refresh_tok = fields.get("refresh_token", "")
    expires_at  = int(fields.get("expires_at") or 0)

    if not access_tok or time.time() > expires_at - 60:
        if not refresh_tok:
            raise RuntimeError("Токен Figma истёк. Переподключи Figma через раздел Доступы.")
        new = await _do_refresh(refresh_tok)
        updated = {**fields, **new}
        connections.save({"id": conn.get("id"), "name": CONN_NAME, "type": "oauth",
                           "fields": updated, "note": conn.get("note", "")})
        return new["access_token"]

    return access_tok


async def revoke() -> None:
    """У Figma нет публичного revoke-эндпоинта — просто удаляем подключение."""
    conn = connections.get_exact_by_name(CONN_NAME)
    if conn and conn.get("id"):
        connections.delete(conn["id"])


def connected() -> bool:
    return connections.get_exact_by_name(CONN_NAME) is not None
