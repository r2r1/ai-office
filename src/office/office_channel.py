"""
Общий канал офиса — лента сообщений всех агентов и пользователя. По тенанту.
"""

import time
import uuid

from src.saas import context as ctx

_FILE = "office_channel.json"
MAX_MESSAGES = 200


def post(from_id: str, role: str, text: str) -> dict:
    msgs = ctx.read_json(_FILE, [])
    msg = {"id": uuid.uuid4().hex[:8], "from": from_id, "role": role,
           "text": text.strip(), "ts": time.time()}
    msgs.append(msg)
    if len(msgs) > MAX_MESSAGES:
        del msgs[: len(msgs) - MAX_MESSAGES]
    ctx.write_json(_FILE, msgs)
    return msg


def recent(n: int = 50) -> list[dict]:
    return ctx.read_json(_FILE, [])[-n:]


def clear() -> None:
    ctx.delete_file(_FILE)


def load() -> None:
    pass


def reset() -> None:
    clear()
