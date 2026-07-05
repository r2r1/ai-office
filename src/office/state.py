"""
История работы офиса (лента событий, агенты, результаты) — по тенанту.
Файл: data/tenants/<tid>/state.json. Переживает рестарт.
"""

import time
from datetime import datetime

from src.saas import context as ctx

_FILE = "state.json"
MAX_EVENTS = 800
# «speech» намеренно НЕ персистится: это самый частый тип (живая болтовня агентов),
# и запись его в историю переписывала весь state.json на каждое событие — блокирующий
# I/O в event-loop десятки раз в секунду. Живой поток speech идёт в SSE и в детальный
# trace (с временем); в постоянной истории он не нужен. Значимые вехи — ниже.
RECORD_TYPES = {"hired", "task_done", "system", "error", "connection_added", "connection_error"}


def _load() -> dict:
    return ctx.read_json(_FILE, {"events": [], "agents": {}, "results": {},
                                 "deliverables": [], "last_runs": {}})


def _save(d: dict) -> None:
    ctx.write_json(_FILE, d)


def record(event: dict) -> None:
    if event.get("type") not in RECORD_TYPES:
        return
    d = _load()
    d["events"].append(event)
    if len(d["events"]) > MAX_EVENTS:
        del d["events"][: len(d["events"]) - MAX_EVENTS]
    etype = event.get("type")
    if etype == "hired" and event.get("agent_id"):
        d["agents"][event["agent_id"]] = {
            "agent_id": event["agent_id"], "role": event.get("role", ""),
            "desk": event.get("desk", 0), "task": event.get("task", ""),
        }
    elif etype == "task_done" and event.get("agent_id"):
        d["results"][event["agent_id"]] = event.get("summary", "")
    _save(d)


def history() -> list[dict]:
    return list(_load()["events"])


def save_deliverable(agent_id: str, role: str, task: str, content: str) -> None:
    if not content or not content.strip():
        return
    from src.office import projects
    proj = projects.active()
    d = _load()
    d["deliverables"].append({"agent_id": agent_id, "role": role, "task": task,
                              "content": content.strip(), "ts": time.time(),
                              "time": datetime.now().strftime("%d.%m %H:%M"),
                              "project": proj["id"] if proj else ""})
    if len(d["deliverables"]) > 200:
        del d["deliverables"][: len(d["deliverables"]) - 200]
    _save(d)


def deliverables() -> list[dict]:
    return list(reversed(_load()["deliverables"]))


def deliverables_for(agent_id: str) -> list[dict]:
    return [d for d in reversed(_load()["deliverables"]) if d.get("agent_id") == agent_id]


def deliverables_for_project(project_id: str) -> list[dict]:
    """Артефакты КОНКРЕТНОГО Work (BOS §5) — для карточки проекта в UI, не
    общего котла на всю компанию. Записи без project (заведены раньше) —
    лениво привязываются к текущему активному, тот же приём, что sites.py."""
    from src.office import projects
    d = _load()
    changed = False
    pid = None
    for item in d["deliverables"]:
        if not item.get("project"):
            if pid is None:
                p = projects.active()
                pid = p["id"] if p else ""
            if pid:
                item["project"] = pid
                changed = True
    if changed:
        _save(d)
    return [x for x in reversed(d["deliverables"]) if x.get("project") == project_id]


def events_for(agent_id: str, limit: int = 30) -> list[dict]:
    return [e for e in _load()["events"] if e.get("agent_id") == agent_id][-limit:]


def saved_agents() -> list[dict]:
    return list(_load()["agents"].values())


def result_for(agent_id: str) -> str:
    return _load()["results"].get(agent_id, "")


def save_last_run(agent_id: str) -> None:
    d = _load()
    d["last_runs"][agent_id] = time.time()
    _save(d)


def last_run_for(agent_id: str) -> float:
    return _load()["last_runs"].get(agent_id, 0.0)


def load() -> None:
    pass


def reset() -> None:
    ctx.delete_file(_FILE)
