import asyncio
import uuid

_pending: dict[str, asyncio.Future] = {}

def ask(question: str, publish_fn) -> tuple[str, asyncio.Future]:
    """Returns (question_id, future). Await the future to get the user's answer."""
    qid = str(uuid.uuid4())[:8]
    loop = asyncio.get_event_loop()
    fut = loop.create_future()
    _pending[qid] = fut
    return qid, fut

def answer(qid: str, answer: str) -> bool:
    """Called when user answers. Returns True if question existed."""
    fut = _pending.pop(qid, None)
    if fut and not fut.done():
        fut.set_result(answer)
        return True
    return False
