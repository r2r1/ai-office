"""
Projects — единица работы крупнее задачи (BOS §1, §4): цель + план + артефакты +
метрики, оставленные после себя. Сущность между компанией и план-графом.

Раньше plan.json был плоской доской ОДНОГО engagement'а: «сделали лендинг, теперь
бот» — либо дозапись в тот же граф, либо reset, история смешивалась. Теперь задачи
принадлежат проекту, компания ведёт их историю, а «работа выполнена» — это
закрытие ПРОЕКТА с фиксацией того, что он оставил после себя (сайты, лиды,
метрики) — принцип BOS «каждый проект оставляет после себя измеримость».

Параллельные Work: до N проектов (type="project") одновременно — лимит
настраивается (get_limit()/set_limit(), по умолчанию 3), сверх лимита новый
проект встаёт в очередь и активируется сам при освобождении слота. Процессы
(type="process") лимит не занимают — конвейер продаж/поддержки не должен
ждать свободного "проектного" слота (см. _is_capped_type). Планировщик уже
ведёт РАБОТНИКОВ параллельно по нескольким активным Work (planning_engine.py,
registry.AgentRecord.project_id, Фаза 2).

Каждый проект получает СВОЮ подпапку в workspace/ (workspace_dir, Фаза 3,
см. src/office/workspace.py) — читаемое имя вида "landing_1", а не голый
project_id ("p1_1143"): человек должен узнавать папку по смыслу, а не по
внутреннему идентификатору. Уникальность гарантирует числовой суффикс
(порядковый номер), а не сам слаг — два проекта с похожим названием получат
разные папки ("landing_1", "landing_2"), а не тихо смешаются в одну.

Хранилище: data/tenants/<tid>/projects.json — {"items": [...]}.
"""

import re
import time

from src.saas import context as ctx

_FILE = "projects.json"
_LIMIT_FILE = "project_limits.json"
DEFAULT_MAX_ACTIVE = 3

# Транслитерация для читаемых ЛАТИНСКИХ имён папок из русских названий проектов
# (папки/URL — латиница; sites.make_slug для НЕ-латинских титулов деградирует до
# md5-хеша, что и есть тот самый "нечитаемый формат", от которого уходим здесь).
_CYR_TO_LAT = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh",
    "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu",
    "я": "ya",
})


def _slug(text: str) -> str:
    """Читаемый ASCII-огрызок названия для имени папки (без транслитерации
    результат был бы пустым/хешем для русских титулов — см. sites.make_slug)."""
    t = (text or "").lower().translate(_CYR_TO_LAT)
    s = re.sub(r"[^a-z0-9]+", "_", t).strip("_")
    return s[:24] or "work"


def _unique_workspace_dir(title: str, existing: set[str]) -> str:
    """slug + числовой суффикс, уникальный СРЕДИ УЖЕ ЗАНЯТЫХ имён (не просто
    порядковый номер проекта — иначе переименованный/удалённый проект мог бы
    оставить дыру и слаг совпал бы с чужой папкой)."""
    base = _slug(title)
    n = 1
    while f"{base}_{n}" in existing:
        n += 1
    return f"{base}_{n}"


def _data() -> dict:
    return ctx.read_json(_FILE, {"items": []})


def _save(d: dict) -> None:
    ctx.write_json(_FILE, d)


def _is_capped_type(p: dict) -> bool:
    """Лимит одновременности касается только type="project" (разовая работа
    с концом) — не "process" (непрерывный конвейер: продажи, поддержка и т.п.
    по смыслу никогда не должен упираться в "слот", иначе офис не может вести
    рутинный процесс просто потому, что заняты 3 слота под разовые проекты) и
    не "initiative" (это ещё не решение, а предложение)."""
    return p.get("type", "project") == "project"


def get_limit() -> int:
    """Сколько ПРОЕКТОВ (type="project") офис ведёт ОДНОВРЕМЕННО — параллельные
    Work с ограниченным числом слотов. По умолчанию 3, настраивается владельцем
    (см. set_limit). Процессы (type="process") в этот лимит не входят — см.
    _is_capped_type."""
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


def workspace_dir_of(project_id: str) -> str:
    """Читаемая подпапка workspace/ этого проекта ("landing_1" и т.п.). "" —
    либо проект не найден, либо создан ДО появления workspace_dir (легаси —
    продолжает работать в корне workspace/, как раньше)."""
    p = get(project_id) if project_id else None
    return (p or {}).get("workspace_dir", "")


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


def active_project_count() -> int:
    """Сколько АКТИВНЫХ проектов (type="project") занимают лимит одновременности
    — в отличие от active_list(), не считает процессы (см. _is_capped_type):
    идущий непрерывный процесс не должен визуально "съедать" слот 2/3."""
    return sum(1 for p in all_projects() if p.get("status") == "active" and _is_capped_type(p))


def _promote_queued(items: list[dict]) -> None:
    """Если после закрытия проекта освободился слот — активирует самый старый
    ПРОЕКТ из очереди (FIFO). Процессы в очередь никогда не попадают (см.
    create()), поэтому этот проход их не касается."""
    limit = get_limit()
    n_active = sum(1 for p in items if p.get("status") == "active" and _is_capped_type(p))
    queued = sorted((p for p in items if p.get("status") == "queued"),
                     key=lambda p: p.get("created_ts", 0))
    for p in queued:
        if n_active >= limit:
            break
        p["status"] = "active"
        n_active += 1


def create(title: str, goal: str = "", type: str = "project") -> dict:
    """Создаёт Work. Для type="project": если активных проектов меньше лимита
    (get_limit(), по умолчанию 3) — становится активным сразу; иначе встаёт в
    очередь (`queued`) и активируется автоматически, когда освободится слот
    (см. close()). Для type="process"/"initiative" лимит не действует —
    становится активным сразу (процесс по смыслу непрерывен и не должен
    ждать освобождения "слота под разовый проект").

    Раньше здесь ЛЮБОЙ новый Work принудительно закрывал текущий активный
    (v1: "один Work одновременно") — вторая принятая инициатива молча убивала
    первую, даже недоделанную. Теперь это ограничение явное (лимит на
    проекты), а не побочный эффект создания нового Work.

    `type` — project (разовое, есть конец, ограничено лимитом) | process
    (никогда не завершается сам, БЕЗ лимита — конвейер продаж/поддержки не
    должен вставать в очередь из-за занятых проектных слотов; v1 пока не
    реализует Instance-поток — заводится как задел на будущее) | initiative
    (идея до решения, без лимита). Сегодня вся созданная работа фактически
    ведётся как project; поле подготавливает данные к разделению."""
    d = _data()
    items = d.get("items", [])
    norm_type = type if type in ("project", "process", "initiative") else "project"
    if norm_type == "project":
        n_active = sum(1 for p in items if p.get("status") == "active" and _is_capped_type(p))
        status = "active" if n_active < get_limit() else "queued"
    else:
        status = "active"
    pid = f"p{len(items) + 1}_{int(time.time()) % 100000}"
    existing_dirs = {p["workspace_dir"] for p in items if p.get("workspace_dir")}
    workspace_dir = _unique_workspace_dir(title or "work", existing_dirs)
    proj = {
        "id": pid, "title": (title or "Проект").strip()[:160],
        "goal": (goal or "").strip()[:300],
        "type": norm_type,
        "status": status,
        "workspace_dir": workspace_dir,  # см. докстринг модуля — читаемая папка в workspace/
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
