"""
Помощники, общие для нескольких HTTP-роутеров server.py (routers/*.py).

Единая точка — иначе rate-limit-буфер (_rate_buckets) продублировался бы
между файлами и лимит перестал бы быть общим для всего приложения.
"""

import os
import time

from fastapi.requests import Request
from fastapi.responses import HTMLResponse, Response

from src.office import workspace as workspace_module
from src.saas import auth as saas_auth, store as saas_store
from src.saas import context as saas_context

# Единый источник правды (PR-5, docs/technical-due-diligence-2026-07-17.md
# §3.2.1): раньше DEMO_MODE был локальной константой server.py, и после
# разбивки на routers/*.py два роутера (team.py, comms.py) продолжали на
# неё ссылаться, не импортируя — реальный баг, найденный живой браузерной
# проверкой (NameError на /api/brief/status, /api/chat, /api/ask), не
# статическим анализом. server.py импортирует это отсюда же, а не определяет
# заново — иначе снова разъедется при следующей правке.
DEMO_MODE = os.getenv("DEMO_MODE", "0") == "1"

# ---- Rate limiting ----
# Один универсальный bucket на (namespace, key): /auth/*, /api/terminal, /api/run
# (дорогое исполнение кода), публичный /api/lead/{tenant}/{slug} и /api/onboarding/
# scan — все проходят через один и тот же механизм (docs/audit-dd-2026-07-06.md
# §11/§19 п.10).
#
# Аудит docs/technical-due-diligence-2026-07-17.md §2.1/§5.5: in-memory bucket
# в процессе не работает на нескольких серверах (каждый считает свой лимит
# независимо — реальный лимит умножается на число серверов) и обнуляется
# рестартом. Если REDIS_URL настроен — лимит считается в Redis (общий для
# всех серверов, скользящее окно 60с через ZSET, та же семантика, что была у
# in-memory списка таймстампов). Без REDIS_URL — прежнее in-memory поведение,
# Redis не обязателен для локальной разработки/одного сервера.
_rate_buckets: dict[str, dict[str, list[float]]] = {}


def rate_limited(namespace: str, key: str, max_per_min: int) -> bool:
    """True — лимит превышен (запрос НУЖНО отклонить). Иначе засчитывает попытку."""
    from src.core import redis_client
    client = redis_client.get_client()
    if client is not None:
        return _rate_limited_redis(client, namespace, key, max_per_min)
    return _rate_limited_memory(namespace, key, max_per_min)


def _rate_limited_redis(client, namespace: str, key: str, max_per_min: int) -> bool:
    import os
    now = time.time()
    rkey = f"ratelimit:{namespace}:{key}"
    pipe = client.pipeline()
    pipe.zremrangebyscore(rkey, 0, now - 60)
    pipe.zcard(rkey)
    _removed, count = pipe.execute()
    if count >= max_per_min:
        client.expire(rkey, 60)
        return True
    # member должен быть уникален внутри ZSET — двух попаданий в одну и ту же
    # миллисекунду достаточно редко, но добавляем нонс на случай гонки.
    member = f"{now}:{os.urandom(4).hex()}"
    client.zadd(rkey, {member: now})
    client.expire(rkey, 60)
    return False


def _rate_limited_memory(namespace: str, key: str, max_per_min: int) -> bool:
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


# ---- Идемпотентность ----
# docs/technical-due-diligence-2026-07-17.md §5.6: двойной клик/ретрай сети на
# рискованном действии (принять инициативу, вебхук от Telegram/GitHub) раньше
# мог выполнить побочный эффект дважды. Точечно — не для вообще всех запросов
# (у большинства повтор и так безвреден: GET ничего не меняет, "поставить на
# паузу" дважды подряд не создаёт вторую паузу), а там, где повтор реально
# порождает новую сущность. Ключ ("Idempotency-Key") генерирует КЛИЕНТ на
# конкретное действие — не платформа проставляет id всему подряд.
_idem_memory: dict[str, tuple[float, object]] = {}


async def idempotent(namespace: str, key: str, ttl_seconds: float, compute):
    """Если (namespace, key) уже видели — вернуть закешированный результат
    БЕЗ повторного вызова compute() (значит, без повторных побочных эффектов).
    Иначе — вызвать compute() (может делать что угодно: писать в план,
    публиковать события), закешировать результат и вернуть его.

    key="" (клиент не прислал Idempotency-Key) — дедупликации нет, compute()
    вызывается всегда: не можем дедуплицировать то, что нечем отличить."""
    if not key:
        return await compute()
    import json as _json
    full_key = f"idem:{namespace}:{key}"
    from src.core import redis_client
    client = redis_client.get_client()
    if client is not None:
        cached = client.get(full_key)
        if cached is not None:
            return _json.loads(cached)
        result = await compute()
        # Кешируем только сериализуемый JSON-результат (обычный ответ). Ветки
        # ошибок/отказов иногда возвращают готовый Response-объект (например
        # JSONResponse со status_code=409) — те не мутируют состояние, поэтому
        # безопасно НЕ дедуплицировать: пересчитать при повторе не страшно.
        if isinstance(result, (dict, list)):
            client.set(full_key, _json.dumps(result, ensure_ascii=False), ex=int(ttl_seconds))
        return result
    now = time.time()
    entry = _idem_memory.get(full_key)
    if entry and entry[0] > now:
        return entry[1]
    result = await compute()
    if isinstance(result, (dict, list)):
        _idem_memory[full_key] = (now + ttl_seconds, result)
        if len(_idem_memory) > 2000:
            for stale in [k for k, (exp, _v) in _idem_memory.items() if exp <= now]:
                _idem_memory.pop(stale, None)
    return result


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



# --- Перенесено из server.py (PR-5): используется несколькими роутерами ---

def with_worker_id(payload):
    """Зеркалит worker_id рядом с agent_id в исходящем JSON (BOS §12 п.4:
    agent_id → worker_id, agent_id остаётся deprecated-алиасом на переходный
    период). Работает и на одном dict, и на списке dict — тем местам ответа,
    которые НЕ идут через bus.publish (там зеркалирование уже единое, см.
    office/bus.py) и формируются server.py напрямую из registry/state/costs."""
    if isinstance(payload, dict):
        return {**payload, "worker_id": payload["agent_id"]} if "agent_id" in payload else payload
    return [{**d, "worker_id": d["agent_id"]} if isinstance(d, dict) and "agent_id" in d else d
            for d in payload]


# Публично отдаём только веб-ресурсы. Если сайт опубликован из КОРНЯ workspace
# (root==""), без этого фильтра были бы доступны bot.py с токенами, docs/*, .env и т.п.
_WEB_ASSET_EXT = {
    ".html", ".htm", ".css", ".js", ".mjs", ".map", ".json", ".svg", ".png", ".jpg",
    ".jpeg", ".gif", ".webp", ".avif", ".ico", ".woff", ".woff2", ".ttf", ".otf",
    ".mp4", ".webm", ".mp3", ".txt", ".xml", ".webmanifest",
}
# Явно приватное — никогда не отдаём, даже если попало в веб-папку.
_FORBIDDEN_NAMES = {".env", "requirements.txt", "config.py", "bot.py", "main.py"}

def serve_site_file(site: dict, subpath: str):
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
