"""
Система инициатив — CEO проактивно предлагает возможности.

Офис не ждёт команды. Он постоянно ищет возможности улучшить
бизнес и предлагает их пользователю с обоснованием и ROI-оценкой.
Пользователь принимает, отклоняет или откладывает инициативу.
При принятии — задачи инициативы добавляются в план.
"""

import time
import uuid
from src.saas import context as ctx

_MAX = 50
_EXPIRE_SECS = 7 * 24 * 3600  # 7 дней


def _load() -> list:
    return ctx.read_json("initiatives") or []


def _save(items: list) -> None:
    ctx.write_json("initiatives", items[-_MAX:])


def add(
    title: str,
    rationale: str,
    expected_outcome: str,
    estimated_effort: str = "1-2 цикла",
    tasks: list | None = None,
    source: str = "ceo",  # "ceo" | "event" | "auto"
) -> str:
    """Добавить инициативу. Дедуп по title."""
    items = _load()
    # Дедупликация по заголовку
    for item in items:
        if item["status"] == "pending" and item["title"].lower() == title.lower():
            return item["id"]

    iid = f"i_{uuid.uuid4().hex[:8]}"
    items.append({
        "id": iid,
        "ts": time.time(),
        "title": title,
        "rationale": rationale,
        "expected_outcome": expected_outcome,
        "estimated_effort": estimated_effort,
        "tasks": tasks or [],
        "source": source,
        "status": "pending",  # pending | accepted | rejected | expired
        "expires_at": time.time() + _EXPIRE_SECS,
    })
    _save(items)
    return iid


def pending() -> list:
    expire_old()
    items = _load()
    return [i for i in items if i["status"] == "pending"]


def accept(iid: str) -> list:
    """Принять инициативу. Возвращает список задач для добавления в план."""
    items = _load()
    tasks = []
    for item in items:
        if item["id"] == iid:
            item["status"] = "accepted"
            tasks = item.get("tasks") or []
            break
    _save(items)
    return tasks


def reject(iid: str) -> None:
    items = _load()
    for item in items:
        if item["id"] == iid:
            item["status"] = "rejected"
            break
    _save(items)


def snooze(iid: str, days: int = 3) -> None:
    """Отложить инициативу на N дней."""
    items = _load()
    for item in items:
        if item["id"] == iid:
            item["expires_at"] = time.time() + days * 86400
            break
    _save(items)


def expire_old() -> None:
    now = time.time()
    items = _load()
    changed = False
    for item in items:
        if item["status"] == "pending" and item.get("expires_at", 0) < now:
            item["status"] = "expired"
            changed = True
    if changed:
        _save(items)


def has_pending_similar(title: str) -> bool:
    for item in pending():
        words_new = set(title.lower().split())
        words_old = set(item["title"].lower().split())
        overlap = len(words_new & words_old) / max(len(words_new), len(words_old), 1)
        if overlap > 0.5:
            return True
    return False


def payload() -> dict:
    p = pending()
    all_items = _load()
    return {
        "pending": p,
        "pending_count": len(p),
        "total": len(all_items),
    }
