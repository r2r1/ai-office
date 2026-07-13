"""
OAuth 2.0 для Bitrix24 (по образцу google_oauth.py) — приложение, а не входящий
вебхук (см. crm_bitrix24.py — тот способ проще для клиента, этот даёт доступ
ко ВСЕМ методам REST API портала, не только crm.*, и не нужно копировать URL
вебхука руками).

Особенность Bitrix24: сам портал multi-tenant (каждый клиент — свой поддомен
*.bitrix24.ru), поэтому запрос на согласие идёт НЕ на общий домен, а на
конкретный портал — его вводит владелец перед подключением (см. server.py
/auth/bitrix24/start?portal=...). Обмен кода на токен и обновление токена, в
отличие от authorize, всегда идут через общий oauth.bitrix.info — портал для
последующих REST-вызовов Bitrix24 сам возвращает в ответе токена (`domain`).

Переменные окружения (.env):
    BITRIX24_CLIENT_ID      — OAuth app Client ID (см. портал → Разработчикам → Другое → Локальное приложение)
    BITRIX24_CLIENT_SECRET  — OAuth app Client Secret
    APP_BASE_URL            — базовый URL сервиса (для redirect_uri)

Как создать локальное приложение в Bitrix24:
  1. На портале клиента: Приложения → Разработчикам → Другое → Локальное приложение
  2. Путь перенаправления (redirect): {APP_BASE_URL}/auth/bitrix24/callback
  3. Скопируй Client ID (ID приложения) и Client Secret (Ключ приложения) в .env
"""

import os
import time
from urllib.parse import urlencode

import httpx

from src.office import connections

BITRIX24_CLIENT_ID     = os.getenv("BITRIX24_CLIENT_ID", "")
BITRIX24_CLIENT_SECRET = os.getenv("BITRIX24_CLIENT_SECRET", "")
APP_BASE_URL           = os.getenv("APP_BASE_URL", "http://localhost:8000").rstrip("/")

_TOKEN_URL = "https://oauth.bitrix.info/oauth/token/"

CONN_NAME = "bitrix24"


def is_configured() -> bool:
    return bool(BITRIX24_CLIENT_ID and BITRIX24_CLIENT_SECRET)


def redirect_uri() -> str:
    return f"{APP_BASE_URL}/auth/bitrix24/callback"


def authorization_url(portal: str, state: str) -> str:
    """`portal` — домен клиента (например my-company.bitrix24.ru), вводит владелец
    перед подключением (см. server.py) — Bitrix24, в отличие от Google/Figma,
    не имеет единой страницы согласия."""
    domain = (portal or "").strip().lower()
    domain = domain.replace("https://", "").replace("http://", "").strip("/")
    if not domain:
        raise RuntimeError("Нужен домен портала Bitrix24 (например my-company.bitrix24.ru).")
    params = {
        "client_id":     BITRIX24_CLIENT_ID,
        "redirect_uri":  redirect_uri(),
        "response_type": "code",
    }
    return f"https://{domain}/oauth/authorize/?{urlencode(params)}"


async def exchange_code(code: str, portal: str) -> dict:
    domain = (portal or "").strip().lower().replace("https://", "").replace("http://", "").strip("/")
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(_TOKEN_URL, params={
            "grant_type":    "authorization_code",
            "client_id":     BITRIX24_CLIENT_ID,
            "client_secret": BITRIX24_CLIENT_SECRET,
            "code":          code,
            "redirect_uri":  redirect_uri(),
            "scope":         "crm",
        })
    data = r.json()
    if "error" in data:
        raise RuntimeError(f"Bitrix24 OAuth: {data.get('error_description', data['error'])}")

    access  = data.get("access_token", "")
    refresh = data.get("refresh_token", "")
    exp     = int(time.time()) + int(data.get("expires_in", 3600))
    # Bitrix24 возвращает реальный домен портала в ответе — надёжнее, чем то,
    # что вводил пользователь (может отличаться регистром/протоколом).
    resolved_domain = data.get("domain", domain)

    return {"access_token": access, "refresh_token": refresh, "expires_at": str(exp), "domain": resolved_domain}


async def _do_refresh(refresh_token: str, domain: str) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(_TOKEN_URL, params={
            "grant_type":    "refresh_token",
            "client_id":     BITRIX24_CLIENT_ID,
            "client_secret": BITRIX24_CLIENT_SECRET,
            "refresh_token": refresh_token,
        })
    data = r.json()
    if "error" in data:
        raise RuntimeError(f"Не удалось обновить токен Bitrix24: {data.get('error_description', data['error'])}")
    return {
        "access_token": data.get("access_token", ""),
        "expires_at":   str(int(time.time()) + int(data.get("expires_in", 3600))),
        "domain":       data.get("domain", domain),
    }


async def get_valid_token() -> tuple[str, str]:
    """Возвращает (access_token, domain портала) для текущего тенанта."""
    conn = connections.get_exact_by_name(CONN_NAME)
    if not conn:
        raise RuntimeError("Bitrix24 не подключён. Нажми «Войти через Bitrix24» в разделе Доступы.")

    fields      = conn.get("fields", {})
    access_tok  = fields.get("access_token", "")
    refresh_tok = fields.get("refresh_token", "")
    expires_at  = int(fields.get("expires_at") or 0)
    domain      = fields.get("domain", "")

    if not access_tok or time.time() > expires_at - 60:
        if not refresh_tok:
            raise RuntimeError("Токен Bitrix24 истёк. Переподключи Bitrix24 через раздел Доступы.")
        new = await _do_refresh(refresh_tok, domain)
        updated = {**fields, **new}
        connections.save({"id": conn.get("id"), "name": CONN_NAME, "type": "oauth",
                           "fields": updated, "note": conn.get("note", "")})
        return new["access_token"], new.get("domain", domain)

    return access_tok, domain


def connected() -> bool:
    return connections.get_exact_by_name(CONN_NAME) is not None


def revoke() -> None:
    """У Bitrix24 нет отдельного revoke-эндпоинта для локальных приложений —
    удаление подключения на нашей стороне (владелец может отозвать доступ и
    в самом портале: Приложения → установленные → удалить)."""
    conn = connections.get_exact_by_name(CONN_NAME)
    if conn and conn.get("id"):
        connections.delete(conn["id"])
