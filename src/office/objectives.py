"""
Objectives — измеримые цели компании (см. docs/bos-architecture.md §1, §4).

Objective ≠ Milestone. Milestone (milestones.py) — производный индикатор прогресса
по плану. Objective — desired state: что компания ХОЧЕТ, с полем `measured_by`.
Пока `measured_by` пуст, objective считается НЕИЗМЕРИМЫМ — Gap Analysis его не
трогает, а World Model показывает это как задачу «обеспечить измеримость» (BOS §3,
принцип bootstrapping-режима: «каждый проект должен оставлять после себя
измеримость»).

Хранилище: data/tenants/<tid>/objectives.json — {"items": [...]}.
"""

import time

from src.saas import context as ctx

_FILE = "objectives.json"


def _data() -> dict:
    return ctx.read_json(_FILE, {"items": []})


def _save(d: dict) -> None:
    ctx.write_json(_FILE, d)


def all_objectives() -> list[dict]:
    return list(_data().get("items", []))


def get(oid: str) -> dict | None:
    for o in all_objectives():
        if o["id"] == oid:
            return dict(o)
    return None


def add(title: str, desired: str = "", measured_by: str = "",
        priority: int = 50, source: str = "owner") -> dict:
    """
    Создаёт Objective. `desired` — целевое значение метрики («10 заявок/неделю»),
    `measured_by` — КАК измеряется («count leads.json за 7 дней»); пустой
    measured_by означает «пока неизмеримо» — objective не участвует в gap-анализе.
    `source`: owner (от владельца) | company (сгенерирована офисом).
    """
    d = _data()
    items = d.get("items", [])
    oid = f"obj{len(items) + 1}_{int(time.time()) % 10000}"
    obj = {
        "id": oid, "title": (title or "").strip()[:200],
        "desired": (desired or "").strip()[:200],
        "measured_by": (measured_by or "").strip()[:200],
        "current_value": "", "priority": max(0, min(100, priority)),
        "status": "active", "source": source,
        "created_ts": time.time(), "updated_ts": time.time(),
    }
    items.append(obj)
    d["items"] = items
    _save(d)
    return obj


def update(oid: str, **patch) -> dict | None:
    d = _data()
    for o in d.get("items", []):
        if o["id"] == oid:
            for k in ("title", "desired", "measured_by", "current_value",
                      "priority", "status"):
                if k in patch:
                    o[k] = patch[k]
            o["updated_ts"] = time.time()
            _save(d)
            return dict(o)
    return None


def ensure_leads_objective(desired: str = "10 заявок/неделю") -> dict | None:
    """Автоматически создаёт ИЗМЕРИМУЮ цель «Заявки в неделю» при первой публикации
    сайта (Phase 3b): measured_by="leads.count() за 7 дней" — реальная метрика, не
    пустая декларация. Идемпотентно (по measured_by с 'leads'). Так objectives.
    measurable() перестаёт быть пустым без ручного создания владельцем (DoD)."""
    for o in all_objectives():
        if "leads" in (o.get("measured_by") or "").lower():
            return None  # уже есть измеримая цель по заявкам
    return add(
        title="Заявки с сайта в неделю",
        desired=desired,
        measured_by="leads.count() за 7 дней",
        priority=70,
        source="company",
    )


def measurable() -> list[dict]:
    """Objectives с заполненным measured_by — участвуют в будущем Gap Analysis."""
    return [o for o in all_objectives() if o.get("measured_by") and o.get("status") == "active"]


def unmeasurable() -> list[dict]:
    """Objectives БЕЗ measured_by — источник работы «обеспечить измеримость»."""
    return [o for o in all_objectives() if not o.get("measured_by") and o.get("status") == "active"]


def context_block() -> str:
    """Блок целей для промпта CEO (desired state — верх иерархии после Constitution/Owner)."""
    items = [o for o in all_objectives() if o.get("status") == "active"]
    if not items:
        return ""
    lines = []
    for o in sorted(items, key=lambda x: -x.get("priority", 50)):
        measured = f" (метрика: {o['measured_by']})" if o.get("measured_by") else " (пока НЕ измерима)"
        lines.append(f"- {o['title']}" + (f" → {o['desired']}" if o.get("desired") else "") + measured)
    return "\n=== ЦЕЛИ КОМПАНИИ (Objectives — desired state) ===\n" + "\n".join(lines) + "\n"


def reset() -> None:
    ctx.delete_file(_FILE)
