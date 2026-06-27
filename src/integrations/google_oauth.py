"""
Общий модуль OAuth 2.0 для всех Google-сервисов (Sheets, Gmail, Calendar).

Один вход — один токен — все API. Токен хранится в connections под именем "google",
автоматически обновляется через refresh_token при истечении.

Переменные окружения (.env):
    GOOGLE_CLIENT_ID      — OAuth 2.0 Client ID (тип «Web application»)
    GOOGLE_CLIENT_SECRET  — OAuth 2.0 Client Secret
    APP_BASE_URL          — базовый URL сервиса (для redirect_uri)

Как создать OAuth-приложение в Google Cloud Console:
  1. console.cloud.google.com → APIs & Services → Credentials → Create OAuth 2.0 Client ID
  2. Тип: Web application; Authorized redirect URIs: {APP_BASE_URL}/auth/google/callback
  3. Скопируй Client ID и Client Secret в .env
  4. APIs & Services → Library → включи: Gmail API, Google Sheets API, Google Calendar API
"""

import os
import time
from urllib.parse import urlencode

import httpx

from src.office import connections

GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
APP_BASE_URL         = os.getenv("APP_BASE_URL", "http://localhost:8000").rstrip("/")

_AUTH_URL   = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL  = "https://oauth2.googleapis.com/token"
_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
_USERINFO   = "https://www.googleapis.com/oauth2/v3/userinfo"

CONN_NAME = "google"

# Один набор scope закрывает Sheets + Gmail + Calendar
SCOPES = " ".join([
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
])


def is_configured() -> bool:
    """True если в .env есть CLIENT_ID и CLIENT_SECRET."""
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)


def redirect_uri() -> str:
    return f"{APP_BASE_URL}/auth/google/callback"


def authorization_url(state: str) -> str:
    """Возвращает URL для редиректа пользователя на страницу согласия Google."""
    params = {
        "client_id":     GOOGLE_CLIENT_ID,
        "redirect_uri":  redirect_uri(),
        "response_type": "code",
        "scope":         SCOPES,
        "access_type":   "offline",  # нужен refresh_token
        "prompt":        "consent",  # принудительно показываем consent → получаем refresh_token
        "state":         state,
    }
    return f"{_AUTH_URL}?{urlencode(params)}"


async def exchange_code(code: str) -> dict:
    """Обменивает authorization code на access_token + refresh_token."""
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(_TOKEN_URL, data={
            "code":          code,
            "client_id":     GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri":  redirect_uri(),
            "grant_type":    "authorization_code",
        })
    data = r.json()
    if "error" in data:
        raise RuntimeError(f"Google OAuth: {data.get('error_description', data['error'])}")

    access  = data.get("access_token", "")
    refresh = data.get("refresh_token", "")
    exp     = int(time.time()) + int(data.get("expires_in", 3600))

    # Получаем email авторизованного пользователя
    email = ""
    if access:
        async with httpx.AsyncClient(timeout=10) as client:
            u = await client.get(_USERINFO, headers={"Authorization": f"Bearer {access}"})
            if u.status_code == 200:
                email = u.json().get("email", "")

    return {
        "access_token":  access,
        "refresh_token": refresh,
        "expires_at":    str(exp),
        "email":         email,
    }


async def _do_refresh(refresh_token: str) -> dict:
    """Низкоуровневое обновление токена."""
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(_TOKEN_URL, data={
            "refresh_token": refresh_token,
            "client_id":     GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "grant_type":    "refresh_token",
        })
    data = r.json()
    if "error" in data:
        raise RuntimeError(f"Не удалось обновить токен Google: {data.get('error_description', data['error'])}")
    return {
        "access_token": data.get("access_token", ""),
        "expires_at":   str(int(time.time()) + int(data.get("expires_in", 3600))),
    }


async def get_valid_token() -> str:
    """
    Возвращает валидный access_token для текущего тенанта.
    Автоматически обновляет токен если он истёк (через refresh_token).
    Сохраняет обновлённые данные обратно в connections.
    """
    conn = connections.get_by_name(CONN_NAME)
    if not conn:
        raise RuntimeError(
            "Google не подключён. Нажми «Подключить Google» в разделе Доступы."
        )

    fields      = conn.get("fields", {})
    access_tok  = fields.get("access_token", "")
    refresh_tok = fields.get("refresh_token", "")
    expires_at  = int(fields.get("expires_at") or 0)

    # Обновляем если токен истекает в течение следующих 60 секунд
    if not access_tok or time.time() > expires_at - 60:
        if not refresh_tok:
            raise RuntimeError(
                "Google токен истёк. Переподключи Google через раздел Доступы."
            )
        new = await _do_refresh(refresh_tok)
        updated = {**fields, **new}
        connections.save({
            "id":   conn.get("id"),
            "name": CONN_NAME,
            "type": "oauth",
            "fields": updated,
            "note": conn.get("note", ""),
        })
        return new["access_token"]

    return access_tok


async def revoke() -> None:
    """Отозвать токен и удалить подключение."""
    conn = connections.get_by_name(CONN_NAME)
    if conn:
        tok = (conn.get("fields") or {}).get("access_token", "")
        if tok:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(_REVOKE_URL, params={"token": tok})
        if conn.get("id"):
            connections.delete(conn["id"])


def connected() -> bool:
    """Есть ли активное Google-подключение для текущего тенанта."""
    return connections.get_by_name(CONN_NAME) is not None
