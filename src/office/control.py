"""
Управление состоянием офис-цикла — пауза / возобновление.

data/tenants/<tid>/control.json:
  {"paused": true/false, "reason": "...", "paused_at": timestamp}
"""

import time
from src.saas import context as ctx

_FILE = "control.json"


def _load() -> dict:
    return ctx.read_json(_FILE, {"paused": False, "reason": "", "paused_at": 0})


def _save(d: dict) -> None:
    ctx.write_json(_FILE, d)


def is_paused() -> bool:
    return bool(_load().get("paused"))


def pause(reason: str = "") -> None:
    _save({"paused": True, "reason": reason, "paused_at": time.time()})
    _reset_approvals()


def resume() -> None:
    _save({"paused": False, "reason": "", "paused_at": 0})
    _reset_approvals()


def _reset_approvals() -> None:
    # Разовые одобрения (публикация и т.п.) не должны переживать паузу/возобновление —
    # это новая «сессия доверия», клиент подтверждает заново. Ленивый импорт против цикла.
    try:
        from src.office import autonomy
        autonomy.reset_approvals()
    except Exception:
        pass


def status() -> dict:
    d = _load()
    return {
        "paused": d.get("paused", False),
        "reason": d.get("reason", ""),
        "paused_at": d.get("paused_at", 0),
    }
