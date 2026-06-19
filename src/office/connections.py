"""
Подключения к внешним платформам — API-ключи, логины/пароли, токены.

Хранятся локально в reports/connections.json. Пользователь управляет ими
через дашборд (вкладка «Подключения»). Агенты могут запросить нужный
доступ через инструмент get_connection, а если его нет — спросить через ask_user.
"""

import json
import uuid
from pathlib import Path

CONN_FILE = Path("reports/connections.json")

_conns: list[dict] = []


def list_all() -> list[dict]:
    return list(_conns)


def save(conn: dict) -> dict:
    """Создаёт или обновляет подключение. conn = {id?, name, type, fields:{...}, note}."""
    cid = conn.get("id")
    item = {
        "id": cid or uuid.uuid4().hex[:8],
        "name": (conn.get("name") or "").strip(),
        "type": (conn.get("type") or "api").strip(),  # api | login | token | other
        "fields": conn.get("fields") or {},
        "note": (conn.get("note") or "").strip(),
    }
    for i, c in enumerate(_conns):
        if c["id"] == item["id"]:
            _conns[i] = item
            _persist()
            return item
    _conns.append(item)
    _persist()
    return item


def delete(cid: str) -> bool:
    global _conns
    before = len(_conns)
    _conns = [c for c in _conns if c["id"] != cid]
    _persist()
    return len(_conns) < before


def get_by_name(name: str) -> dict | None:
    name = (name or "").lower().strip()
    for c in _conns:
        if c["name"].lower() == name:
            return c
    # частичное совпадение
    for c in _conns:
        if name and name in c["name"].lower():
            return c
    return None


def names() -> list[str]:
    return [c["name"] for c in _conns if c["name"]]


def _persist() -> None:
    CONN_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONN_FILE.write_text(json.dumps(_conns, ensure_ascii=False, indent=2), encoding="utf-8")


def load() -> None:
    global _conns
    if CONN_FILE.exists():
        try:
            data = json.loads(CONN_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                _conns = data
        except (json.JSONDecodeError, OSError):
            pass


def reset() -> None:
    global _conns
    _conns = []
    if CONN_FILE.exists():
        CONN_FILE.unlink()
