"""
Пер-тенантные предпочтения UI: видимость/порядок под-вкладок раздела (сейчас —
только "Результаты", реестр из results.py). Персонализация поверх реестра —
владелец решает, что видно и в каком порядке, реестр решает, что вообще
доступно (тот же принцип развязки: платформа регистрирует, тенант выбирает).
"""

from src.saas import context as ctx

_FILE = "ui_prefs.json"
_DEFAULT_SECTION = {"order": [], "hidden": []}


def get_section(section: str) -> dict:
    prefs = ctx.read_json(_FILE, {})
    return prefs.get(section, dict(_DEFAULT_SECTION))


def set_section(section: str, order: list[str] | None = None, hidden: list[str] | None = None) -> dict:
    prefs = ctx.read_json(_FILE, {})
    cur = prefs.get(section, dict(_DEFAULT_SECTION))
    if order is not None:
        cur["order"] = [str(x) for x in order]
    if hidden is not None:
        cur["hidden"] = [str(x) for x in hidden]
    prefs[section] = cur
    ctx.write_json(_FILE, prefs)
    return cur
