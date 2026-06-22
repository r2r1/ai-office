"""
План-граф задач — машинночитаемый список задач компании (per-tenant).

В отличие от текстовой стратегии/ТЗ (по которым агенты «додумывают»), это структура:
задача = {id, title, role, department, deps, status, done_criterion}. Лидер берёт из
графа СЛЕДУЮЩУЮ готовую к работе задачу своего отдела (зависимости выполнены) — это
убирает дубли, делает прогресс измеримым, а «готово» проверяемым.

Хранилище: data/tenants/<tid>/plan.json — {tasks: [...], generated: bool}.
"""

import time

from src.saas import context as ctx
from src.office import org

_FILE = "plan.json"

# Роль → отдел (для маршрутизации задач лидерам)
_ROLE_DEPT = {
    "developer": "tech", "designer": "tech", "integrator": "tech", "architect": "tech",
    "marketer": "marketing", "salesman": "sales",
}


def _data() -> dict:
    return ctx.read_json(_FILE, {"tasks": [], "generated": False})


def _save(d: dict) -> None:
    ctx.write_json(_FILE, d)


def is_generated() -> bool:
    return bool(_data().get("generated"))


def set_tasks(tasks: list[dict]) -> None:
    """Сохраняет сгенерированный граф задач (нормализует поля)."""
    norm = []
    for i, t in enumerate(tasks):
        role = (t.get("role") or "").strip()
        tid = (t.get("id") or f"t{i+1}").strip()
        norm.append({
            "id": tid,
            "title": (t.get("title") or "").strip()[:200],
            "role": role,
            "department": _ROLE_DEPT.get(role, ""),
            "deps": [d for d in (t.get("deps") or []) if d],
            "done_criterion": (t.get("done_criterion") or "").strip()[:200],
            "status": "pending",
        })
    _save({"tasks": norm, "generated": True})


def all_tasks() -> list[dict]:
    return list(_data().get("tasks", []))


def _done_ids() -> set:
    return {t["id"] for t in all_tasks() if t.get("status") == "done"}


def departments_needed() -> list[str]:
    """Какие отделы нужны для невыполненных задач (для CEO — открыть параллельно)."""
    done = _done_ids()
    deps = set()
    for t in all_tasks():
        if t.get("status") != "done" and t.get("department") and t["id"] not in done:
            deps.add(t["department"])
    return sorted(deps)


def ready_for_department(dept_id: str) -> list[dict]:
    """Все готовые к работе задачи отдела (зависимости выполнены, ещё не сделаны)."""
    done = _done_ids()
    roles = set(org.member_roles(dept_id))
    out = []
    for t in all_tasks():
        if t.get("status") != "pending":
            continue
        if t.get("department") != dept_id and t.get("role") not in roles:
            continue
        if all(dep in done for dep in t.get("deps", [])):
            out.append(dict(t))
    return out


def next_for_department(dept_id: str) -> dict | None:
    """Первая готовая к работе задача отдела (или None)."""
    ready = ready_for_department(dept_id)
    return ready[0] if ready else None


def mark(task_id: str, status: str) -> None:
    d = _data()
    for t in d.get("tasks", []):
        if t["id"] == task_id:
            t["status"] = status
            t["updated_ts"] = time.time()
            break
    _save(d)


def mark_done_by_role(role: str) -> str | None:
    """
    Помечает выполненной первую задачу роли в работе/ожидании. Возвращает её id.
    Используется когда работник сдал результат и прошёл критика.
    """
    d = _data()
    done = {t["id"] for t in d.get("tasks", []) if t.get("status") == "done"}
    for t in d.get("tasks", []):
        if t.get("role") == role and t.get("status") in ("pending", "in_progress") \
                and all(dep in done for dep in t.get("deps", [])):
            t["status"] = "done"
            t["updated_ts"] = time.time()
            _save(d)
            return t["id"]
    return None


def progress() -> dict:
    tasks = all_tasks()
    total = len(tasks)
    done = sum(1 for t in tasks if t.get("status") == "done")
    return {"total": total, "done": done,
            "percent": round(done / total * 100) if total else 0}


def reset() -> None:
    ctx.delete_file(_FILE)
