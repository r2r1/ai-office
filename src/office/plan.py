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
            "assignee": "",        # agent_id исполнителя (когда взята в работу)
            "requested_by": "",    # кто поставил (CEO/план или коллега-агент)
        })
    _save({"tasks": norm, "generated": True})


def add_task(title: str, role: str, done_criterion: str = "",
             requested_by: str = "", deps: list[str] | None = None) -> dict:
    """
    Добавляет задачу в доску (например, поставленную КОЛЛЕГОЙ-агентом другому отделу/роли).
    Возвращает созданную задачу. Видна в to-do списке исполнителя и у его лидера.
    """
    d = _data()
    tasks = d.get("tasks", [])
    tid = f"t{len(tasks) + 1}_{int(time.time()) % 10000}"
    task = {
        "id": tid, "title": (title or "").strip()[:200], "role": (role or "").strip(),
        "department": _ROLE_DEPT.get((role or "").strip(), ""),
        "deps": [x for x in (deps or []) if x],
        "done_criterion": (done_criterion or "").strip()[:200],
        "status": "pending", "assignee": "", "requested_by": requested_by,
    }
    tasks.append(task)
    d["tasks"] = tasks
    d["generated"] = True  # доска становится активной даже если граф не строился
    _save(d)
    return task


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


def assign(task_id: str, agent_id: str) -> None:
    """Взять задачу в работу: статус in_progress + закрепить исполнителя."""
    d = _data()
    for t in d.get("tasks", []):
        if t["id"] == task_id:
            t["status"] = "in_progress"
            t["assignee"] = agent_id
            t["updated_ts"] = time.time()
            break
    _save(d)


def complete(task_id: str) -> None:
    mark(task_id, "done")


def revert(task_id: str) -> None:
    """Вернуть зависшую/упавшую задачу в очередь (in_progress → pending)."""
    d = _data()
    for t in d.get("tasks", []):
        if t["id"] == task_id and t.get("status") == "in_progress":
            t["status"] = "pending"
            t["assignee"] = ""
            t["updated_ts"] = time.time()
            break
    _save(d)


def for_agent(agent_id: str) -> list[dict]:
    """To-do список конкретного агента: его задачи + поставленные ему коллегами."""
    return [t for t in all_tasks()
            if t.get("assignee") == agent_id and t.get("status") != "done"]


def board(dept_id: str | None = None) -> dict:
    """Доска задач (todo/doing/done) — целиком или по отделу. Для отслеживания лидером/UI."""
    tasks = all_tasks()
    if dept_id:
        roles = set(org.member_roles(dept_id))
        tasks = [t for t in tasks if t.get("department") == dept_id or t.get("role") in roles]
    return {
        "todo": [t for t in tasks if t.get("status") == "pending"],
        "doing": [t for t in tasks if t.get("status") == "in_progress"],
        "done": [t for t in tasks if t.get("status") == "done"],
    }


def board_summary(dept_id: str | None = None) -> str:
    """Короткая сводка доски для лидера: «✓3 ⟳1 ☐2» + что в работе."""
    b = board(dept_id)
    doing = "; ".join(f"{t['id']}:{t['title'][:30]}" for t in b["doing"]) or "—"
    return f"✓{len(b['done'])} ⟳{len(b['doing'])} ☐{len(b['todo'])} | в работе: {doing}"


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
