"""
Постоянная память офиса — ответы пользователя на вопросы агентов (по тенанту).
"""

import time

from src.saas import context as ctx

_FILE = "memory.json"


def _all() -> list[dict]:
    return ctx.read_json(_FILE, [])


def remember(question: str, answer: str) -> None:
    if not answer.strip():
        return
    entries = _all()
    entries.append({"question": question, "answer": answer, "ts": time.time()})
    ctx.write_json(_FILE, entries)


def lookup(question: str) -> str:
    q_words = set(question.lower().split())
    best_score, best_answer = 0.0, ""
    for entry in _all():
        e_words = set(entry["question"].lower().split())
        if not e_words:
            continue
        overlap = len(q_words & e_words) / max(len(q_words), len(e_words))
        if overlap > 0.5 and overlap > best_score:
            best_score, best_answer = overlap, entry["answer"]
    return best_answer


def all_entries() -> list[dict]:
    return list(reversed(_all()))


def context_block() -> str:
    entries = _all()
    if not entries:
        return ""
    lines = [f"В: {e['question']}\nО: {e['answer']}" for e in entries[-8:]]
    return "\n\n=== ОТВЕТЫ ПОЛЬЗОВАТЕЛЯ ===\n" + "\n---\n".join(lines)


def load() -> None:
    pass


def reset() -> None:
    ctx.delete_file(_FILE)
