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
_LIMIT_FILE = "project_limits.json"
DEFAULT_MAX_ACTIVE = 3


def _data() -> dict:
    return ctx.read_json(_FILE, {"items": []})


def _save(d: dict) -> None:
    ctx.write_json(_FILE, d)


def get_limit() -> int:
    """Сколько проектов офис ведёт ОДНОВРЕМЕННО (параллельные Work, не история).
    По умолчанию 3 — настраивается владельцем (см. set_limit), не хардкод без выхода."""
    d = ctx.read_json(_LIMIT_FILE, {})
    return max(1, int(d.get("max_active", DEFAULT_MAX_ACTIVE)))


def set_limit(n: int) -> None:
    ctx.write_json(_LIMIT_FILE, {"max_active": max(1, int(n))})


def all_projects() -> list[dict]:
    return list(_data().get("items", []))


def get(pid: str) -> dict | None:
    for p in all_projects():
        if p["id"] == pid:
            return dict(p)
    return None


def active() -> dict | None:
    """Первый активный проект — для звонков, которым нужен ОДИН проект "по умолчанию"
    (site/task без явного project_id и т.п.). При нескольких активных это не
    "самый важный", а самый старый из активных — вызывающему, которому важен
    конкретный проект, стоит передавать project_id явно, а не полагаться на active()."""
    return next((dict(p) for p in all_projects() if p.get("status") == "active"), None)


def active_list() -> list[dict]:
    """ВСЕ проекты в активной работе одновременно (v2: параллельные Work,
    см. BOS §10 — «параллельные проекты после выноса живости из памяти
    процесса»). Используется планировщиком (planning_engine), а не только
    самый первый."""
    return [dict(p) for p in all_projects() if p.get("status") == "active"]


def queued_list() -> list[dict]:
    return [dict(p) for p in all_projects() if p.get("status") == "queued"]


def _promote_queued(items: list[dict]) -> None:
    """Если после закрытия проекта освободился слот — активирует самый старый
    проект из очереди (FIFO), а не оставляет его ждать следующего события."""
    limit = get_limit()
    n_active = sum(1 for p in items if p.get("status") == "active")
    queued = sorted((p for p in items if p.get("status") == "queued"),
                     key=lambda p: p.get("created_ts", 0))
    for p in queued:
        if n_active >= limit:
            break
        p["status"] = "active"
        n_active += 1


def create(title: str, goal: str = "", type: str = "project") -> dict:
    """Создаёт Work. Если активных проектов меньше лимита (get_limit(), по
    умолчанию 3) — становится активным сразу; иначе встаёт в очередь (`queued`)
    и активируется автоматически, когда освободится слот (см. close()).

    Раньше здесь ЛЮБОЙ новый проект принудительно закрывал текущий активный
    (v1: "один Work одновременно") — вторая принятая инициатива молча убивала
    первую, даже недоделанную. Теперь это ограничение явное (лимит), а не
    побочный эффект создания нового проекта.

    `type` — project (разовое, есть конец) | process (никогда не завершается сам,
    v1 пока не реализует Instance-поток — заводится как задел на будущее) |
    initiative (идея до решения). Сегодня вся созданная работа фактически ведётся
    как project; поле подготавливает данные к разделению, не меняя раннее поведение."""
    d = _data()
    items = d.get("items", [])
    n_active = sum(1 for p in items if p.get("status") == "active")
    status = "active" if n_active < get_limit() else "queued"
    pid = f"p{len(items) + 1}_{int(time.time()) % 100000}"
    proj = {
        "id": pid, "title": (title or "Проект").strip()[:160],
        "goal": (goal or "").strip()[:300],
        "type": type if type in ("project", "process", "initiative") else "project",
        "status": status,
        "created_ts": time.time(), "closed_ts": None,
        "left_behind": {},   # что проект оставил после себя (заполняется при закрытии)
    }
    items.append(proj)
    d["items"] = items
    _save(d)
    return proj


def ensure_active() -> dict:
    """Активный проект (если слот занят — из очереди, если очередь пуста — новый
    из цели брифа). Единая точка: задачи всегда принадлежат какому-то проекту."""
    cur = active()
    if cur:
        return cur
    d = _data()
    _promote_queued(d.get("items", []))
    _save(d)
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
    # progress(project_id) — раньше вызывался без project_id (progress()
    # компании целиком). Пока Work был один это давало тот же результат, но
    # при параллельных проектах закрытие проекта A показало бы прогресс ПО
    # ВСЕМ активным проектам, а не только по A.
    prog = plan.progress(target["id"])
    target["status"] = "done"
    target["closed_ts"] = time.time()
    target["note"] = (note or "")[:300]
    target["left_behind"] = {
        "tasks_done": prog.get("done", 0),
        "tasks_total": prog.get("total", 0),
        "sites": [s.get("slug", "") for s in sites.all_sites()],
        "leads_count": leads.count(),
    }
    _promote_queued(d.get("items", []))
    _save(d)
    world.save_snapshot(f"project_closed:{target['id']}")
    return dict(target)


def context_block() -> str:
    """Блок проектов для промпта CEO: активные + очередь + краткая история."""
    items = all_projects()
    if not items:
        return ""
    queued = queued_list()
    lines = []
    for p in items[-5:]:
        mark = "🟢" if p.get("status") == "active" else "⏳" if p.get("status") == "queued" else "✅"
        left = p.get("left_behind") or {}
        tail = (f" (сдано {left.get('tasks_done', 0)} задач, лидов: {left.get('leads_count', 0)})"
                if p.get("status") == "done" and left else "")
        lines.append(f"{mark} {p['title']}{tail}")
    header = f"\n=== ПРОЕКТЫ КОМПАНИИ (лимит одновременных: {get_limit()}) ===\n"
    if queued:
        header += f"⏳ В очереди на свободный слот: {len(queued)}\n"
    return header + "\n".join(lines) + "\n"


def reset() -> None:
    ctx.delete_file(_FILE)
    ctx.delete_file(_LIMIT_FILE)
