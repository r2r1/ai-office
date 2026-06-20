"""
Персональные чаты пользователя с агентами (отображаемая переписка). По тенанту.
Вопросы агентов (ask_user) тоже попадают сюда как kind="question" с question_id.
"""

import time
import uuid

from src.saas import context as ctx

_FILE = "threads.json"
MAX_PER_THREAD = 100


def _all() -> dict:
    return ctx.read_json(_FILE, {})


def post(agent_id: str, sender: str, text: str, kind: str = "msg", question_id: str = "") -> dict:
    threads = _all()
    msg = {"id": uuid.uuid4().hex[:8], "from": sender, "text": (text or "").strip(),
           "ts": time.time(), "kind": kind, "question_id": question_id, "answered": False}
    thread = threads.setdefault(agent_id, [])
    thread.append(msg)
    if len(thread) > MAX_PER_THREAD:
        del thread[: len(thread) - MAX_PER_THREAD]
    ctx.write_json(_FILE, threads)
    return msg


def recent(agent_id: str, n: int = 100) -> list[dict]:
    return _all().get(agent_id, [])[-n:]


def mark_answered(question_id: str) -> None:
    if not question_id:
        return
    threads = _all()
    changed = False
    for thread in threads.values():
        for m in thread:
            if m.get("question_id") == question_id and not m.get("answered"):
                m["answered"] = True
                changed = True
    if changed:
        ctx.write_json(_FILE, threads)


def summaries() -> dict:
    out = {}
    for aid, thread in _all().items():
        if not thread:
            continue
        last = thread[-1]
        unanswered = sum(1 for m in thread if m.get("kind") == "question" and not m.get("answered"))
        out[aid] = {"last_text": last.get("text", ""), "last_ts": last.get("ts", 0),
                    "last_from": last.get("from", ""), "unanswered": unanswered}
    return out


def load() -> None:
    pass


def reset() -> None:
    ctx.delete_file(_FILE)
