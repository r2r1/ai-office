"""
Trust Score — счёт доверия к офису и каждому отделу (per-tenant).

Растёт с успешными задачами, падает при ошибках/зависаниях.
Используется для:
- предложения повысить уровень автономности
- расчёта Health Score по отделу
- отображения в дашборде
"""

import time
from src.saas import context as ctx

_DEPTS = ["tech", "marketing", "sales"]
_COMPANY_KEY = "company"

# Изменения score
_SUCCESS_DEPT = 3      # успешная задача отдела
_SUCCESS_COMPANY = 1   # вклад в компанию
_FAILURE_DEPT = -8     # провал задачи
_FAILURE_COMPANY = -3
_STUCK_DEPT = -4       # зависший агент
_STUCK_COMPANY = -2

# Порог для предложения upgrade
_UPGRADE_THRESHOLD = 72
_UPGRADE_STREAK = 8   # подряд успешных задач


def _load() -> dict:
    d = ctx.read_json("trust", None) or {}
    return {
        _COMPANY_KEY: d.get(_COMPANY_KEY, 20),
        "tech":       d.get("tech", 20),
        "marketing":  d.get("marketing", 20),
        "sales":      d.get("sales", 20),
        "streak":     d.get("streak", 0),       # подряд успешных задач
        "total_done": d.get("total_done", 0),
        "total_fail": d.get("total_fail", 0),
        "last_upgrade_proposed": d.get("last_upgrade_proposed", 0),
    }


def _save(d: dict) -> None:
    ctx.write_json("trust", d)


def _clamp(v: int) -> int:
    return max(0, min(100, v))


def record_success(dept: str) -> None:
    d = _load()
    if dept in d:
        d[dept] = _clamp(d[dept] + _SUCCESS_DEPT)
    d[_COMPANY_KEY] = _clamp(d[_COMPANY_KEY] + _SUCCESS_COMPANY)
    d["streak"] = d.get("streak", 0) + 1
    d["total_done"] = d.get("total_done", 0) + 1
    _save(d)


def record_failure(dept: str) -> None:
    d = _load()
    if dept in d:
        d[dept] = _clamp(d[dept] + _FAILURE_DEPT)
    d[_COMPANY_KEY] = _clamp(d[_COMPANY_KEY] + _FAILURE_COMPANY)
    d["streak"] = 0
    d["total_fail"] = d.get("total_fail", 0) + 1
    _save(d)


def record_stuck(dept: str) -> None:
    d = _load()
    if dept in d:
        d[dept] = _clamp(d[dept] + _STUCK_DEPT)
    d[_COMPANY_KEY] = _clamp(d[_COMPANY_KEY] + _STUCK_COMPANY)
    d["streak"] = 0
    _save(d)


def get_score(key: str = _COMPANY_KEY) -> int:
    return _load().get(key, 20)


def should_propose_upgrade() -> bool:
    """Пора ли предложить пользователю повысить уровень автономности."""
    from src.office import autonomy
    level = autonomy.get_level()
    if level == "autonomous":
        return False  # уже максимум

    d = _load()
    company = d.get(_COMPANY_KEY, 0)
    streak = d.get("streak", 0)

    # Не предлагать чаще раза в сутки
    last = d.get("last_upgrade_proposed", 0)
    if time.time() - last < 86400:
        return False

    return company >= _UPGRADE_THRESHOLD and streak >= _UPGRADE_STREAK


def mark_upgrade_proposed() -> None:
    d = _load()
    d["last_upgrade_proposed"] = time.time()
    _save(d)


def upgrade_proposal_text() -> str:
    """Текст предложения повысить уровень автономности для CEO."""
    from src.office import autonomy
    current = autonomy.get_level()
    levels = autonomy.LEVELS
    idx = levels.index(current)
    if idx + 1 >= len(levels):
        return ""
    next_level = levels[idx + 1]
    cur_info = autonomy.LEVEL_INFO[current]
    next_info = autonomy.LEVEL_INFO[next_level]
    d = _load()
    return (
        f"Офис успешно выполнил {d.get('total_done', 0)} задач "
        f"({d.get('streak', 0)} подряд без ошибок). "
        f"Trust Score компании: {d.get(_COMPANY_KEY, 0)}/100. "
        f"Текущий уровень: {cur_info['icon']} {cur_info['name']}. "
        f"Предлагаю перейти на {next_info['icon']} {next_info['name']} — "
        f"{next_info['desc']}. Команда «/autonomy {next_level}» или через Дашборд."
    )


def payload() -> dict:
    d = _load()
    return {
        "company": d.get(_COMPANY_KEY, 20),
        "departments": {dept: d.get(dept, 20) for dept in _DEPTS},
        "streak":     d.get("streak", 0),
        "total_done": d.get("total_done", 0),
        "total_fail": d.get("total_fail", 0),
    }

