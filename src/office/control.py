"""
Управление состоянием офис-цикла — пауза / возобновление.

data/tenants/<tid>/control.json:
  {"paused": true/false, "reason": "...", "paused_at": timestamp}
"""

import time
from src.saas import context as ctx

_FILE = "control.json"


def _load() -> dict:
    return ctx.read_json(_FILE, {"paused": False, "reason": "", "paused_at": 0})


def _save(d: dict) -> None:
    ctx.write_json(_FILE, d)


def is_paused() -> bool:
    return bool(_load().get("paused"))


def pause(reason: str = "") -> None:
    _save({"paused": True, "reason": reason, "paused_at": time.time()})
    _reset_approvals()


def resume() -> None:
    _save({"paused": False, "reason": "", "paused_at": 0})
    _reset_approvals()


def _reset_approvals() -> None:
    # Разовые одобрения (публикация и т.п.) не должны переживать паузу/возобновление —
    # это новая «сессия доверия», клиент подтверждает заново. Ленивый импорт против цикла.
    try:
        from src.office import autonomy
        autonomy.reset_approvals()
    except Exception:
        pass


def status() -> dict:
    d = _load()
    return {
        "paused": d.get("paused", False),
        "reason": d.get("reason", ""),
        "paused_at": d.get("paused_at", 0),
    }


def summary_text() -> str:
    """Сводка «на чём остановились» — публикуется сразу после постановки на
    паузу (см. call sites pause() в execution.py/loop.py/routers/*.py).

    Форензик-аудит прогона 2026-07-18 («Кухни на заказ КМВ»): прогон оборвался
    на автопаузе по отрицательному балансу LLM-провайдера, и последним
    сообщением в ленте оказался случайный вопрос агента про стиль обложек —
    владелец, вернувшись после пополнения баланса, должен был сам
    восстанавливать картину «что было в работе», пролистывая ленту назад.
    Явная сводка сразу после сообщения о причине паузы закрывает это —
    не заменяет причину, а дополняет её конкретикой (сколько задач в работе,
    сколько заблокировано, есть ли неотвеченный вопрос владельцу)."""
    from src.office import plan as plan_module, questions as questions_module
    if not plan_module.is_generated():
        return ""
    doing = [t for t in plan_module.all_tasks() if t.get("status") == "in_progress"]
    blocked = plan_module.blocked_tasks()
    open_qs = questions_module.list_pending()
    if not doing and not blocked and not open_qs:
        return ""
    lines = ["📋 На чём остановились:"]
    if doing:
        titles = "; ".join(f"{t['id']} ({t.get('role','?')})" for t in doing[:5])
        lines.append(f"— в работе: {titles}")
    if blocked:
        titles = "; ".join(t["id"] for t in blocked[:5])
        lines.append(f"— заблокировано, ждёт решения: {titles}")
    if open_qs:
        lines.append(f"— неотвеченных вопросов владельцу: {len(open_qs)}")
    return "\n".join(lines)
