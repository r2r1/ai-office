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


def _data() -> dict:
    return ctx.read_json(_FILE, {"tasks": [], "generated": False})


# Роли, у которых есть отдел-исполнитель. Задача с ролью вне этого набора не
# маршрутизируется (department=='' → её никто не берёт), и офис тихо стопорился.
_ROLE_REMAP = {
    "researcher": "analyst", "architect": "developer", "strategist": "marketer",
    "hr": "developer", "cto": "developer", "cmo": "marketer", "sales_lead": "salesman",
    "seo": "marketer", "qa": "developer", "copywriter": "marketer", "ux": "designer",
}


def _valid_role(role: str) -> str:
    """Приводит роль задачи к исполнимой (с реальным отделом). Неизвестную → developer."""
    role = (role or "").strip()
    if org.department_of_role(role):
        return role
    return _ROLE_REMAP.get(role, "developer")


def _save(d: dict) -> None:
    ctx.write_json(_FILE, d)


def is_generated() -> bool:
    return bool(_data().get("generated"))


def set_tasks(tasks: list[dict]) -> None:
    """Сохраняет сгенерированный граф задач (нормализует поля). Задачи принадлежат
    активному ПРОЕКТУ (BOS: Project — единица работы крупнее задачи)."""
    from src.office import projects
    project_id = projects.ensure_active()["id"]
    norm = []
    for i, t in enumerate(tasks):
        role = _valid_role(t.get("role") or "")  # роль без отдела → исполнимая (A1)
        tid = (t.get("id") or f"t{i+1}").strip()
        norm.append({
            "id": tid,
            "title": (t.get("title") or "").strip()[:200],
            "role": role,
            "department": org.department_of_role(role),
            "deps": [d for d in (t.get("deps") or []) if d],
            "done_criterion": (t.get("done_criterion") or "").strip()[:200],
            "status": "pending",
            "assignee": "",        # agent_id исполнителя (когда взята в работу)
            "requested_by": "",    # кто поставил (CEO/план или коллега-агент)
            "project": project_id,
        })
    # Чистим deps от ссылок на НЕсуществующие id: LLM иногда генерит зависимость на
    # опечатанный/выдуманный id, и такая задача (и всё, что от неё зависит) НИКОГДА не
    # становится готовой — офис тихо застревал без единой ошибки в логе. Неизвестные deps
    # просто отбрасываем (лучше выполнить раньше, чем не выполнить вообще).
    valid_ids = {t["id"] for t in norm}
    for t in norm:
        cleaned = [d for d in t["deps"] if d in valid_ids and d != t["id"]]
        t["deps"] = cleaned
    _save({"tasks": norm, "generated": True})


def add_task(title: str, role: str, done_criterion: str = "",
             requested_by: str = "", deps: list[str] | None = None) -> dict:
    """
    Добавляет задачу в доску (например, поставленную КОЛЛЕГОЙ-агентом другому отделу/роли).
    Возвращает созданную задачу. Видна в to-do списке исполнителя и у его лидера.
    """
    d = _data()
    tasks = d.get("tasks", [])
    role = _valid_role(role)  # роль без отдела → исполнимая (A1)
    # Дедуп: если такая же незакрытая задача той же роли уже есть — не плодим дубль
    # (циклы делегирования иначе ставили один и тот же таск несколько раз). Инвариант
    # проекта — дедупликация.
    norm_title = " ".join((title or "").lower().split())
    norm_role = (role or "").strip()
    for t in tasks:
        if (t.get("status") in ("pending", "in_progress")
                and t.get("role") == norm_role
                and " ".join((t.get("title", "")).lower().split()) == norm_title):
            return t  # уже стоит в очереди/в работе — возвращаем существующую
    from src.office import projects
    tid = f"t{len(tasks) + 1}_{int(time.time()) % 10000}"
    task = {
        "id": tid, "title": (title or "").strip()[:200], "role": (role or "").strip(),
        "department": org.department_of_role((role or "").strip()),
        "deps": [x for x in (deps or []) if x],
        "done_criterion": (done_criterion or "").strip()[:200],
        "status": "pending", "assignee": "", "requested_by": requested_by,
        "project": projects.ensure_active()["id"],
    }
    tasks.append(task)
    d["tasks"] = tasks
    d["generated"] = True  # доска становится активной даже если граф не строился
    _save(d)
    return task


def all_tasks() -> list[dict]:
    return list(_data().get("tasks", []))


def adopt_orphan_tasks(project_id: str) -> int:
    """Миграция: приписывает задачи БЕЗ проекта (созданные до появления сущности
    Project) к указанному проекту. Возвращает число усыновлённых задач."""
    d = _data()
    n = 0
    for t in d.get("tasks", []):
        if not t.get("project"):
            t["project"] = project_id
            n += 1
    if n:
        _save(d)
    return n


def _done_ids() -> set:
    return {t["id"] for t in all_tasks() if t.get("status") == "done"}


def departments_needed() -> list[str]:
    """Какие отделы нужны для невыполненных задач (для CEO — открыть параллельно)."""
    deps = set()
    for t in all_tasks():
        if t.get("status") != "done" and t.get("department"):
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


