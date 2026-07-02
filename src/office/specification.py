"""
Specification — формализованное понимание работы ДО исполнения (BOS §1, §8 L1).

Спецификация — контракт приёмки: что делаем (функции) и когда это считается
успехом (критерии). Источник чек-листа Acceptance-слоя. v1 собирается
ДЕТЕРМИНИРОВАННО из брифа и план-графа (без LLM и без блокировки офиса);
подтверждение владельцем — опциональное действие (POST /api/specification/confirm),
повышающее доверие к приёмке, а не ворота перед стартом.

Хранилище: data/tenants/<tid>/specification.json.
"""

import time

from src.saas import context as ctx

_FILE = "specification.json"


def get() -> dict:
    return ctx.read_json(_FILE, {})


def exists() -> bool:
    return bool(get().get("functions"))


def ensure() -> dict:
    """Собирает спецификацию из брифа + плана, если её ещё нет. Идемпотентно."""
    cur = get()
    if cur.get("functions"):
        return cur
    from src.office import brief, plan
    b = brief.get()
    tasks = plan.all_tasks()
    spec = {
        "goal": brief.effective_goal(),
        "niche": b.get("niche", ""),
        "audience": b.get("audience", ""),
        # Функции = что офис собирается сделать (из заголовков плана)
        "functions": [t.get("title", "")[:160] for t in tasks if t.get("title")],
        # Критерии успеха = проверяемые done_criterion задач (контракт приёмки)
        "success_criteria": [t["done_criterion"][:160] for t in tasks
                             if t.get("done_criterion")],
        "status": "draft",       # draft → confirmed (владелец подтвердил)
        "confirmed_note": "",
        "created_ts": time.time(),
    }
    ctx.write_json(_FILE, spec)
    return spec


def confirm(note: str = "") -> dict:
    """Владелец подтвердил спецификацию (Level 1 пройден явно)."""
    spec = get()
    if not spec:
        spec = ensure()
    spec["status"] = "confirmed"
    spec["confirmed_note"] = (note or "").strip()[:300]
    spec["confirmed_ts"] = time.time()
    ctx.write_json(_FILE, spec)
    return spec


def checklist() -> list[str]:
    """Критерии успеха для финальной приёмки engagement'а."""
    return list(get().get("success_criteria", []))


def context_block() -> str:
    """Блок спецификации для промптов (или '')."""
    spec = get()
    if not spec.get("functions"):
        return ""
    status = "подтверждена владельцем" if spec.get("status") == "confirmed" else "черновик"
    lines = [f"Статус: {status}"]
    if spec.get("success_criteria"):
        lines.append("Критерии успеха:")
        lines += [f"  ✓ {c}" for c in spec["success_criteria"][:8]]
    return "\n=== СПЕЦИФИКАЦИЯ РАБОТЫ (контракт приёмки) ===\n" + "\n".join(lines) + "\n"


def reset() -> None:
    ctx.delete_file(_FILE)
