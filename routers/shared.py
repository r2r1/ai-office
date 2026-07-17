"""
Помощники, общие для нескольких HTTP-роутеров server.py (routers/*.py).

Единая точка — иначе rate-limit-буфер (_rate_buckets) продублировался бы
между файлами и лимит перестал бы быть общим для всего приложения.
"""

import time

from fastapi.requests import Request

from src.saas import auth as saas_auth, store as saas_store

# ---- Rate limiting (без внешних зависимостей) ----
# Один универсальный bucket на (namespace, key): /auth/*, /api/terminal, /api/run
# (дорогое исполнение кода), публичный /api/lead/{tenant}/{slug} и /api/onboarding/
# scan — все проходят через один и тот же механизм (docs/audit-dd-2026-07-06.md
# §11/§19 п.10). Чистим мёртвые ключи, только когда bucket раздулся.
_rate_buckets: dict[str, dict[str, list[float]]] = {}


def rate_limited(namespace: str, key: str, max_per_min: int) -> bool:
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


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or request.client.host or "unknown"


def current_user(request: Request) -> dict | None:
    """Текущий пользователь из подписанной session-cookie (или None)."""
    uid = saas_auth.read_session(request.cookies.get(saas_auth.SESSION_COOKIE, ""))
    return saas_store.get_user(uid) if uid else None


def set_session_cookie(resp, user_id: str) -> None:
    secure = saas_auth.APP_BASE_URL.startswith("https")
    resp.set_cookie(
        saas_auth.SESSION_COOKIE, saas_auth.make_session(user_id),
        max_age=saas_auth.SESSION_TTL, httponly=True, samesite="lax", secure=secure,
    )
