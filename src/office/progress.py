"""
Прогресс офиса (линейные этапы) — по тенанту.
"""

from src.saas import context as ctx

_FILE = "progress.json"

STAGES = [
    "Бриф", "Исследование", "Стратегия", "Команда",
    "Развитие", "Результаты", "Масштаб",
]


def _state() -> dict:
    return ctx.read_json(_FILE, {"stage": 0, "note": ""})


def set_stage(stage: int, note: str = "") -> dict:
    st = _state()
    stage = max(0, min(stage, len(STAGES) - 1))
    if stage >= st["stage"]:
        st["stage"] = stage
    if note:
        st["note"] = note
    ctx.write_json(_FILE, st)
    return get()


def bump_to(stage: int, note: str = "") -> dict:
    return set_stage(stage, note)


def get() -> dict:
    st = _state()
    idx = st["stage"]
    return {
        "stage": idx, "label": STAGES[idx], "stages": STAGES,
        "percent": round(idx / (len(STAGES) - 1) * 100), "note": st["note"],
    }


def load() -> None:
    pass


def reset() -> None:
    ctx.delete_file(_FILE)
