"""
Бриф клиента — то, что превращает универсальный офис в офис «под клиента».

Хранится по тенанту (data/tenants/<tid>/brief.json). Готовность брифа офис-цикл
определяет опросом файла (без глобального asyncio.Event — он не мультиарендный).
"""

from src.saas import context as ctx

_FILE = "brief.json"


def set_brief(data: dict) -> None:
    ctx.write_json(_FILE, data or {})


def get() -> dict:
    return ctx.read_json(_FILE, {})


def is_ready() -> bool:
    return bool(get().get("summary"))


def research_question() -> str:
    b = get()
    if b.get("research_question"):
        return b["research_question"]
    niche = b.get("niche", "")
    goal = b.get("goal", "")
    if niche or goal:
        return (
            f"Проанализируй актуальные тренды 2026 года в нише: {niche}. "
            f"Цель клиента: {goal}. Найди что сейчас работает, кейсы, "
            f"каналы продвижения, как делать контент с максимальным охватом."
        )
    return ""


def summary() -> str:
    return get().get("summary", "")


def avg_check() -> float | None:
    """Средний чек из типизированного брифа (Phase 3a) или None. Вход прокси-выручки
    Measurement (лиды × чек). Валюта — как ввёл клиент; прокси валюто-независим."""
    v = get().get("avg_check_usd")
    return float(v) if isinstance(v, (int, float)) else None


def budget() -> float | None:
    """Бюджет/оборот из типизированного брифа или None."""
    v = get().get("budget_usd")
    return float(v) if isinstance(v, (int, float)) else None


_JUNK_GOALS = {"не знаю", "незнаю", "не знаю.", "-", "—", "нет", "хз", "?", ""}


def is_junk_goal(goal: str) -> bool:
    """Цель бессодержательна («не знаю», «-», пусто). Единый сигнал качества цели —
    его читают и effective_goal (подмена целью из стратегии), и understanding
    (мусорная цель не должна засчитываться как понятая — раньше индикатор давал
    +10 за любую непустую строку, включая «не знаю»)."""
    return (goal or "").strip().lower() in _JUNK_GOALS


def has_meaningful_goal() -> bool:
    """У брифа есть осмысленная цель компании (не «не знаю»/пусто)."""
    return not is_junk_goal(get().get("goal") or "")


def effective_goal() -> str:
    """
    Осмысленная цель компании для промптов (переехало из loop._goal — цель принадлежит
    брифу, а не циклу). Клиент в онбординге может ответить «не знаю» — тогда
    «Цель компании: не знаю» замусоривала КАЖДЫЙ промпт, хотя стратег уже сформулировал
    реальную цель. Мусорная цель → берём её из стратегии.
    """
    g = (get().get("goal") or "").strip()
    if not is_junk_goal(g):
        return g
    # Первая содержательная строка стратегии обычно и есть сформулированная цель.
    f = ctx.tenant_dir() / "strategy.md"
    strategy = f.read_text(encoding="utf-8") if f.exists() else ""
    for line in strategy.splitlines():
        line = line.strip().lstrip("#*-1234567890. ").strip()
        if line.lower().startswith("цель"):
            return line[:200]
    return summary() or "разобраться в нише и предложить первый результат"


def load() -> bool:
    return is_ready()


def reset() -> None:
    ctx.delete_file(_FILE)
