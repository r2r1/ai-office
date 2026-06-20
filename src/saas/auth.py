"""
Аутентификация: сессии (подписанная cookie на PyJWT) + вход через GitHub OAuth.

GitHub OAuth закрывает сразу две задачи: вход в сервис И подключение GitHub-аккаунта
клиента (тем же токеном позже делаем push/деплой кода).

Конфигурация через .env:
    APP_SECRET=<длинная случайная строка>     # подпись сессий
    APP_BASE_URL=http://localhost:8000         # для redirect_uri
    GITHUB_CLIENT_ID=...                        # GitHub OAuth App
    GITHUB_CLIENT_SECRET=...
    ALLOW_DEV_LOGIN=1                           # локальный вход без GitHub (dev)
"""

import os
import time

import httpx
import jwt

SESSION_COOKIE = "ai_office_session"
SESSION_TTL = 60 * 60 * 24 * 14  # 14 дней
STATE_TTL = 600  # 10 минут на завершение OAuth

APP_SECRET = os.getenv("APP_SECRET", "dev-insecure-change-me")
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000").rstrip("/")
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")
ALLOW_DEV_LOGIN = os.getenv("ALLOW_DEV_LOGIN", "1") == "1"

GITHUB_AUTHORIZE = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN = "https://github.com/login/oauth/access_token"
GITHUB_API = "https://api.github.com"


def github_configured() -> bool:
    return bool(GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET)


# ---- Сессии ----

def make_session(user_id: str) -> str:
    now = int(time.time())
    return jwt.encode(
        {"uid": user_id, "iat": now, "exp": now + SESSION_TTL},
        APP_SECRET, algorithm="HS256",
    )


def read_session(token: str) -> str | None:
    if not token:
        return None
    try:
        data = jwt.decode(token, APP_SECRET, algorithms=["HS256"])
        return data.get("uid")
    except jwt.PyJWTError:
        return None


# ---- OAuth state (stateless, подписанный) ----

def make_state() -> str:
    now = int(time.time())
    return jwt.encode({"k": "oauth", "iat": now, "exp": now + STATE_TTL},
                      APP_SECRET, algorithm="HS256")


def verify_state(state: str) -> bool:
    try:
        jwt.decode(state, APP_SECRET, algorithms=["HS256"])
        return True
    except jwt.PyJWTError:
        return False


# ---- GitHub OAuth ----

def github_login_url() -> str:
    from urllib.parse import urlencode
    params = {
        "client_id": GITHUB_CLIENT_ID,
        "redirect_uri": f"{APP_BASE_URL}/auth/github/callback",
        "scope": "read:user user:email repo",
        "state": make_state(),
        "allow_signup": "true",
    }
    return f"{GITHUB_AUTHORIZE}?{urlencode(params)}"


async def github_exchange_code(code: str) -> str | None:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            GITHUB_TOKEN,
            headers={"Accept": "application/json"},
            data={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": f"{APP_BASE_URL}/auth/github/callback",
            },
        )
    try:
        return r.json().get("access_token")
    except ValueError:
        return None


async def github_fetch_profile(token: str) -> dict | None:
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    async with httpx.AsyncClient(timeout=20) as client:
        u = await client.get(f"{GITHUB_API}/user", headers=headers)
        if u.status_code != 200:
            return None
        profile = u.json()
        if not profile.get("email"):
            emails = await client.get(f"{GITHUB_API}/user/emails", headers=headers)
            if emails.status_code == 200:
                primary = next((e for e in emails.json() if e.get("primary")), None)
                if primary:
                    profile["email"] = primary.get("email")
    return profile
