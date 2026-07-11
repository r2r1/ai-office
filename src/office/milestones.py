"""
Этапы (вехи) пути офиса к цели — динамический прогресс-бар. По тенанту.

BOS §5/§14 п.6: Stage переезжает ПОД конкретный Work. Системные этапы (intake/
research/strategy) — одноразовый BOOTSTRAP компании, общий для всех проектов
(видны всегда, тегом проекта не помечаются). Бизнес-этапы (заведённые CEO под
конкретный engagement) помечены `project` — тем проектом, для которого их создали;
читающие функции по умолчанию видят только этапы ТЕКУЩЕГО активного проекта, но
принимают `project_id` явно (для карточки закрытого проекта в UI).

Старые записи без `project` (заведены до этой миграции) лениво приписываются
текущему активному проекту при первом чтении — тот же приём, что
`plan.adopt_orphan_tasks`.
"""

import time

from src.saas import context as ctx

_FILE = "milestones.json"

BASE_STAGES = [
    {"id": "intake", "title": "Запрос", "status": "pending", "summary": "", "items": []},
    {"id": "research", "title": "Исследование", "status": "pending", "summary": "", "items": []},
    {"id": "strategy", "title": "Стратегия", "status": "pending", "summary": "", "items": []},
]

_SYS = ("intake", "research", "strategy")


def _current_project_id() -> str:
    from src.office import projects
    p = projects.active()
    return p["id"] if p else ""


def _load() -> list[dict]:
    st = ctx.read_json(_FILE, None)
    if not st:
        return [dict(s) for s in BASE_STAGES]
    pid = _current_project_id()
    if pid:
        changed = False
        for s in st:
            if s["id"] not in _SYS and not s.get("project"):
                s["project"] = pid
                changed = True
        if changed:
            _save(st)
    return st


def _save(stages: list[dict]) -> None:
    ctx.write_json(_FILE, stages)


def all_stages(project_id: str = "") -> list[dict]:
    """Системные этапы (всегда) + бизнес-этапы указанного проекта (или текущего
    активного, если project_id не передан)."""
    st = _load()
    pid = project_id or _current_project_id()
    return [dict(s) for s in st if s["id"] in _SYS or (s.get("project") or "") == pid]


def get(stage_id: str) -> dict | None:
    for s in _load():
        if s["id"] == stage_id:
            return dict(s)
    return None


def set_status(stage_id: str, status: str) -> None:
    st = _load()
    for s in st:
        if s["id"] == stage_id:
            s["status"] = status
            s["updated_ts"] = time.time()
            break
    _save(st)


def mark_active(stage_id: str) -> None:
    st = _load()
    for s in st:
        if s["id"] == stage_id:
            s["status"] = "active"
            s["updated_ts"] = time.time()
        elif s["status"] == "active":
            # Закрываем только РАНЕЕ активный этап. Раньше здесь принудительно ставились
            # done ВСЕ предыдущие не-done этапы — перескок «задним числом» отмечал
            # пропущенные как выполненные (ложный прогресс). Теперь пропущенный этап
            # остаётся pending, а не выдаётся за сделанный.
            s["status"] = "done"
            s["updated_ts"] = time.time()
    _save(st)


def add_item(stage_id: str, text: str, agent_id: str = "", role: str = "") -> None:
    import time
    st = _load()
    for s in st:
        if s["id"] == stage_id:
            s["items"].append({"text": text.strip(), "agent_id": agent_id, "role": role, "ts": time.time()})
            if len(s["items"]) > 40:
                s["items"] = s["items"][-40:]
            break
    _save(st)


def set_summary(stage_id: str, summary: str) -> None:
    st = _load()
    for s in st:
        if s["id"] == stage_id:
            s["summary"] = summary.strip()
            break
    _save(st)


