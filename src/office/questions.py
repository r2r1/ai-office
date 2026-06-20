"""
Блокирующие вопросы агентов пользователю — по тенанту.

Futures живут в памяти (на время ожидания ответа), сгруппированы по tenant_id.
Дедуп одинаковых вопросов в пределах тенанта: общий future.
"""

import asyncio
import time
import uuid
from collections import defaultdict

from src.saas import context as ctx

_pending: dict[str, dict[str, asyncio.Future]] = defaultdict(dict)
_meta: dict[str, dict[str, dict]] = defaultdict(dict)
_by_text: dict[str, dict[str, str]] = defaultdict(dict)


def _normalize(text: str) -> str:
    return " ".join(text.lower().strip().split())


def ask(question: str, publish_fn=None, agent_id: str = "") -> tuple[str, asyncio.Future]:
    tid = ctx.get_tenant()
    pend, meta, by_text = _pending[tid], _meta[tid], _by_text[tid]
    key = _normalize(question)
    existing_qid = by_text.get(key)
    if existing_qid and existing_qid in pend:
        loop = asyncio.get_event_loop()
        proxy = loop.create_future()
        orig = pend[existing_qid]

        def _forward(f):
            if not proxy.done():
                try:
                    proxy.set_result(f.result())
                except Exception as e:
                    proxy.set_exception(e)

        orig.add_done_callback(_forward)
        return existing_qid, proxy

    qid = str(uuid.uuid4())[:8]
    fut = asyncio.get_event_loop().create_future()
    pend[qid] = fut
    meta[qid] = {"text": question, "agent_id": agent_id, "ts": time.time()}
    by_text[key] = qid
    return qid, fut


def answer(qid: str, answer: str) -> bool:
    tid = ctx.get_tenant()
    fut = _pending[tid].pop(qid, None)
    meta = _meta[tid].pop(qid, None)
    if meta:
        _by_text[tid].pop(_normalize(meta.get("text", "")), None)
    if fut and not fut.done():
        fut.set_result(answer)
        return True
    return False


def pending_for(agent_id: str) -> str:
    meta = _meta[ctx.get_tenant()]
    cands = [(m["ts"], qid) for qid, m in meta.items() if m.get("agent_id") == agent_id]
    if not cands:
        return ""
    cands.sort()
    return cands[-1][1]


def list_pending() -> list[dict]:
    meta = _meta[ctx.get_tenant()]
    return sorted([{"question_id": qid, **m} for qid, m in meta.items()], key=lambda x: x["ts"])
