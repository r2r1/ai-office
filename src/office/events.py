"""
Event Layer (item 7) — отделы взаимодействуют через СОБЫТИЯ, а не напрямую.

Идея из gpt_vision.md: вместо того чтобы дёргать конкретного коллегу
(ask_colleague), отдел публикует доменное событие в компанию — наблюдение,
проблему, возможность или блокер. CEO (orchestrator) на своём цикле
ИНТЕРПРЕТИРУЕТ накопленные события и решает, что с ними делать (поставить задачу
другому отделу, скорректировать курс). Так агенты не знают друг о друге напрямую —
связь идёт через компанию.

Поток: Событие → Интерпретация (CEO) → Решение → Исполнение.

Это ДОМЕННЫЕ события офиса (per-tenant), а не SSE-события UI (см. bus.py).
Хранилище: data/tenants/<tid>/events.json — {"events": [...], "seq": N}.
"""

import time

from src.saas import context as ctx

_FILE = "events.json"
_MAX = 100

# Типы сигналов, которые отдел может поднять в компанию.
KINDS = {
    "problem":     "🔴 проблема",
    "blocker":     "⛔ блокер",
    "opportunity": "🟢 возможность",
    "signal":      "📡 наблюдение",
    "info":        "ℹ️ информация",
}


def _load() -> dict:
    return ctx.read_json(_FILE, {"events": [], "seq": 0})


def _save(d: dict) -> None:
    ctx.write_json(_FILE, d)


def raise_event(kind: str, summary: str, detail: str = "",
                from_role: str = "", from_agent: str = "") -> dict:
    """Отдел публикует событие в компанию. Возвращает созданное событие."""
    summary = (summary or "").strip()
    if not summary:
        return {}
    kind = kind if kind in KINDS else "signal"
    d = _load()
    d["seq"] = d.get("seq", 0) + 1
    ev = {
        "id": d["seq"],
        "kind": kind,
        "summary": summary[:240],
        "detail": (detail or "").strip()[:600],
        "from_role": from_role,
        "from_agent": from_agent,
        "ts": time.time(),
        "processed": False,
    }
    d["events"] = (d.get("events", []) + [ev])[-_MAX:]
    _save(d)
    return ev


def pending() -> list[dict]:
    """Необработанные CEO события (для интерпретации на цикле)."""
    return [e for e in _load().get("events", []) if not e.get("processed")]


def mark_processed(ids: list[int]) -> None:
    if not ids:
        return
    idset = set(ids)
    d = _load()
    for e in d.get("events", []):
        if e.get("id") in idset:
            e["processed"] = True
    _save(d)


def recent(n: int = 30) -> list[dict]:
    return list(reversed(_load().get("events", [])))[:n]


def context_block() -> str:
    """Блок необработанных сигналов для промпта CEO (или '')."""
    items = pending()
    if not items:
        return ""
    lines = []
    for e in items[-8:]:
        label = KINDS.get(e["kind"], e["kind"])
        who = e.get("from_role") or "отдел"
        lines.append(f"- {label} от {who}: {e['summary']}")
    return ("\n=== СИГНАЛЫ ОТ ОТДЕЛОВ (события, требуют интерпретации) ===\n"
            + "\n".join(lines) + "\n")


def reset() -> None:
    ctx.delete_file(_FILE)