# ── Мьютекс артефакта «сайт» ─────────────────────────────────────────────────
# Две задачи, пишущие в site/, НЕЛЬЗЯ выполнять параллельно: агенты переписывают
# index.html целиком и затирают работу друг друга (реальный кейс: designer затёр
# 3D-версию developer через 9 секунд — «последний победил»).
#
# Раньше считали «трогает сайт» по словам в ЗАГОЛОВКЕ задачи — и словили тот же
# баг снова: задача developer «Собрать сценарий проверки и протестировать путь
# обращения» не содержит ни одного site-слова в заголовке, но по факту это QA
# по site/ (использует qa_site_selfcheck, читает и правит site/index.html) —
# мьютекс её не увидел, и designer с developer 4 минуты параллельно переписывали
# один и тот же site/index.html (ai-office-log-20260702_134612). Инвертируем
# логику: designer/developer в tech-отделе по умолчанию считаются «трогают
# сайт», кроме явно НЕ-сайтовых задач (телеграм-бот и т.п.) — так безопаснее,
# чем угадывать по формулировке заголовка.
_NON_SITE_WORDS = ("telegram", "телеграм", " бот", "-бот", "бот)", "боту", "бота",
                    "aiogram", "чат-бот", "chatbot")


def touches_site(task: dict) -> bool:
    """Задача, скорее всего, пишет в site/ (по роли; НЕ-сайтовые задачи — исключение)."""
    if task.get("role") not in ("designer", "developer"):
        return False
    t = (task.get("title") or "").lower()
    return not any(w in t for w in _NON_SITE_WORDS)


def site_task_in_progress() -> str:
    """id сайт-задачи, которая сейчас в работе (или ''). Для мьютекса артефакта."""
    for t in all_tasks():
        if t.get("status") == "in_progress" and touches_site(t):
            return t["id"]
    return ""


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


def complete(task_id: str, acceptance: dict | None = None) -> None:
    """Закрыть задачу. `acceptance` — вердикт приёмки (уровни/проблемы), пишется
    в задачу для UI и History (BOS §8: done только через приёмку)."""
    d = _data()
    for t in d.get("tasks", []):
        if t["id"] == task_id:
            t["status"] = "done"
            if acceptance is not None:
                t["acceptance"] = acceptance
            t["updated_ts"] = time.time()
            break
    _save(d)


def revert(task_id: str) -> int:
    """Вернуть зависшую/упавшую/не прошедшую приёмку задачу в очередь
    (in_progress → pending). Каждый возврат увеличивает счётчик попыток —
    по нему loop эскалирует вместо вечного цикла fail→revert→fail (BOS §8).
    Возвращает новое число попыток (0, если задача не была in_progress)."""
    d = _data()
    for t in d.get("tasks", []):
        if t["id"] == task_id and t.get("status") == "in_progress":
            t["status"] = "pending"
            t["assignee"] = ""
            t["attempts"] = int(t.get("attempts", 0)) + 1
            t["updated_ts"] = time.time()
            _save(d)
            return t["attempts"]
    return 0


def block(task_id: str, reason: str) -> None:
    """Заблокировать задачу после исчерпания попыток: она уходит с доски исполнителей
    (ready_for_department берёт только pending) и ждёт вмешательства владельца/CEO."""
    d = _data()
    for t in d.get("tasks", []):
        if t["id"] == task_id:
            t["status"] = "blocked"
            t["assignee"] = ""
            t["blocked_reason"] = (reason or "")[:300]
            t["updated_ts"] = time.time()
            break
    _save(d)


def unblock(task_id: str) -> bool:
    """Вернуть заблокированную задачу в очередь со сброшенными попытками
    (владелец/CEO вмешался — исполнитель получает чистый счётчик)."""
    d = _data()
    for t in d.get("tasks", []):
        if t["id"] == task_id and t.get("status") == "blocked":
            t["status"] = "pending"
            t["attempts"] = 0
            t["blocked_reason"] = ""
            t["last_feedback"] = ""
            t["updated_ts"] = time.time()
            _save(d)
            return True
    return False


def set_feedback(task_id: str, feedback: str) -> None:
    """Сохранить фидбек приёмки в задаче — попадёт исполнителю при переназначении."""
    d = _data()
    for t in d.get("tasks", []):
        if t["id"] == task_id:
            t["last_feedback"] = (feedback or "")[:500]
            break
    _save(d)


def get_task(task_id: str) -> dict | None:
    for t in all_tasks():
        if t["id"] == task_id:
            return t
    return None


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
        "blocked": [t for t in tasks if t.get("status") == "blocked"],
    }


def board_summary(dept_id: str | None = None) -> str:
    """Короткая сводка доски для лидера: «✓3 ⟳1 ☐2» + что в работе."""
    b = board(dept_id)
    doing = "; ".join(f"{t['id']}:{t['title'][:30]}" for t in b["doing"]) or "—"
    blocked = f" ⛔{len(b['blocked'])}" if b.get("blocked") else ""
    return f"✓{len(b['done'])} ⟳{len(b['doing'])} ☐{len(b['todo'])}{blocked} | в работе: {doing}"


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
