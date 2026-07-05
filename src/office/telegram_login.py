"""
Вход в личный Telegram-аккаунт (MTProto, через Telethon) — интерактивный флоу,
не вписывается в обычную "введи один ключ" модель connections.py: нужен запрос
кода на телефон, ввод кода, опционально 2FA-пароль. Здесь держим ТОЛЬКО состояние
незавершённого входа (эфемерно, в памяти процесса, по тенанту) — как только вход
завершён успешно, сессия уходит в connections.py (шифруется at-rest как обычно).

⚠️ Личный аккаунт ≠ бот: сообщение уходит от имени реального человека. Массовая
холодная рассылка незнакомым людям — то, из-за чего Telegram ограничивает аккаунты
(anti-spam эвристики видят паттерн "много первых сообщений подряд"), вне зависимости
от того, через MTProto это делается или руками. Используй по одному лиду за раз.

О api_id/api_hash: настоящего OAuth для MTProto-сессии (с правом слать сообщения)
у Telegram НЕТ — их Login Widget подтверждает только личность для входа на сайт,
сессию для отправки не выдаёт. Обычный пользователь не должен идти на my.telegram.org
сам: api_id/api_hash — ключи ПРИЛОЖЕНИЯ (одни на весь AI-Office, как LLM_API_KEY),
их вводит оператор один раз в .env (TELEGRAM_API_ID/TELEGRAM_API_HASH). Пользователю
остаётся только телефон → код (+ 2FA). Если оператор их не задал — как временный
фолбэк форма всё ещё принимает api_id/api_hash вручную (см. has_default_creds()).
"""

import os
import time

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    SessionPasswordNeededError, PhoneCodeInvalidError, PhoneCodeExpiredError,
    FloodWaitError, PhoneNumberInvalidError,
)


def default_creds() -> tuple[int, str] | None:
    """Ключи ПРИЛОЖЕНИЯ, заданные оператором один раз (.env), а не пользователем.
    my.telegram.org — шаг разработчика приложения, не конечного клиента; без
    этого поле api_id/api_hash в форме входа было непонятно обычному пользователю."""
    try:
        api_id = int(os.getenv("TELEGRAM_API_ID") or 0)
    except ValueError:
        api_id = 0
    api_hash = (os.getenv("TELEGRAM_API_HASH") or "").strip()
    if not api_id or not api_hash:
        return None
    return api_id, api_hash


def has_default_creds() -> bool:
    return default_creds() is not None


def proxy_from_env() -> tuple | None:
    """MTProto — сырой TCP, а не HTTP: Telethon НЕ читает HTTP_PROXY/HTTPS_PROXY
    автоматически (в отличие от httpx/openai-клиента в core/llm.py), хотя сама
    сеть может требовать прокси для любого внешнего соединения (реальный кейс:
    та же машина, что не достаёт LLM-провайдера напрямую, не достаёт и Telegram).
    PySocks поддерживает туннелирование через HTTP CONNECT — передаём тот же
    прокси explicit-параметром, раз уж он всё равно настроен в окружении."""
    raw = os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY") or os.getenv("https_proxy") or os.getenv("http_proxy")
    if not raw:
        return None
    try:
        import socks
        from urllib.parse import urlparse
        u = urlparse(raw)
        if not u.hostname or not u.port:
            return None
        return (socks.HTTP, u.hostname, u.port, True, u.username, u.password)
    except Exception:
        return None

# tenant_id -> {"client": TelegramClient, "phone": str, "phone_code_hash": str,
#               "api_id": int, "api_hash": str, "ts": float}
# Эфемерно и осознанно: рестарт сервера просто требует начать вход заново — это
# НЕ состояние домена (в отличие от futures в questions.py, которое per-tenant
# и переживает такие рестарты по другой причине), это ровно middle-of-login буфер.
_pending: dict[str, dict] = {}
_PENDING_TTL = 600  # 10 минут на ввод кода, потом начинай заново


def _cleanup(tid: str) -> None:
    p = _pending.pop(tid, None)
    if p and p.get("client"):
        try:
            p["client"].disconnect()
        except Exception:
            pass


async def start(tid: str, phone: str, api_id: int = 0, api_hash: str = "") -> dict:
    """Шаг 1: запросить код на телефон. api_id/api_hash — опциональны, по
    умолчанию берутся из TELEGRAM_API_ID/TELEGRAM_API_HASH (ключи приложения,
    заданные оператором); ручные значения — фолбэк, если оператор их не задал.
    Возвращает {ok, error?}."""
    if not api_id or not api_hash:
        d = default_creds()
        if not d:
            return {"ok": False, "error": "api_id/api_hash не заданы (ни оператором в .env, ни в форме)."}
        api_id, api_hash = d
    _cleanup(tid)
    client = TelegramClient(StringSession(), api_id, api_hash, proxy=proxy_from_env(), connection_retries=2, timeout=10)
    try:
        await client.connect()
        sent = await client.send_code_request(phone)
    except PhoneNumberInvalidError:
        await client.disconnect()
        return {"ok": False, "error": "Неверный номер телефона (формат +79991234567)."}
    except FloodWaitError as e:
        await client.disconnect()
        return {"ok": False, "error": f"Telegram просит подождать {e.seconds}с перед повтором."}
    except ConnectionError:
        # Не достучались до серверов Telegram вообще (сеть/прокси) — реальный кейс
        # в этой же среде: MTProto не ходит через HTTP_PROXY автоматически (см.
        # proxy_from_env), без явного перехвата это падало необработанным 500.
        try:
            await client.disconnect()
        except Exception:
            pass
        return {"ok": False, "error": "Не удалось подключиться к серверам Telegram — "
                                      "проверьте интернет/прокси и повторите."}
    _pending[tid] = {"client": client, "phone": phone, "phone_code_hash": sent.phone_code_hash,
                     "api_id": api_id, "api_hash": api_hash, "ts": time.time()}
    return {"ok": True}


async def confirm(tid: str, code: str, password: str = "") -> dict:
    """Шаг 2: подтвердить код (+ 2FA-пароль, если включён). Возвращает
    {ok, need_password?, error?} — при успехе сессия УЖЕ сохранена в connections."""
    p = _pending.get(tid)
    if not p or time.time() - p["ts"] > _PENDING_TTL:
        _cleanup(tid)
        return {"ok": False, "error": "Сессия входа истекла — начните заново (номер и код)."}
    client: TelegramClient = p["client"]
    try:
        if password:
            await client.sign_in(password=password)
        else:
            await client.sign_in(phone=p["phone"], code=code, phone_code_hash=p["phone_code_hash"])
    except SessionPasswordNeededError:
        return {"ok": False, "need_password": True,
                "error": "На аккаунте включена двухфакторная защита — введите пароль."}
    except ConnectionError:
        _cleanup(tid)
        return {"ok": False, "error": "Соединение с Telegram прервалось — начните вход заново."}
    except (PhoneCodeInvalidError, PhoneCodeExpiredError):
        return {"ok": False, "error": "Код неверный или истёк — запросите новый."}
    session_str = client.session.save()
    me = await client.get_me()
    await client.disconnect()
    _pending.pop(tid, None)

    from src.office import connections
    connections.save({
        "name": "telegram_personal", "type": "api",
        "fields": {"session": session_str, "phone": p["phone"],
                   "api_id": str(p["api_id"]), "api_hash": p["api_hash"]},
        "note": f"Личный Telegram: {me.first_name or ''} (@{me.username or '—'})",
    })
    return {"ok": True, "name": me.first_name, "username": me.username}


def cancel(tid: str) -> None:
    _cleanup(tid)
