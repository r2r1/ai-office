"""
Прогресс офиса — на каком этапе пути к цели находится бизнес.

Этапы линейные: от получения брифа до масштабирования. Текущий этап
показывается в дашборде индикатором прогресса. Сохраняется между перезапусками.
"""

import json
from pathlib import Path

PROGRESS_FILE = Path("reports/progress.json")

STAGES = [
    "Бриф",          # 0 — ждём/получили задачу клиента
    "Исследование",  # 1 — ресёрчер изучает рынок и тренды
    "Стратегия",     # 2 — стратег строит план
    "Команда",       # 3 — HR набирает специалистов
    "Развитие",      # 4 — агенты работают над задачами
    "Результаты",    # 5 — пошли первые готовые результаты
    "Масштаб",       # 6 — масштабирование к цели
]

_state = {"stage": 0, "note": ""}


def set_stage(stage: int, note: str = "") -> dict:
    """Устанавливает этап (не откатывает назад)."""
    stage = max(0, min(stage, len(STAGES) - 1))
    if stage >= _state["stage"]:
        _state["stage"] = stage
    if note:
        _state["note"] = note
    _save()
    return get()


def bump_to(stage: int, note: str = "") -> dict:
    return set_stage(stage, note)


def get() -> dict:
    idx = _state["stage"]
    return {
        "stage": idx,
        "label": STAGES[idx],
        "stages": STAGES,
        "percent": round(idx / (len(STAGES) - 1) * 100),
        "note": _state["note"],
    }


def _save() -> None:
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS_FILE.write_text(json.dumps(_state, ensure_ascii=False), encoding="utf-8")


def load() -> None:
    if PROGRESS_FILE.exists():
        try:
            d = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
            _state["stage"] = d.get("stage", 0)
            _state["note"] = d.get("note", "")
        except (json.JSONDecodeError, OSError):
            pass


def reset() -> None:
    _state["stage"] = 0
    _state["note"] = ""
    if PROGRESS_FILE.exists():
        PROGRESS_FILE.unlink()
