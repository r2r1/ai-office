"""
Персональные чаты пользователя с агентами (отображаемая переписка).

В отличие от `chat.py` (там история в формате LLM role/content для контекста)
здесь хранится ОТОБРАЖАЕМАЯ лента сообщений: кто, когда, что написал, и был ли
это вопрос агента, ожидающий ответа. Эта лента — источник правды для вкладки
«Чаты». Вопросы агентов (`ask_user`) тоже попадают сюда как сообщения с
kind="question" и привязанным question_id.
"""

import json
import time
import uuid
from pathlib import Path

THREADS_FILE = Path("reports/threads.json")
MAX_PER_THREAD = 100

# agent_id -> [ {id, from, text, ts, kind, question_id, answered} ]
_threads: dict[str, list[dict]] = {}


def post(agent_id: str, sender: str, text: str, kind: str = "msg",
         question_id: str = "") -> dict:
    """Добавляет сообщение в тред агента. sender: 'user' | 'agent' | 'system'."""
    msg = {
        "id": uuid.uuid4().hex[:8],
        "from": sender,
        "text": (text or "").strip(),
        "ts": time.time(),
        "kind": kind,                 # 'msg' | 'question'
        "question_id": question_id,
        "answered": False,
    }
    thread = _threads.setdefault(agent_id, [])
    thread.append(msg)
    if len(thread) > MAX_PER_THREAD:
        del thread[: len(thread) - MAX_PER_THREAD]
    _persist()
    return msg


def recent(agent_id: str, n: int = 100) -> list[dict]:
    return list(_threads.get(agent_id, [])[-n:])


def mark_answered(question_id: str) -> None:
    """Помечает вопрос(ы) с этим question_id как отвеченные (во всех тредах)."""
    if not question_id:
        return
    changed = False
    for thread in _threads.values():
        for m in thread:
            if m.get("question_id") == question_id and not m.get("answered"):
                m["answered"] = True
                changed = True
    if changed:
        _persist()


def summaries() -> dict[str, dict]:
    """Для боковой панели: по треду — последнее сообщение и число открытых вопросов."""
    out: dict[str, dict] = {}
    for aid, thread in _threads.items():
        if not thread:
            continue
        last = thread[-1]
        unanswered = sum(1 for m in thread
                         if m.get("kind") == "question" and not m.get("answered"))
        out[aid] = {
            "last_text": last.get("text", ""),
            "last_ts": last.get("ts", 0),
            "last_from": last.get("from", ""),
            "unanswered": unanswered,
        }
    return out


def _persist() -> None:
    THREADS_FILE.parent.mkdir(parents=True, exist_ok=True)
    THREADS_FILE.write_text(json.dumps(_threads, ensure_ascii=False, indent=2),
                            encoding="utf-8")


def load() -> None:
    global _threads
    if THREADS_FILE.exists():
        try:
            data = json.loads(THREADS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                _threads = data
        except (json.JSONDecodeError, OSError):
            pass


def reset() -> None:
    global _threads
    _threads = {}
    if THREADS_FILE.exists():
        THREADS_FILE.unlink()
