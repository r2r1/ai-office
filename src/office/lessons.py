"""
Память офиса между прогонами — «уроки» по ролям (per-tenant).

Каждый урок — короткий вывод «что сработало / чего избегать», извлечённый из
проверки результата (critic) или ошибки. Уроки подмешиваются в контекст будущих
задач той же роли, чтобы система не повторяла одни и те же грабли
(битые картинки, один index.html, ресёрч-циклы про Tilda и т.п.).

Хранилище: data/tenants/<tid>/lessons.json — {role: [ {text, ts}, ... ]}.
"""

import time

from src.saas import context as ctx

_FILE = "lessons.json"
_MAX_PER_ROLE = 12          # держим только последние уроки на роль
_MAX_INJECT = 5             # сколько подмешивать в контекст задачи


def _all() -> dict:
    return ctx.read_json(_FILE, {})


def add(role: str, text: str) -> None:
    """Сохраняет урок для роли (с дедупликацией по тексту)."""
    text = (text or "").strip()
    if not text or not role:
        return
    data = _all()
    items = data.setdefault(role, [])
    norm = text.lower()
    if any((it.get("text") or "").lower() == norm for it in items):
        return  # уже знаем этот урок
    items.append({"text": text[:300], "ts": time.time()})
    data[role] = items[-_MAX_PER_ROLE:]
    ctx.write_json(_FILE, data)


def for_role(role: str, limit: int = _MAX_INJECT) -> list[str]:
    """Последние уроки роли (для инъекции в задачу)."""
    items = _all().get(role, [])
    return [it.get("text", "") for it in items[-limit:] if it.get("text")]


def context_block(role: str) -> str:
    """Готовый блок уроков для системного/пользовательского промпта (или '')."""
    items = for_role(role)
    if not items:
        return ""
    lines = "\n".join(f"- {t}" for t in items)
    return ("\n=== УРОКИ ПРОШЛЫХ ЗАДАЧ (учитывай, не повторяй ошибок) ===\n"
            f"{lines}\n")


def all_lessons() -> dict:
    return _all()


def reset() -> None:
    ctx.delete_file(_FILE)
