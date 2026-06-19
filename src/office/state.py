"""
Память офиса — сохраняет всю историю работы между перезапусками.

Чтобы при рестарте пользователь НЕ начинал с нуля: лента событий, нанятые
агенты и их результаты восстанавливаются из reports/state.json.
"""

import json
from pathlib import Path

STATE_FILE = Path("reports/state.json")
MAX_EVENTS = 800  # храним последние N событий, чтобы файл не рос бесконечно

# Какие события стоит запоминать в ленту истории
RECORD_TYPES = {"hired", "speech", "task_done", "system", "error"}

_events: list[dict] = []
_agents: dict[str, dict] = {}  # agent_id -> {agent_id, role, desk, task}
_results: dict[str, str] = {}  # agent_id -> последний результат (task_done summary)
_deliverables: list[dict] = []  # готовые результаты работы агентов (полный текст)


def record(event: dict) -> None:
    """Записывает значимое событие в историю и сохраняет на диск."""
    etype = event.get("type")
    if etype not in RECORD_TYPES:
        return

    _events.append(event)
    if len(_events) > MAX_EVENTS:
        del _events[: len(_events) - MAX_EVENTS]

    if etype == "hired" and event.get("agent_id"):
        _agents[event["agent_id"]] = {
            "agent_id": event["agent_id"],
            "role": event.get("role", ""),
            "desk": event.get("desk", 0),
            "task": event.get("task", ""),
        }
    elif etype == "task_done" and event.get("agent_id"):
        _results[event["agent_id"]] = event.get("summary", "")

    _save()


def history() -> list[dict]:
    return list(_events)


def save_deliverable(agent_id: str, role: str, task: str, content: str) -> None:
    """Сохраняет готовый результат работы агента (полный текст) для пользователя."""
    if not content or not content.strip():
        return
    from datetime import datetime
    _deliverables.append({
        "agent_id": agent_id,
        "role": role,
        "task": task,
        "content": content.strip(),
        "time": datetime.now().strftime("%d.%m %H:%M"),
    })
    if len(_deliverables) > 200:
        del _deliverables[: len(_deliverables) - 200]
    _save()


def deliverables() -> list[dict]:
    return list(reversed(_deliverables))  # новые сверху


def deliverables_for(agent_id: str) -> list[dict]:
    """Все готовые результаты конкретного агента, новые сверху."""
    return [d for d in reversed(_deliverables) if d.get("agent_id") == agent_id]


def events_for(agent_id: str, limit: int = 30) -> list[dict]:
    """Последние события конкретного агента (что делал/говорил)."""
    out = [e for e in _events if e.get("agent_id") == agent_id]
    return out[-limit:]


def saved_agents() -> list[dict]:
    return list(_agents.values())


def result_for(agent_id: str) -> str:
    return _results.get(agent_id, "")


def _save() -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {"events": _events, "agents": _agents, "results": _results, "deliverables": _deliverables}
    STATE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load() -> None:
    """Загружает историю при старте сервера."""
    global _events, _agents, _results, _deliverables
    if STATE_FILE.exists():
        try:
            d = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            _events = d.get("events", [])
            _agents = d.get("agents", {})
            _results = d.get("results", {})
            _deliverables = d.get("deliverables", [])
        except (json.JSONDecodeError, OSError):
            pass


def reset() -> None:
    global _events, _agents, _results, _deliverables
    _events = []
    _agents = {}
    _results = {}
    _deliverables = []
    if STATE_FILE.exists():
        STATE_FILE.unlink()
