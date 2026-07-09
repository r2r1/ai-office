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


def _similar_active(title: str, role: str, project_id: str) -> dict | None:
    """Уже есть активный процесс той же роли/проекта с похожим названием?
    Тот же приём, что initiatives.has_pending_similar (word-overlap > 50%).
    Реальный кейс из лога прогона 2026-07-09: salesman завёл ПЯТЬ отдельных
    процессов с названием "Лидогенерация и продажи внедрения ИИ-агентов" за
    один прогон (proc1..proc5) — каждый тикал каждый цикл независимо, впустую
    тратя бюджет на переписывание одного и того же docs/outreach.md."""
    words_new = set((title or "").lower().split())
    if not words_new:
        return None
    for p in _all():
        if p.get("status") != "active" or p.get("role") != role:
            continue
        if p.get("project_id", "") != (project_id or ""):
            continue
        words_old = set((p.get("title") or "").lower().split())
        if not words_old:
            continue
        overlap = len(words_new & words_old) / max(len(words_new), len(words_old), 1)
        if overlap > 0.5:
            return dict(p)
    return None


def create(title: str, role: str, instruction: str, cadence: str = "every_cycle",
           project_id: str = "") -> dict:
    """`project_id` — если процесс родился ВНУТРИ конкретного проекта (например
    агент сам завёл его через create_recurring_process, чтобы периодически
    запускать скрипт, который он же написал), задачи этого процесса ВСЕГДА
    попадают в ТОТ ЖЕ проект/workspace — иначе tick() отдавал их в "первый
    активный" проект (projects.ensure_active()), и при нескольких параллельных
    проектах задача могла уйти в ЧУЖОЙ workspace, где написанного скрипта
    просто нет (реальный кейс: t1.py лежал в проекте p4, а задача процесса
    "запусти t1.py" досталась воркеру проекта p3 — тот не находил файл).
    Пусто — прежнее поведение (компания-wide процесс, заведённый вручную из UI
    вне контекста конкретного проекта).

    Дедуп: похожий АКТИВНЫЙ процесс той же роли/проекта — возвращает его вместо
    создания нового (помечен `_deduped=True`, чтобы вызывающий код мог сказать
    агенту «уже есть», а не тихо расплодить дубли, см. _similar_active)."""
    existing = _similar_active(title, role, project_id)
    if existing:
        return {**existing, "_deduped": True}
    items = _all()
    proc = {
        "id": f"proc{len(items) + 1}_{int(time.time()) % 100000}",
        "title": (title or "").strip()[:160],
        "role": (role or "").strip(),
        "instruction": (instruction or "").strip()[:500],
        "cadence": cadence if cadence in CADENCES else "every_cycle",
        "status": "active",  # active | paused
        "project_id": project_id or "",
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
            requested_by=tag, project_id=p.get("project_id", ""),
        )
        _mark_run(p["id"])
        created.append(task)
    return created


def reset() -> None:
    ctx.delete_file(_FILE)
