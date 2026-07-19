"""
Философия компании — самый верхний уровень системы управления.

Определяет «характер» цифровой организации: почему она существует,
что считается успехом, какими принципами не жертвует, стиль роста.
Инжектируется в промпт CEO и всех агентов с НАИВЫСШИМ приоритетом
(выше стратегии, выше ТЗ) — чтобы два клиента с одинаковым брифом
получили решения, соответствующие характеру их компании.
"""

from src.saas import context as ctx

GROWTH_STYLES = {
    "aggressive":    "Агрессивный рост — скорость важнее осторожности, риски приемлемы",
    "stable":        "Устойчивое развитие — надёжность и предсказуемость важнее скорости",
    "premium":       "Премиальное качество — лучше сделать меньше, но безупречно",
    "experimental":  "Экспериментальный — тестирование гипотез, итерации, pivot при необходимости",
}

RISK_APPETITES = {
    "low":    "Низкий — избегать рисков, каждое решение согласовывать",
    "medium": "Средний — разумный риск в рамках стратегии",
    "high":   "Высокий — готовы рисковать ради быстрого результата",
}

_DEFAULT: dict = {
    "growth_style": "stable",
    "mission": "",
    "success_means": "",
    "never_sacrifice": "",
    "risk_appetite": "medium",
    # ⚠️ НЕ то же самое, что growth_style (портрет §11 — важно не перепутать):
    # growth_style — КАК офис растёт, если растёт (осторожно/агрессивно/premium).
    # boost — растит ли офис ВООБЩЕ САМ, без запроса. True (дефолт) — офис сам
    # активно ищет точки роста (см. planning_engine.py «Блок 4»). False —
    # «поддержание»: офис не хантит новые возможности сам, но Process и прямой
    # запрос владельца по-прежнему могут породить инициативу — boost гейтит
    # ТОЛЬКО источник «CEO сам заметил и предложил», не инициативы вообще.
    "boost": True,
}


def load() -> dict:
    data = ctx.read_json("philosophy", None) or {}
    return {**_DEFAULT, **data}


def save(data: dict) -> None:
    current = load()
    current.update({k: v for k, v in data.items() if k in _DEFAULT})
    ctx.write_json("philosophy", current)


def is_set() -> bool:
    d = load()
    return bool(d.get("mission") or d.get("success_means") or d.get("growth_style") != "stable")


def context_block() -> str:
    """Блок для всех агентов. Наивысший приоритет в системном промпте."""
    d = load()
    if not d.get("mission") and not d.get("success_means"):
        return ""
    style = GROWTH_STYLES.get(d.get("growth_style", "stable"), "")
    risk = RISK_APPETITES.get(d.get("risk_appetite", "medium"), "")
    lines = ["=== ФИЛОСОФИЯ КОМПАНИИ (наивысший приоритет) ==="]
    if d.get("mission"):
        lines.append(f"Миссия: {d['mission']}")
    if d.get("success_means"):
        lines.append(f"Успех — это: {d['success_means']}")
    if d.get("never_sacrifice"):
        lines.append(f"Никогда не жертвуем: {d['never_sacrifice']}")
    if style:
        lines.append(f"Стиль роста: {style}")
    if risk:
        lines.append(f"Аппетит к риску: {risk}")
    lines.append("Все решения должны соответствовать этой философии.")
    return "\n".join(lines)

