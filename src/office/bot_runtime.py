"""
Polling Telegram-ботов.

На localhost Telegram не может поставить вебхук, поэтому модуль сам опрашивает
getUpdates для всех тенантов с включённым ботом. Работает автоматически:
- localhost / без APP_BASE_URL → polling всегда включён
- продакшен HTTPS → polling включён только если BOT_POLLING=1

Вебхук и getUpdates взаимоисключающи: на localhost launch_bot вебхук не ставит.
"""

import asyncio
import os

import httpx

from src.saas import context as ctx
from src.saas import store as saas_store
from src.office import bot_config, bot_engine

_offsets: dict[str, int] = {}   # tid -> следующий update_id


def _should_poll() -> bool:
    """Polling нужен на localhost или если явно включён флагом."""
    if os.getenv("BOT_POLLING", "0") == "1":
        return True
    base = os.getenv("APP_BASE_URL", "http://localhost:8000")
    return base.startswith("http://localhost") or "127.0.0.1" in base or not base.startswith("https://")


async def _poll_tenant(tid: str) -> None:
    ctx.set_tenant(tid)
    cfg = bot_config.get()
    if not cfg.get("enabled"):
        return
    token = bot_config.resolve_token()
    if not token:
        return
    offset = _offsets.get(tid, 0)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                f"https://api.telegram.org/bot{token}/getUpdates",
                json={"offset": offset, "timeout": 5},
            )
            data = r.json()
    except Exception:
        return
    if not data.get("ok"):
        return
    for upd in data.get("result", []):
        _offsets[tid] = upd["update_id"] + 1
        ctx.set_tenant(tid)
        try:
            await bot_engine.handle_update(upd)
        except Exception:
            pass


async def run() -> None:
    """Фоновый цикл: опрашивает всех тенантов с включённым ботом."""
    while True:
        try:
            if _should_poll():
                tids = {ws["id"] for ws in saas_store.all_workspaces()}
                tids.add("default")  # demo / без авторизации
                for tid in tids:
                    await _poll_tenant(tid)
        except Exception:
            pass
        await asyncio.sleep(2)


def enabled() -> bool:
    """Оставлено для обратной совместимости — run() теперь запускается всегда."""
    return True
