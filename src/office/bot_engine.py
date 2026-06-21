"""
Движок Telegram-бота записи клиентов — ОДИН на всю платформу.

Поведение конкретного бота задаётся конфигом тенанта (bot_config.py) и его токеном.
Сценарий «booking»: /start → выбор услуги → сбор полей (имя, телефон…) → заявка (лид).

Сессии диалога хранятся по chat_id (bot_sessions.json, по тенанту), поэтому движок
stateless между апдейтами и переживает рестарт сервера.
"""

import httpx

from src.saas import context as ctx
from src.office import bot_config, leads, bus

_SESS = "bot_sessions.json"
_API = "https://api.telegram.org/bot{token}/{method}"


async def _api(token: str, method: str, payload: dict) -> dict:
    url = _API.format(token=token, method=method)
    async with httpx.AsyncClient(timeout=20) as client:
        try:
            r = await client.post(url, json=payload)
            return r.json()
        except Exception:
            return {}


async def _send(token: str, chat_id, text: str, keyboard=None) -> None:
    payload = {"chat_id": chat_id, "text": text}
    if keyboard is not None:
        payload["reply_markup"] = keyboard
    await _api(token, "sendMessage", payload)


def _services_keyboard(services: list[str]) -> dict:
    return {"keyboard": [[{"text": s}] for s in services],
            "resize_keyboard": True, "one_time_keyboard": True}


_REMOVE_KB = {"remove_keyboard": True}


def _load_sessions() -> dict:
    return ctx.read_json(_SESS, {})


def _save_sessions(d: dict) -> None:
    ctx.write_json(_SESS, d)


async def handle_update(update: dict) -> None:
    """Обрабатывает один апдейт Telegram согласно конфигу тенанта."""
    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    if chat_id is None:
        return
    text = (msg.get("text") or "").strip()

    cfg = bot_config.get()
    token = bot_config.resolve_token()
    if not token or not cfg.get("enabled"):
        return

    sessions = _load_sessions()
    key = str(chat_id)
    sess = sessions.get(key)
    services = cfg.get("services") or []
    fields = cfg.get("ask_fields") or ["Имя", "Телефон"]

    # /start или новый диалог — приветствие
    if text == "/start" or sess is None:
        greeting = cfg.get("greeting") or "Здравствуйте! Давайте оформим заявку."
        wh = cfg.get("working_hours")
        if wh:
            greeting += f"\n\n🕒 {wh}"
        if services:
            sessions[key] = {"step": "service", "service": "", "data": {}, "idx": 0}
            await _send(token, chat_id, greeting, _services_keyboard(services))
        else:
            # Без услуг — сразу собираем поля
            sessions[key] = {"step": "collect", "service": "", "data": {}, "idx": 0}
            await _send(token, chat_id, greeting + f"\n\n{fields[0]}?", _REMOVE_KB)
        _save_sessions(sessions)
        return

    step = sess.get("step")

    if step == "service":
        if text in services:
            sess["service"] = text
            sess["step"] = "collect"
            sess["idx"] = 0
            await _send(token, chat_id, f"Отлично, «{text}».\n\n{fields[0]}?", _REMOVE_KB)
        else:
            await _send(token, chat_id, "Пожалуйста, выберите услугу кнопкой ниже.",
                        _services_keyboard(services))
        sessions[key] = sess
        _save_sessions(sessions)
        return

    if step == "collect":
        idx = sess.get("idx", 0)
        if idx < len(fields):
            sess["data"][fields[idx]] = text
            idx += 1
            sess["idx"] = idx
        if idx < len(fields):
            await _send(token, chat_id, f"{fields[idx]}?", _REMOVE_KB)
            sessions[key] = sess
            _save_sessions(sessions)
            return
        # Все поля собраны — оформляем заявку
        await _finalize(token, chat_id, cfg, sess)
        sessions.pop(key, None)
        _save_sessions(sessions)
        return

    # Неизвестный шаг — перезапуск
    sessions.pop(key, None)
    _save_sessions(sessions)
    await _send(token, chat_id, "Давайте начнём заново — отправьте /start.")


async def _finalize(token: str, chat_id, cfg: dict, sess: dict) -> None:
    data = sess.get("data", {})
    service = sess.get("service", "")
    # Имя/контакт — по типичным полям, остальное уходит в текст заявки
    name = data.get("Имя") or data.get("Name") or next(iter(data.values()), "Клиент")
    contact = data.get("Телефон") or data.get("Phone") or data.get("Контакт") or ""
    extras = [f"{k}: {v}" for k, v in data.items() if k not in ("Имя", "Name", "Телефон", "Phone")]
    parts = ([f"Услуга: {service}"] if service else []) + extras
    message = "; ".join(parts)

    lead = leads.add(cfg.get("lead_slug", "telegram-bot"), name, contact, message)
    await _send(token, chat_id, cfg.get("success_message") or "Спасибо! Заявка принята. ✅")

    # Уведомляем интерфейс офиса (вкладка «Лиды» + тост)
    try:
        await bus.publish({
            "type": "lead_captured", "lead": lead,
            "text": f"🎯 Заявка из Telegram-бота: {name} ({contact or 'без контакта'})",
        })
    except Exception:
        pass


def reset() -> None:
    ctx.delete_file(_SESS)
