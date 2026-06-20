"""
Интеграция с Telegram через Bot API.

Реальные вызовы https://api.telegram.org/bot<TOKEN>/<method>.
Учётные данные: токен бота (получается у @BotFather) и (для отправки)
идентификатор чата/канала.

Это эталонная интеграция — по её образцу добавляются остальные сервисы.
"""

import httpx

from src.integrations.base import Action, CredField, Integration

API = "https://api.telegram.org/bot{token}/{method}"


async def _call(token: str, method: str, payload: dict) -> dict:
    """Один вызов Telegram Bot API. Бросает RuntimeError с понятным текстом."""
    url = API.format(token=token, method=method)
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(url, json=payload)
    try:
        data = resp.json()
    except ValueError:
        raise RuntimeError(f"Telegram вернул не-JSON (HTTP {resp.status_code})")
    if not data.get("ok"):
        desc = data.get("description", "неизвестная ошибка")
        raise RuntimeError(f"Telegram API: {desc}")
    return data.get("result", {})


def _token(creds: dict) -> str:
    token = (creds.get("token") or creds.get("key") or creds.get("value") or "").strip()
    if not token:
        raise RuntimeError("Нет токена бота. Запроси у пользователя через ask_user.")
    return token


async def _send_message(creds: dict, params: dict) -> str:
    token = _token(creds)
    chat_id = (params.get("chat_id") or creds.get("chat_id") or "").strip()
    text = (params.get("text") or "").strip()
    if not chat_id:
        return ("Не указан chat_id (id чата/канала). Для канала это @username, для лички — "
                "числовой id. Уточни у пользователя через ask_user.")
    if not text:
        return "Пустой текст сообщения."
    payload = {"chat_id": chat_id, "text": text}
    if params.get("parse_mode"):
        payload["parse_mode"] = params["parse_mode"]
    result = await _call(token, "sendMessage", payload)
    mid = result.get("message_id")
    return f"Сообщение отправлено в {chat_id} (message_id={mid})."


async def _send_photo(creds: dict, params: dict) -> str:
    token = _token(creds)
    chat_id = (params.get("chat_id") or creds.get("chat_id") or "").strip()
    photo = (params.get("photo_url") or "").strip()
    if not chat_id or not photo:
        return "Нужны chat_id и photo_url (прямая ссылка на изображение)."
    payload = {"chat_id": chat_id, "photo": photo}
    if params.get("caption"):
        payload["caption"] = params["caption"]
    result = await _call(token, "sendPhoto", payload)
    return f"Фото отправлено в {chat_id} (message_id={result.get('message_id')})."


async def _get_me(creds: dict, params: dict) -> str:
    """Проверка подключения — getMe возвращает данные бота."""
    token = _token(creds)
    result = await _call(token, "getMe", {})
    return (f"Подключение работает. Бот: @{result.get('username')} "
            f"(id={result.get('id')}, имя «{result.get('first_name')}»).")


INTEGRATION = Integration(
    name="telegram",
    title="Telegram",
    icon="✈️",
    description="Отправка сообщений и постов в чаты и каналы через Bot API.",
    how_to=(
        "1. Открой @BotFather в Telegram → /newbot → задай имя и username.\n"
        "2. Скопируй TOKEN вида 123456:ABC-DEF...\n"
        "3. Добавь бота админом в нужный канал (или напиши ему в личку).\n"
        "4. Для отправки укажи chat_id: для канала это @username, "
        "для лички — числовой id (узнать можно через @userinfobot)."
    ),
    cred_fields=[
        CredField(key="token", label="Токен бота (от @BotFather)", secret=True),
        CredField(key="chat_id", label="Chat ID по умолчанию (@канал или id), опц.", secret=False),
    ],
    actions={
        "get_me": Action(
            name="get_me",
            description="Проверить подключение бота (getMe). Параметры не нужны.",
            handler=_get_me,
        ),
        "send_message": Action(
            name="send_message",
            description="Отправить текстовое сообщение/пост в чат или канал.",
            handler=_send_message,
            params={
                "chat_id": {"type": "string", "description": "@канал или числовой id (если не задан — берётся из подключения)"},
                "text": {"type": "string", "description": "Текст сообщения"},
                "parse_mode": {"type": "string", "enum": ["HTML", "Markdown", "MarkdownV2"], "description": "Разметка, опционально"},
            },
            required=["text"],
        ),
        "send_photo": Action(
            name="send_photo",
            description="Отправить фото по прямой ссылке с подписью.",
            handler=_send_photo,
            params={
                "chat_id": {"type": "string", "description": "@канал или числовой id"},
                "photo_url": {"type": "string", "description": "Прямая ссылка на изображение"},
                "caption": {"type": "string", "description": "Подпись, опционально"},
            },
            required=["photo_url"],
        ),
    },
)
