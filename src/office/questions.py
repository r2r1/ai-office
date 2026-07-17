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

# Журнал КАЖДОГО вопроса (не только висящих — _meta теряет запись при answer()).
# Нужен для программных гейтов приёмки (acceptance.py): «эта роль обязана была
# спросить владельца перед сдачей» — по факту вызова, а не по тексту в skill.md,
# который LLM вольна проигнорировать (реальный кейс: designer ни разу за прогон
# не вызвал ask_user, хотя brand_book.md явно требует). Живёт только в памяти
# процесса — этого достаточно, приёмка проверяется в рамках того же запуска.
_asked_log: dict[str, list[dict]] = defaultdict(list)


def _normalize(text: str) -> str:
    return " ".join(text.lower().strip().split())


_STOPQ = {"и", "в", "на", "с", "по", "для", "что", "как", "это", "ли", "у", "о",
          "the", "a", "to", "of", "is", "do", "you", "мне", "нужно", "надо"}


def _q_tokens(text: str) -> set[str]:
    words = "".join(c.lower() if c.isalnum() else " " for c in (text or "")).split()
    return {w for w in words if len(w) > 2 and w not in _STOPQ}


def _find_similar(pend: dict, meta: dict, question: str) -> str:
    """
    id уже висящего вопроса, БЛИЗКОГО по смыслу (перекрытие ключевых слов ≥ 0.6),
    или ''. Раньше дедуп был только по точному тексту — два агента, спросившие одно
    и то же разными словами, плодили два блокирующих вопроса клиенту (B6).
    """
    qt = _q_tokens(question)
    if not qt:
        return ""
    for qid, m in meta.items():
        if qid not in pend:
            continue
        ot = _q_tokens(m.get("text", ""))
        if not ot:
            continue
        jacc = len(qt & ot) / len(qt | ot)
        if jacc >= 0.6:
            return qid
    return ""


def ask(question: str, publish_fn=None, agent_id: str = "") -> tuple[str, asyncio.Future]:
    tid = ctx.get_tenant()
    pend, meta, by_text = _pending[tid], _meta[tid], _by_text[tid]
    key = _normalize(question)
    existing_qid = by_text.get(key) or _find_similar(pend, meta, question)
    if existing_qid and existing_qid in pend:
        loop = asyncio.get_running_loop()
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
    fut = asyncio.get_running_loop().create_future()
    pend[qid] = fut
    ts = time.time()
    meta[qid] = {"text": question, "agent_id": agent_id, "ts": ts}
    by_text[key] = qid
    _asked_log[tid].append({"agent_id": agent_id, "text": question, "ts": ts})
    return qid, fut


def asked_since(agent_id: str, ts: float = 0.0) -> bool:
    """Спрашивал ли этот агент владельца (ask_user) начиная с момента ts.
    Для программных гейтов приёмки — см. acceptance.py."""
    if not agent_id:
        return False
    return any(e["agent_id"] == agent_id and e["ts"] >= ts
               for e in _asked_log[ctx.get_tenant()])


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
