"""
Этапы (вехи) пути офиса к цели — динамический прогресс-бар.

Сначала есть только базовые этапы (Запрос → Исследование → Стратегия).
После того как стратег построил план, оркестратор формирует РЕАЛЬНЫЕ этапы
развития бизнеса под конкретную цель клиента. По каждому этапу копится сводка
того, что уже сделано — пользователь может кликнуть на этап и посмотреть.

Хранится в reports/milestones.json, переживает перезапуски.
"""

import json
import time
from pathlib import Path

MILESTONES_FILE = Path("reports/milestones.json")

# Базовые этапы, которые есть всегда до построения стратегии
BASE_STAGES = [
    {"id": "intake", "title": "Запрос", "status": "pending", "summary": "", "items": []},
    {"id": "research", "title": "Исследование", "status": "pending", "summary": "", "items": []},
    {"id": "strategy", "title": "Стратегия", "status": "pending", "summary": "", "items": []},
]

# status: pending | active | done

_stages: list[dict] = []


def _ensure_base() -> None:
    """Гарантирует наличие базовых этапов в начале списка."""
    global _stages
    if not _stages:
        _stages = [dict(s) for s in BASE_STAGES]


def all_stages() -> list[dict]:
    _ensure_base()
    return [dict(s) for s in _stages]


def get(stage_id: str) -> dict | None:
    for s in _stages:
        if s["id"] == stage_id:
            return dict(s)
    return None


def set_status(stage_id: str, status: str) -> None:
    _ensure_base()
    for s in _stages:
        if s["id"] == stage_id:
            s["status"] = status
            break
    _save()


def mark_active(stage_id: str) -> None:
    """Делает этап активным, а все предыдущие — выполненными."""
    _ensure_base()
    found = False
    for s in _stages:
        if s["id"] == stage_id:
            s["status"] = "active"
            found = True
        elif not found:
            if s["status"] != "done":
                s["status"] = "done"
    _save()


def add_item(stage_id: str, text: str, agent_id: str = "", role: str = "") -> None:
    """Добавляет запись о проделанной работе к этапу + обновляет краткую сводку."""
    _ensure_base()
    for s in _stages:
        if s["id"] == stage_id:
            s["items"].append({
                "text": text.strip(),
                "agent_id": agent_id,
                "role": role,
                "ts": time.time(),
            })
            # держим максимум 40 записей на этап
            if len(s["items"]) > 40:
                s["items"] = s["items"][-40:]
            break
    _save()


def set_summary(stage_id: str, summary: str) -> None:
    _ensure_base()
    for s in _stages:
        if s["id"] == stage_id:
            s["summary"] = summary.strip()
            break
    _save()


def set_business_stages(stages: list[dict]) -> None:
    """
    Устанавливает реальные этапы развития бизнеса (после стратегии).
    stages = [{"id","title","summary"?}], добавляются ПОСЛЕ базовых трёх.
    Базовые этапы помечаются выполненными.
    """
    _ensure_base()
    base = [s for s in _stages if s["id"] in ("intake", "research", "strategy")]
    for b in base:
        b["status"] = "done"

    biz = []
    existing = {s["id"]: s for s in _stages}
    for i, st in enumerate(stages):
        sid = st.get("id") or f"stage_{i+1}"
        if sid in existing and existing[sid]["id"] not in ("intake", "research", "strategy"):
            # сохраняем накопленные items/summary при повторной установке
            prev = existing[sid]
            biz.append({
                "id": sid,
                "title": st.get("title", prev["title"]),
                "status": prev.get("status", "pending"),
                "summary": prev.get("summary", st.get("summary", "")),
                "items": prev.get("items", []),
            })
        else:
            biz.append({
                "id": sid,
                "title": st.get("title", f"Этап {i+1}"),
                "status": "pending",
                "summary": st.get("summary", ""),
                "items": [],
            })

    globals()["_stages"] = base + biz
    _save()


def has_business_stages() -> bool:
    _ensure_base()
    return any(s["id"] not in ("intake", "research", "strategy") for s in _stages)


def current_index() -> int:
    """Индекс активного этапа (или последнего выполненного)."""
    _ensure_base()
    active = [i for i, s in enumerate(_stages) if s["status"] == "active"]
    if active:
        return active[0]
    done = [i for i, s in enumerate(_stages) if s["status"] == "done"]
    return (done[-1] + 1) if done and done[-1] + 1 < len(_stages) else (done[-1] if done else 0)


def progress_payload() -> dict:
    """Данные для прогресс-бара во фронте."""
    _ensure_base()
    n = len(_stages)
    idx = current_index()
    done_count = len([s for s in _stages if s["status"] == "done"])
    percent = round(done_count / n * 100) if n else 0
    return {
        "stages": [
            {"id": s["id"], "title": s["title"], "status": s["status"],
             "summary": s["summary"], "item_count": len(s["items"])}
            for s in _stages
        ],
        "current": idx,
        "percent": percent,
    }


def _save() -> None:
    MILESTONES_FILE.parent.mkdir(parents=True, exist_ok=True)
    MILESTONES_FILE.write_text(json.dumps(_stages, ensure_ascii=False, indent=2), encoding="utf-8")


def load() -> None:
    global _stages
    if MILESTONES_FILE.exists():
        try:
            data = json.loads(MILESTONES_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list) and data:
                _stages = data
                return
        except (json.JSONDecodeError, OSError):
            pass
    _ensure_base()


def reset() -> None:
    global _stages
    _stages = [dict(s) for s in BASE_STAGES]
    if MILESTONES_FILE.exists():
        MILESTONES_FILE.unlink()
