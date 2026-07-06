"""
Processes — BOS §5: Work, который никогда не завершается сам по себе. Раньше
единственным примером был поток Instance (продажи, `process_instances.py`) —
но Process это ЛЮБОЕ повторяющееся действие или цикл действий, необязательно
конвейер с карточками: «контент-завод — пост каждый цикл», «ежедневная
аналитика рынка». Это второй вид Process — recurring action, а не Instance-поток.

Каданс v1 — только `every_cycle`: процесс проверяется каждый цикл офиса
(LOOP_INTERVAL_SECONDS) и получает новую задачу, как только предыдущая закрыта
(done/skipped) — тот же дедуп-приём, что gap.replan(). Время суток (07:00) —
следующий шаг, когда появится реальная потребность в точном расписании.

Хранилище: data/tenants/<tid>/processes.json — {"items": [...]} (тот же формат,
что objectives.json). Раньше здесь был голый список `[...]`, а не `{"items": []}`,
как у objectives.json/plan.json — расхождение формы одинаковых по духу сущностей
без единого контракта: рефакторинг, трогающий оба модуля по аналогии, мог тихо
всё сломать (`list.get()` не существует, но копипаста кода чтения одного файла
для другого падает не сразу, а только на реальных данных тенанта в проде).
"""

import time

from src.saas import context as ctx

_FILE = "processes.json"

CADENCES = ("every_cycle",)


def _all() -> list[dict]:
    d = ctx.read_json(_FILE, {"items": []})
    if isinstance(d, list):
        return d  # старый формат (голый список) — читаем как есть, без падения
    return list(d.get("items", []))


def _save(items: list[dict]) -> None:
    ctx.write_json(_FILE, {"items": items})


def create(title: str, role: str, instruction: str, cadence: str = "every_cycle") -> dict:
    items = _all()
    proc = {
        "id": f"proc{len(items) + 1}_{int(time.time()) % 100000}",
        "title": (title or "").strip()[:160],
        "role": (role or "").strip(),
        "instruction": (instruction or "").strip()[:500],
        "cadence": cadence if cadence in CADENCES else "every_cycle",
        "status": "active",  # active | paused
        "created_ts": time.time(),
        "last_run_ts": None,
        "run_count": 0,
    }
    items.append(proc)
    _save(items)
    return proc


def all_processes() -> list[dict]:
    return list(_all())


def get(pid: str) -> dict | None:
    for p in _all():
        if p["id"] == pid:
            return dict(p)
    return None


def set_status(pid: str, status: str) -> dict | None:
    if status not in ("active", "paused"):
        return None
    items = _all()
    for p in items:
        if p["id"] == pid:
            p["status"] = status
            _save(items)
            return dict(p)
    return None


def delete(pid: str) -> bool:
    items = _all()
    filtered = [p for p in items if p["id"] != pid]
    changed = len(filtered) != len(items)
    if changed:
        _save(filtered)
    return changed


def _mark_run(pid: str) -> None:
    items = _all()
    for p in items:
        if p["id"] == pid:
            p["last_run_ts"] = time.time()
            p["run_count"] = p.get("run_count", 0) + 1
            break
    _save(items)


def tick() -> list[dict]:
    """Раз в цикл офиса: для каждого активного процесса, чья предыдущая задача
    уже закрыта, создаёт новую. Дедуп по requested_by=`process:<id>` смотрит
    только на pending/in_progress — тот же приём, что gap.replan() (см.
    src/office/gap.py): иначе процесс либо не запустился бы повторно после
    первой задачи, либо заспамил бы доску одинаковыми задачами каждый цикл."""
    from src.office import plan
    created = []
    active_tags = {t.get("requested_by", "") for t in plan.all_tasks()
                   if t.get("status") in ("pending", "in_progress")}
    for p in _all():
        if p.get("status") != "active":
            continue
        tag = f"process:{p['id']}"
        if tag in active_tags:
            continue
        title = p.get("instruction") or p["title"]
        task = plan.add_task(
            title, p.get("role", ""),
            f"Повторяющаяся задача процесса «{p['title']}» выполнена",
            requested_by=tag,
        )
        _mark_run(p["id"])
        created.append(task)
    return created


def reset() -> None:
    ctx.delete_file(_FILE)
