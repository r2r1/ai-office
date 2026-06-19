import asyncio
import time
import uuid

_pending: dict[str, asyncio.Future] = {}
_meta: dict[str, dict] = {}  # qid -> {text, agent_id, ts}

def ask(question: str, publish_fn, agent_id: str = "") -> tuple[str, asyncio.Future]:
    """Returns (question_id, future). Await the future to get the user's answer."""
    qid = str(uuid.uuid4())[:8]
    loop = asyncio.get_event_loop()
    fut = loop.create_future()
    _pending[qid] = fut
    _meta[qid] = {"text": question, "agent_id": agent_id, "ts": time.time()}
    return qid, fut

def answer(qid: str, answer: str) -> bool:
    """Called when user answers. Returns True if question existed."""
    fut = _pending.pop(qid, None)
    _meta.pop(qid, None)
    if fut and not fut.done():
        fut.set_result(answer)
        return True
    return False

def list_pending() -> list[dict]:
    """Returns all unanswered questions, oldest first."""
    return sorted(
        [{"question_id": qid, **m} for qid, m in _meta.items()],
        key=lambda x: x["ts"],
    )
