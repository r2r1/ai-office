"""
Общий канал офиса — лента сообщений всех агентов и пользователя.

Агенты могут читать канал через инструмент read_office_chat.
Пользователь может писать через /api/chat.
"""

import json
import time
import uuid
from pathlib import Path

CHANNEL_FILE = Path("reports/office_channel.json")
MAX_MESSAGES = 200

_messages: list[dict] = []


def post(from_id: str, role: str, text: str) -> dict:
    """Добавляет сообщение в канал. Возвращает сохранённое сообщение."""
    msg = {
        "id": uuid.uuid4().hex[:8],
        "from": from_id,
        "role": role,
        "text": text.strip(),
        "ts": time.time(),
    }
    _messages.append(msg)
    if len(_messages) > MAX_MESSAGES:
        del _messages[: len(_messages) - MAX_MESSAGES]
    _persist()
    return msg


def recent(n: int = 50) -> list[dict]:
    """Возвращает последние n сообщений."""
    return list(_messages[-n:])


def clear() -> None:
    _messages.clear()
    if CHANNEL_FILE.exists():
        CHANNEL_FILE.unlink()


def load() -> None:
    global _messages
    if CHANNEL_FILE.exists():
        try:
            data = json.loads(CHANNEL_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                _messages = data[-MAX_MESSAGES:]
        except (json.JSONDecodeError, OSError):
            pass


def reset() -> None:
    clear()


def _persist() -> None:
    CHANNEL_FILE.parent.mkdir(parents=True, exist_ok=True)
    CHANNEL_FILE.write_text(
        json.dumps(_messages, ensure_ascii=False, indent=2), encoding="utf-8"
    )
