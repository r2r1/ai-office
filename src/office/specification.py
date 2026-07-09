"""
Specification — формализованное понимание работы ДО исполнения (BOS §1, §8 L1).

Спецификация — контракт приёмки: что делаем (функции) и когда это считается
успехом (критерии). Источник чек-листа Acceptance-слоя. v1 собирается
ДЕТЕРМИНИРОВАННО из брифа и план-графа (без LLM и без блокировки офиса);
подтверждение владельцем — опциональное действие (POST /api/specification/confirm),
повышающее доверие к приёмке, а не ворота перед стартом.

Хранилище: data/tenants/<tid>/specification.json, ключ — project_id.
Раньше был ОДИН контракт на весь тенант, собранный из plan.all_tasks() один
раз при BOOTSTRAP — реальный кейс (лог прогона 2026-07-09): второй параллельный
проект (принятая инициатива) получал 100% задач с warning "работа вне
согласованного объёма", потому что сверялся со спекой ПЕРВОГО проекта, с
которой структурно не мог совпасть. Теперь спецификация — per-project, каждый
Work получает свой контракт из своих же задач (plan.for_project).
"""

import time

from src.saas import context as ctx

_FILE = "specification.json"


def _current_project_id() -> str:
    from src.office import projects
    return projects.ensure_active()["id"]


def _all() -> dict:
    """{"by_project": {pid: spec}}. Старый формат ({"functions": [...], ...} —
    плоский, один контракт на тенанта) мигрируется на лету под id проекта,
    активного на момент чтения, чтобы уже начатые прогоны не потеряли свою
    единственную спецификацию при обновлении."""
    d = ctx.read_json(_FILE, {})
    if "by_project" in d:
        return d
    if d.get("functions"):
        return {"by_project": {_current_project_id(): d}}
    return {"by_project": {}}


def _save(d: dict) -> None:
    ctx.write_json(_FILE, d)


def get(project_id: str = "") -> dict:
    pid = project_id or _current_project_id()
    return dict(_all().get("by_project", {}).get(pid, {}))


def exists(project_id: str = "") -> bool:
    return bool(get(project_id).get("functions"))


def ensure(project_id: str = "") -> dict:
    """Собирает спецификацию из брифа + задач ЭТОГО проекта, если её ещё нет.
    Идемпотентно. `project_id=""` — активный проект (обратная совместимость с
    единственным-проектом сценарием: bootstrap ещё не знает id заранее)."""
    pid = project_id or _current_project_id()
    cur = get(pid)
    if cur.get("functions"):
        return cur
    from src.office import brief, plan
    b = brief.get()
    tasks = plan.for_project(pid)
    spec = {
        "project_id": pid,
        "goal": brief.effective_goal(),
        "niche": b.get("niche", ""),
        "audience": b.get("audience", ""),
        # Функции = что офис собирается сделать (из заголовков плана ЭТОГО проекта)
        "functions": [t.get("title", "")[:160] for t in tasks if t.get("title")],
        # Критерии успеха = проверяемые done_criterion задач (контракт приёмки)
        "success_criteria": [t["done_criterion"][:160] for t in tasks
                             if t.get("done_criterion")],
        "status": "draft",       # draft → confirmed (владелец подтвердил)
        "confirmed_note": "",
        "created_ts": time.time(),
    }
    d = _all()
    d.setdefault("by_project", {})[pid] = spec
    _save(d)
    return spec


def confirm(note: str = "", project_id: str = "") -> dict:
    """Владелец подтвердил спецификацию (Level 1 пройден явно)."""
    pid = project_id or _current_project_id()
    spec = get(pid)
    if not spec:
        spec = ensure(pid)
    spec["status"] = "confirmed"
    spec["confirmed_note"] = (note or "").strip()[:300]
    spec["confirmed_ts"] = time.time()
    d = _all()
    d.setdefault("by_project", {})[pid] = spec
    _save(d)
    return spec


def checklist(project_id: str = "") -> list[str]:
    """Критерии успеха для финальной приёмки engagement'а этого проекта."""
    return list(get(project_id).get("success_criteria", []))


def covers(criterion: str, project_id: str = "") -> bool:
    """Покрыт ли `criterion` (done_criterion задачи) контрактом приёмки ЕЁ
    СОБСТВЕННОГО проекта (success_criteria спецификации). Спецификация
    собирается из done_criterion задач плана — критерий исходной задачи в ней
    есть по построению. Задача, добавленная ПОЗЖЕ (делегирование/директива/
    fix), может нести критерий ВНЕ согласованного контракта — тогда приёмка
    помечает это предупреждением (Acceptance L1, не жёсткий провал — v1).

    Сверка: точное совпадение нормализованного текста ИЛИ высокое перекрытие
    токенов (≥60% токенов критерия покрыты одним из success_criteria) — устойчиво
    к мелким переформулировкам, не к смене сути работы."""
    from src.office import needs
    crit = " ".join((criterion or "").lower().split())
    if not crit:
        return True  # нет критерия — нечего сверять
    crit_tokens = needs.tokens(criterion)
    if not crit_tokens:
        return True
    for sc in get(project_id).get("success_criteria", []):
        if " ".join((sc or "").lower().split()) == crit:
            return True
        common = len(crit_tokens & needs.tokens(sc))
        if common >= max(1, int(len(crit_tokens) * 0.6)):
            return True
    return False


def status(project_id: str = "") -> str:
    """Статус контракта ЭТОГО проекта: 'draft' | 'confirmed' | '' (нет спецификации)."""
    spec = get(project_id)
    return spec.get("status", "") if spec.get("functions") else ""


def context_block(project_id: str = "") -> str:
    """Блок спецификации для промптов (или '')."""
    spec = get(project_id)
    if not spec.get("functions"):
        return ""
    st = "подтверждена владельцем" if spec.get("status") == "confirmed" else "черновик"
    lines = [f"Статус: {st}"]
    if spec.get("success_criteria"):
        lines.append("Критерии успеха:")
        lines += [f"  ✓ {c}" for c in spec["success_criteria"][:8]]
    return "\n=== СПЕЦИФИКАЦИЯ РАБОТЫ (контракт приёмки) ===\n" + "\n".join(lines) + "\n"


def all_specs() -> dict:
    """{project_id: spec} для всех проектов — вкладка «Проект» показывает
    контракт КАЖДОГО параллельного Work, не только активного по умолчанию."""
    return dict(_all().get("by_project", {}))


def reset() -> None:
    ctx.delete_file(_FILE)
