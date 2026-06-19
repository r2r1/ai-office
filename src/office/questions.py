import asyncio
import time
import uuid

_pending: dict[str, asyncio.Future] = {}
_meta: dict[str, dict] = {}  # qid -> {text, agent_id, ts}

# Dedup index: normalized text -> qid of the existing pending question
# Multiple agents asking the same question share one future.
_by_text: dict[str, str] = {}


def _normalize(text: str) -> str:
    return " ".join(text.lower().strip().split())


def ask(question: str, publish_fn, agent_id: str = "") -> tuple[str, asyncio.Future]:
    """Returns (question_id, future). Await the future to get the user's answer.

    If an identical question is already pending, returns the existing (qid, future)
    so all agents waiting on the same info share one question card and one answer.
    """
    key = _normalize(question)
    existing_qid = _by_text.get(key)
    if existing_qid and existing_qid in _pending:
        # Attach another waiter to the same future via a wrapper future
        loop = asyncio.get_event_loop()
        proxy = loop.create_future()
        orig = _pending[existing_qid]

        def _forward(f):
            if not proxy.done():
                try:
                    proxy.set_result(f.result())
                except Exception as e:
                    proxy.set_exception(e)

        orig.add_done_callback(_forward)
        return existing_qid, proxy

    qid = str(uuid.uuid4())[:8]
    loop = asyncio.get_event_loop()
    fut = loop.create_future()
    _pending[qid] = fut
    _meta[qid] = {"text": question, "agent_id": agent_id, "ts": time.time()}
    _by_text[key] = qid
    return qid, fut


def answer(qid: str, answer: str) -> bool:
    """Called when user answers. Returns True if question existed."""
    fut = _pending.pop(qid, None)
    meta = _meta.pop(qid, None)
    if meta:
        key = _normalize(meta.get("text", ""))
        _by_text.pop(key, None)
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
