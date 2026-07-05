"""
Projects — единица работы крупнее задачи (BOS §1, §4): цель + план + артефакты +
метрики, оставленные после себя. Сущность между компанией и план-графом.

Раньше plan.json был плоской доской ОДНОГО engagement'а: «сделали лендинг, теперь
бот» — либо дозапись в тот же граф, либо reset, история смешивалась. Теперь задачи
принадлежат проекту, компания ведёт их историю, а «работа выполнена» — это
закрытие ПРОЕКТА с фиксацией того, что он оставил после себя (сайты, лиды,
метрики) — принцип BOS «каждый проект оставляет после себя измеримость».

v1: один активный проект в момент времени (MAX_PER_ROLE-логика для работ);
параллельные проекты — после выноса живости из памяти процесса (BOS §10).

Хранилище: data/tenants/<tid>/projects.json — {"items": [...]}.
"""

import time

from src.saas import context as ctx

_FILE = "projects.json"


def _data() -> dict:
    return ctx.read_json(_FILE, {"items": []})


def _save(d: dict) -> None:
    ctx.write_json(_FILE, d)


def all_projects() -> list[dict]:
    return list(_data().get("items", []))


def get(pid: str) -> dict | None:
    for p in all_projects():
        if p["id"] == pid:
            return dict(p)
    return None


def active() -> dict | None:
    """Текущий активный проект (v1 — максимум один)."""
    for p in all_projects():
        if p.get("status") == "active":
            return dict(p)
    return None


def create(title: str, goal: str = "", type: str = "project") -> dict:
    """Создаёт Work и делает его активным (прежний активный закрывается как done —
    v1 не ведёт два активных Work параллельно, см. BOS §5/§14 п.6).

    `type` — project (разовое, есть конец) | process (никогда не завершается сам,
    v1 пока не реализует Instance-поток — заводится как задел на будущее) |
    initiative (идея до решения). Сегодня вся созданная работа фактически ведётся
    как project; поле подготавливает данные к разделению, не меняя раннее поведение."""
    d = _data()
    items = d.get("items", [])
    for p in items:
        if p.get("status") == "active":
            p["status"] = "done"
            p["closed_ts"] = time.time()
    pid = f"p{len(items) + 1}_{int(time.time()) % 100000}"
    proj = {
        "id": pid, "title": (title or "Проект").strip()[:160],
        "goal": (goal or "").strip()[:300],
        "type": type if type in ("project", "process", "initiative") else "project",
        "status": "active",
        "created_ts": time.time(), "closed_ts": None,
        "left_behind": {},   # что проект оставил после себя (заполняется при закрытии)
    }
    items.append(proj)
    d["items"] = items
    _save(d)
    return proj


def ensure_active() -> dict:
    """Активный проект или новый из цели брифа. Единая точка: задачи всегда
    принадлежат какому-то проекту."""
    cur = active()
    if cur:
        return cur
    from src.office import brief
    goal = brief.effective_goal()
    return create(goal[:80] or "Первый проект", goal)


def rename(pid: str, title: str) -> None:
    """Переименовывает проект (BOS §3: Gap создаёт Work, а не голую задачу — если под
    разрыв только что был авто-создан пустой активный проект вместо конкретной цели,
    его название должно отражать разрыв, а не общий бриф-заголовок). Вызывающий сам
    решает, когда переименование уместно (см. gap.replan)."""
    d = _data()
    for p in d.get("items", []):
        if p["id"] == pid:
            p["title"] = (title or p["title"]).strip()[:160]
            _save(d)
            return


def close(pid: str = "", note: str = "") -> dict | None:
    """Закрывает проект, фиксируя «что оставил после себя»: прогресс плана, сайты,
    лиды, срез мира (Measurement-петля будет сравнивать эти срезы)."""
    from src.office import plan, sites, leads, world
    d = _data()
    target = None
    for p in d.get("items", []):
        if (pid and p["id"] == pid) or (not pid and p.get("status") == "active"):
            target = p
            break
    if not target:
        return None
    prog = plan.progress()
    target["status"] = "done"
    target["closed_ts"] = time.time()
    target["note"] = (note or "")[:300]
    target["left_behind"] = {
        "tasks_done": prog.get("done", 0),
        "tasks_total": prog.get("total", 0),
        "sites": [s.get("slug", "") for s in sites.all_sites()],
        "leads_count": leads.count(),
    }
    _save(d)
    world.save_snapshot(f"project_closed:{target['id']}")
    return dict(target)


def context_block() -> str:
    """Блок проектов для промпта CEO: активный + краткая история."""
    items = all_projects()
    if not items:
        return ""
    lines = []
    for p in items[-5:]:
        mark = "🟢" if p.get("status") == "active" else "✅"
        left = p.get("left_behind") or {}
        tail = (f" (сдано {left.get('tasks_done', 0)} задач, лидов: {left.get('leads_count', 0)})"
                if p.get("status") == "done" and left else "")
        lines.append(f"{mark} {p['title']}{tail}")
    return "\n=== ПРОЕКТЫ КОМПАНИИ ===\n" + "\n".join(lines) + "\n"


def reset() -> None:
    ctx.delete_file(_FILE)
