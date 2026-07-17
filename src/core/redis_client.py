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
