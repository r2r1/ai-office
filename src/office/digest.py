"""
Morning Digest — что офис сделал пока тебя не было.

Хранит метку времени последнего визита (data/tenants/<tid>/digest.json).
GET /api/digest → события с последнего визита → обновляет метку.
"""

import time
from datetime import datetime

from src.saas import context as ctx

_FILE = "digest.json"
_LAST_FILE = "last_digest.json"

# Читай-мутируй-пиши без блокировки: два почти одновременных вызова (два
# открытых таба одного тенанта) видят один и тот же старый last_seen и оба
# строят/показывают ОДИН И ТОТ ЖЕ дайджест (production-readiness worklist
# п.27). Полноценный лок непропорционален риску (дубль всплывашки, не потеря
# данных) — вместо этого маленький in-memory дебаунс: повторный вызов В ТЕЧЕНИЕ
# нескольких секунд после первого для ТОГО ЖЕ тенанта получает пустой дайджест.
_DEBOUNCE_SECS = 5.0
_last_call: dict[str, float] = {}


def _load() -> dict:
    return ctx.read_json(_FILE, {"last_seen": 0})


def _save(d: dict) -> None:
    ctx.write_json(_FILE, d)


def get_and_mark_seen() -> dict:
    """Возвращает дайджест с момента последнего визита, обновляет метку."""
    tid = ctx.get_tenant()
    now = time.time()
    prev_call = _last_call.get(tid, 0.0)
    if now - prev_call < _DEBOUNCE_SECS:
        return {"items": [], "count": 0, "since": "", "is_first": False}
    _last_call[tid] = now

    d = _load()
    last_seen = d.get("last_seen", 0)

    digest = _build(last_seen)
    d["last_seen"] = now
    _save(d)
    if digest.get("count"):
        # Сохраняем последний НЕПУСТОЙ дайджест отдельно от точки last_seen
        # (round2 audit, U3): сам факт этого вызова необратимо продвигает
        # last_seen — если попап закроется случайно (клик мимо, рефреш
        # посреди чтения, F5 в пути) ДО того, как пользователь его прочитал,
        # раньше контент терялся навсегда без единого способа его вернуть.
        ctx.write_json(_LAST_FILE, digest)
    return digest


def peek_last() -> dict:
    """Последний собранный непустой дайджест — открыть повторно, НЕ трогая
    last_seen и не потребляя новое окно (см. get_and_mark_seen)."""
    return ctx.read_json(_LAST_FILE, {"items": [], "count": 0, "since": "", "is_first": False})


def _fmt_ago(ts: float) -> str:
    """Человекочитаемое 'X минут назад' / 'X часов назад'."""
    diff = time.time() - ts
    if diff < 60:
        return "только что"
    if diff < 3600:
        return f"{int(diff // 60)} мин назад"
    if diff < 86400:
        return f"{int(diff // 3600)} ч назад"
    return f"{int(diff // 86400)} д назад"


def _build(last_seen: float) -> dict:
    from src.office import state, workspace, milestones as ms_module, plan as plan_module

    items: list[dict] = []
    # last_seen=0 значит «первый визит» — тогда показываем всё как есть (нечего
    # «с прошлого раза» показывать). Иначе фильтруем каждый источник по своей
    # временной метке: раньше этот параметр принимался, но НИГДЕ не использовался
    # для фильтрации — дайджест «что было пока вас не было» на самом деле каждый
    # раз показывал вообще всё, что офис сделал с начала работы.

    # --- Выполненные задачи плана ---
    for t in plan_module.all_tasks():
        if t.get("status") == "done" and t.get("updated_ts", 0) > last_seen:
            items.append({"kind": "task", "icon": "✅",
                          "text": t.get("title", "Задача выполнена")[:120]})

    # --- Новые результаты агентов (deliverables) ---
    for d in state.deliverables():
        if d.get("ts", 0) <= last_seen:
            continue
        items.append({"kind": "deliverable", "icon": "📄",
                      "text": f"{d.get('role','?')}: {d.get('task','')[:80]}"})
        if len(items) >= 10:
            break

    # --- Файлы в workspace ---
    files = [f for f in workspace.list_files() if f.get("mtime", 0) > last_seen]
    code_files = [f for f in files if not f["path"].startswith("docs/")]
    if code_files:
        names = ", ".join(f["path"] for f in code_files[:4])
        if len(code_files) > 4:
            names += f" и ещё {len(code_files) - 4}"
        items.append({"kind": "code", "icon": "💻", "text": f"Написан код: {names}"})

    doc_files = [f for f in files if f["path"].startswith("docs/")]
    if doc_files:
        names = ", ".join(f["path"] for f in doc_files[:3])
        items.append({"kind": "docs", "icon": "📋", "text": f"Документы: {names}"})

    # --- Завершённые этапы ---
    for s in ms_module.all_stages():
        if s.get("status") == "done" and s.get("updated_ts", 0) > last_seen:
            items.append({"kind": "milestone", "icon": "🎯",
                          "text": f"Этап завершён: {s.get('title','')[:80]}"})

    # Убираем дубликаты по тексту
    seen_texts: set[str] = set()
    unique: list[dict] = []
    for item in items:
        if item["text"] not in seen_texts:
            seen_texts.add(item["text"])
            unique.append(item)

    since_str = _fmt_ago(last_seen) if last_seen else "начала работы"

    return {
        "items": unique[:15],
        "count": len(unique),
        "since": since_str,
        "is_first": last_seen == 0,
    }
