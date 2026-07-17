"""
Единый клиент Redis для распределённого состояния между несколькими серверами
(docs/technical-due-diligence-2026-07-17.md §2.1/§11): rate-limit, локи,
SSE pub/sub.

Без REDIS_URL в .env всё работает как раньше — один процесс, in-memory
состояние; Redis не обязателен для локальной разработки или запуска одного
сервера, только для горизонтального масштабирования на несколько серверов.
Соединение проверяется один раз при первом обращении (PING) — если Redis
не настроен или недоступен, все зависящие модули молча деградируют к
прежнему in-memory поведению, а не падают.
"""

import os

try:
    import redis as _redis_lib
except ImportError:
    _redis_lib = None

_client = None
_tried = False


def get_client():
    """Возвращает подключённый redis.Redis или None (если REDIS_URL не задан,
    пакет redis не установлен, либо PING не прошёл). Кешируется на процесс —
    один раз попробовали, дальше не долбим недоступный Redis на каждый запрос."""
    global _client, _tried
    if _tried:
        return _client
    _tried = True
    url = os.getenv("REDIS_URL", "").strip()
    if not url or _redis_lib is None:
        return None
    try:
        c = _redis_lib.Redis.from_url(
            url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2)
        c.ping()
        _client = c
    except Exception:
        _client = None
    return _client


def available() -> bool:
    return get_client() is not None


def reset_for_tests() -> None:
    """Сбрасывает кеш попытки подключения — тесты переключают REDIS_URL
    между сценариями "доступен"/"недоступен" и должны видеть актуальное
    состояние, не залипшее с первого вызова в процессе."""
    global _client, _tried
    _client = None
    _tried = False


# ---- Распределённые локи (docs/technical-due-diligence-2026-07-17.md §2.1) ----
# Классический паттерн SET NX PX + токен: acquire ставит ключ, только если его
# ещё нет (NX), с TTL (PX) — если процесс, взявший лок, упадёт молча, лок сам
# истечёт и не будет держать ресурс вечно. release/renew проверяют токен через
# Lua-скрипт (атомарно "прочитать-и-сравнить-и-удалить/продлить"), чтобы один
# процесс не мог случайно снять/продлить чужой лок, если его собственный уже
# истёк и был перехвачен другим процессом — иначе гонка: A держит лок, TTL
# истекает, B перехватывает, A (не зная об этом) продлевает УЖЕ ЧУЖОЙ лок.
_RELEASE_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""
_RENEW_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("pexpire", KEYS[1], ARGV[2])
else
    return 0
end
"""


def try_acquire_lock(key: str, ttl_seconds: float) -> str | None:
    """Пытается взять лок `key` на ttl_seconds. Возвращает уникальный токен
    (нужен для release/renew) при успехе, или None если уже занят кем-то
    другим. Если Redis не настроен/недоступен — возвращает пустой токен ""
    (не None!): вызывающий код должен трактовать "" как "лока нет, но и
    конкурентов тоже нет — работай, как раньше, в один процесс"."""
    import uuid
    client = get_client()
    if client is None:
        return ""
    token = uuid.uuid4().hex
    ok = client.set(key, token, nx=True, px=int(ttl_seconds * 1000))
    return token if ok else None


def renew_lock(key: str, token: str, ttl_seconds: float) -> bool:
    """Продлевает TTL уже взятого лока — только если токен совпадает (это
    всё ещё НАШ лок, не чужой, перехваченный после истечения)."""
    if not token:
        return True  # Redis недоступен — локи не используются, всегда "ок"
    client = get_client()
    if client is None:
        return True
    try:
        return bool(client.eval(_RENEW_LUA, 1, key, token, int(ttl_seconds * 1000)))
    except Exception:
        return False


def release_lock(key: str, token: str) -> None:
    if not token:
        return
    client = get_client()
    if client is None:
        return
    try:
        client.eval(_RELEASE_LUA, 1, key, token)
    except Exception:
        pass
