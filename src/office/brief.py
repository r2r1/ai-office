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


def load() -> bool:
    return is_ready()


def reset() -> None:
    ctx.delete_file(_FILE)
