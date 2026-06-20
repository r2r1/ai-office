"""
Этапы (вехи) пути офиса к цели — динамический прогресс-бар. По тенанту.
"""

from src.saas import context as ctx

_FILE = "milestones.json"

BASE_STAGES = [
    {"id": "intake", "title": "Запрос", "status": "pending", "summary": "", "items": []},
    {"id": "research", "title": "Исследование", "status": "pending", "summary": "", "items": []},
    {"id": "strategy", "title": "Стратегия", "status": "pending", "summary": "", "items": []},
]

_SYS = ("intake", "research", "strategy")


def _load() -> list[dict]:
    st = ctx.read_json(_FILE, None)
    if not st:
        st = [dict(s) for s in BASE_STAGES]
    return st


def _save(stages: list[dict]) -> None:
    ctx.write_json(_FILE, stages)


def all_stages() -> list[dict]:
    return [dict(s) for s in _load()]


def get(stage_id: str) -> dict | None:
    for s in _load():
        if s["id"] == stage_id:
            return dict(s)
    return None


def set_status(stage_id: str, status: str) -> None:
    st = _load()
    for s in st:
        if s["id"] == stage_id:
            s["status"] = status
            break
    _save(st)


def mark_active(stage_id: str) -> None:
    st = _load()
    found = False
    for s in st:
        if s["id"] == stage_id:
            s["status"] = "active"
            found = True
        elif not found and s["status"] != "done":
            s["status"] = "done"
    _save(st)


def add_item(stage_id: str, text: str, agent_id: str = "", role: str = "") -> None:
    import time
    st = _load()
    for s in st:
        if s["id"] == stage_id:
            s["items"].append({"text": text.strip(), "agent_id": agent_id, "role": role, "ts": time.time()})
            if len(s["items"]) > 40:
                s["items"] = s["items"][-40:]
            break
    _save(st)


def set_summary(stage_id: str, summary: str) -> None:
    st = _load()
    for s in st:
        if s["id"] == stage_id:
            s["summary"] = summary.strip()
            break
    _save(st)


def set_business_stages(stages: list[dict]) -> None:
    st = _load()
    base = [s for s in st if s["id"] in _SYS]
    for b in base:
        b["status"] = "done"
    existing = {s["id"]: s for s in st}
    biz = []
    for i, sd in enumerate(stages):
        sid = sd.get("id") or f"stage_{i+1}"
        if sid in existing and sid not in _SYS:
            prev = existing[sid]
            biz.append({"id": sid, "title": sd.get("title", prev["title"]),
                        "status": prev.get("status", "pending"),
                        "summary": prev.get("summary", sd.get("summary", "")),
                        "items": prev.get("items", [])})
        else:
            biz.append({"id": sid, "title": sd.get("title", f"Этап {i+1}"),
                        "status": "pending", "summary": sd.get("summary", ""), "items": []})
    _save(base + biz)


def has_business_stages() -> bool:
    return any(s["id"] not in _SYS for s in _load())


def all_business_done() -> bool:
    biz = [s for s in _load() if s["id"] not in _SYS]
    return bool(biz) and all(s["status"] == "done" for s in biz)


def current_index() -> int:
    st = _load()
    active = [i for i, s in enumerate(st) if s["status"] == "active"]
    if active:
        return active[0]
    done = [i for i, s in enumerate(st) if s["status"] == "done"]
    return (done[-1] + 1) if done and done[-1] + 1 < len(st) else (done[-1] if done else 0)


def progress_payload() -> dict:
    st = _load()
    n = len(st)
    done_count = len([s for s in st if s["status"] == "done"])
    return {
        "stages": [{"id": s["id"], "title": s["title"], "status": s["status"],
                    "summary": s["summary"], "item_count": len(s["items"])} for s in st],
        "current": current_index(),
        "percent": round(done_count / n * 100) if n else 0,
    }


def load() -> None:
    pass


def reset() -> None:
    ctx.delete_file(_FILE)
