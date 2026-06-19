"""
Постоянная память офиса — хранит ответы пользователя на вопросы агентов.

Агенты могут прочитать память перед тем, как задавать вопрос — так они
не будут спрашивать одно и то же дважды.

Пишется в reports/memory.json.
"""

import json
import time
from pathlib import Path

MEMORY_FILE = Path("reports/memory.json")

# keyword -> {"question": str, "answer": str, "ts": float}
_entries: list[dict] = []


def remember(question: str, answer: str) -> None:
    """Сохраняет пару вопрос-ответ в память."""
    if not answer.strip():
        return
    _entries.append({"question": question, "answer": answer, "ts": time.time()})
    _save()


def lookup(question: str) -> str:
    """
    Ищет похожий уже отвеченный вопрос.
    Возвращает ответ если нашёл, иначе пустую строку.
    Простой поиск по пересечению слов.
    """
    q_words = set(question.lower().split())
    best_score = 0
    best_answer = ""
    for entry in _entries:
        e_words = set(entry["question"].lower().split())
        if not e_words:
            continue
        overlap = len(q_words & e_words) / max(len(q_words), len(e_words))
        if overlap > 0.5 and overlap > best_score:
            best_score = overlap
            best_answer = entry["answer"]
    return best_answer


def all_entries() -> list[dict]:
    """Полный список Q&A — для отображения в интерфейсе и вставки в контекст агента."""
    return list(reversed(_entries))


def context_block() -> str:
    """Формирует блок для системного промпта агента со всеми известными ответами."""
    if not _entries:
        return ""
    lines = []
    for e in _entries[-30:]:  # последние 30, чтобы не перегружать контекст
        lines.append(f"В: {e['question']}\nО: {e['answer']}")
    return "\n\n=== ОТВЕТЫ ПОЛЬЗОВАТЕЛЯ (не спрашивай повторно) ===\n" + "\n---\n".join(lines)


def reset() -> None:
    global _entries
    _entries = []
    if MEMORY_FILE.exists():
        MEMORY_FILE.unlink()


def load() -> None:
    global _entries
    if MEMORY_FILE.exists():
        try:
            _entries = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            _entries = []


def _save() -> None:
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_FILE.write_text(json.dumps(_entries, ensure_ascii=False, indent=2), encoding="utf-8")