def set_business_stages(stages: list[dict], project_id: str = "") -> None:
    """Задаёт бизнес-этапы ТЕКУЩЕГО проекта (или указанного). Этапы других проектов
    в файле не трогаем — история чужих Work остаётся читаемой (карточка проекта)."""
    pid = project_id or _current_project_id()
    st = _load()
    base = [s for s in st if s["id"] in _SYS]
    for b in base:
        b["status"] = "done"
    other_projects = [s for s in st if s["id"] not in _SYS and (s.get("project") or "") != pid]
    existing = {s["id"]: s for s in st if s["id"] in _SYS or (s.get("project") or "") == pid}
    used_ids = {s["id"] for s in st}  # избегаем коллизий id вообще со всеми, не только своим проектом
    biz = []
    for i, sd in enumerate(stages):
        sid = sd.get("id") or f"stage_{i+1}"
        if sid in existing and sid not in _SYS:
            prev = existing[sid]
            biz.append({"id": sid, "title": sd.get("title", prev["title"]),
                        "status": prev.get("status", "pending"),
                        "summary": prev.get("summary", sd.get("summary", "")),
                        "items": prev.get("items", []), "project": pid})
        else:
            # ЛЛМ может вернуть id, совпадающий с системным этапом (intake/research/
            # strategy) или с другим бизнес-этапом того же ответа — без дедупа два
            # разных этапа получают один id, и любой поиск по id находит только
            # первый, молча пряча второй (реальный кейс: два этапа "strategy").
            if sid in used_ids:
                base_sid, n = sid, 2
                while f"{base_sid}_{n}" in used_ids:
                    n += 1
                sid = f"{base_sid}_{n}"
            biz.append({"id": sid, "title": sd.get("title", f"Этап {i+1}"),
                        "status": "pending", "summary": sd.get("summary", ""), "items": [], "project": pid})
        used_ids.add(sid)
    _save(base + other_projects + biz)


def insert_business_stage(title: str, after_id: str | None = None, status: str = "pending",
                           project_id: str = "") -> str:
    """Добавляет новый бизнес-этап ТЕКУЩЕМУ проекту (по запросу предпринимателя).
    Системные этапы не трогаем. Возвращает id созданного этапа."""
    import re
    pid = project_id or _current_project_id()
    st = _load()
    base = re.sub(r"[^a-z0-9]+", "_", (title or "").lower()).strip("_")[:20] or f"stage_{len(st)+1}"
    sid, i = base, 2
    while any(s["id"] == sid for s in st):
        sid, i = f"{base}_{i}", i + 1
    new = {"id": sid, "title": (title or "").strip()[:80], "status": status, "summary": "", "items": [], "project": pid}
    # позиция вставки: после after_id, но не раньше системных этапов
    idx = len(st)
    if after_id:
        for j, s in enumerate(st):
            if s["id"] == after_id:
                idx = j + 1
                break
    min_idx = max((j for j, s in enumerate(st) if s["id"] in _SYS), default=-1) + 1
    st.insert(max(idx, min_idx), new)
    _save(st)
    return sid


def retitle(stage_id: str, title: str) -> bool:
    st = _load()
    for s in st:
        if s["id"] == stage_id:
            s["title"] = (title or "").strip()[:80]
            _save(st)
            return True
    return False


def has_business_stages(project_id: str = "") -> bool:
    """Есть ли у ТЕКУЩЕГО (или указанного) проекта уже заведённые бизнес-этапы —
    после закрытия проекта и старта нового ответ снова False: новый Work строит
    свой путь заново, не наследует чужой."""
    pid = project_id or _current_project_id()
    return any(s["id"] not in _SYS and (s.get("project") or "") == pid for s in _load())


def all_business_done(project_id: str = "") -> bool:
    pid = project_id or _current_project_id()
    biz = [s for s in _load() if s["id"] not in _SYS and (s.get("project") or "") == pid]
    return bool(biz) and all(s["status"] == "done" for s in biz)


def current_index(project_id: str = "") -> int:
    st = all_stages(project_id)
    active = [i for i, s in enumerate(st) if s["status"] == "active"]
    if active:
        return active[0]
    done = [i for i, s in enumerate(st) if s["status"] == "done"]
    if not done:
        return 0
    # Следующий за последним завершённым; если завершены все — указываем ЗА последний
    # (len), а не на уже готовый этап (иначе прогресс-бар подсвечивал done как «текущий»).
    return done[-1] + 1


def active_stage_id(project_id: str = "") -> str:
    """id этапа, актуального для проекта СЕЙЧАС (активный или ближайший
    ожидающий) — единственная точка, которой plan.py помечает НОВЫЕ задачи
    (milestone_id), чтобы дерево Этап→Задача в UI было честным, а не
    выдуманным сопоставлением. Раньше Stage и Task были двумя параллельными,
    никак не связанными системами (Stage — только текстовый журнал событий)."""
    st = all_stages(project_id)
    if not st:
        return ""
    idx = current_index(project_id)
    if 0 <= idx < len(st):
        return st[idx]["id"]
    return st[-1]["id"]


def progress_payload(project_id: str = "") -> dict:
    st = all_stages(project_id)
    n = len(st)
    done_count = len([s for s in st if s["status"] == "done"])
    return {
        "stages": [{"id": s["id"], "title": s["title"], "status": s["status"],
                    "summary": s["summary"], "item_count": len(s["items"])} for s in st],
        "current": current_index(project_id),
        "percent": round(done_count / n * 100) if n else 0,
    }


def load() -> None:
    pass


def reset() -> None:
    ctx.delete_file(_FILE)
