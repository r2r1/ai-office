"""
Tool Router (item 8): развязывает агентов от конкретных интеграций.

Идея из 1.md: агент говорит «мне нужен сайт» / «отправить сообщение в telegram»,
а не `use_integration("website", "publish_landing", {...})`. Роутер сам подбирает
интеграцию и действие. Поменяли инструмент под капотом — агент не заметил.

Каталог способностей строится ИЗ МЕТАДАННЫХ интеграций (имя/описание/действия),
поэтому новая интеграция подхватывается роутером автоматически — как и в остальной
системе (см. CLAUDE.md). Сверху — словарь синонимов для абстрактных намерений
(«лендинг», «бот», «письмо»), которые человек формулирует не словами из API.

Роутинг детерминированный (ключевые слова, без LLM) — дёшево и предсказуемо.
Скоринг — единый скорер потребностей needs.py (BOS §5), общий со Skills.
"""

from src.integrations import registry as integrations_registry
from src.office import needs

# Синонимы намерения теперь живут В МЕТАДАННЫХ действия (Action.synonyms,
# src/integrations/base.py) — автор новой интеграции видит необходимость сразу
# в своём файле, а не в отдельном модуле роутера. Этот словарь остаётся только
# как fallback для действий, которые ЕЩЁ не задекларировали свои synonyms (не
# должен расти для новых интеграций — там сразу используйте Action(synonyms=[...])).
_INTENT_HINTS: dict[str, tuple[str, str]] = {}

def _capabilities() -> list[dict]:
    """Плоский каталог: каждое действие интеграции — отдельная способность."""
    caps = []
    for integ in integrations_registry.all_integrations():
        for action in integ.actions.values():
            text = f"{integ.name} {integ.title} {integ.description} {action.name} {action.description}"
            caps.append({
                "integration": integ.name,
                "action": action.name,
                "title": integ.title,
                "tokens": needs.tokens(text),
                "connected": integrations_registry.is_connected(integ),
                "synonyms": list(getattr(action, "synonyms", None) or []),
            })
    return caps


def route(need: str, top: int = 3) -> list[dict]:
    """
    Ранжирует способности по близости к свободному описанию потребности.
    Возвращает список кандидатов [{integration, action, title, score, connected}].
    """
    caps = _capabilities()
    by_key = {(c["integration"], c["action"]): c for c in caps}

    scored: dict[tuple[str, str], float] = {}
    low = (need or "").lower()
    # 1) Совпадение по ключевым словам метаданных (единый скорер needs)
    for c in caps:
        overlap = needs.overlap(need, c["tokens"])
        if overlap:
            scored[(c["integration"], c["action"])] = float(overlap)
    # 2) Бонус за синонимы намерения, задекларированные в самом действии
    # (распознаём «лендинг», «письмо» и т.п., которых нет в его описании)
    for c in caps:
        if any(stem in low for stem in c["synonyms"]):
            key = (c["integration"], c["action"])
            scored[key] = scored.get(key, 0.0) + 2.5
    # 3) Legacy fallback — действия без своих synonyms (см. docstring _INTENT_HINTS)
    for stem, (integ_name, action_name) in _INTENT_HINTS.items():
        if stem in low and (integ_name, action_name) in by_key:
            scored[(integ_name, action_name)] = scored.get((integ_name, action_name), 0.0) + 2.5

    ranked = sorted(scored.items(), key=lambda kv: kv[1], reverse=True)[:top]
    out = []
    for (integ_name, action_name), score in ranked:
        c = by_key[(integ_name, action_name)]
        out.append({
            "integration": integ_name, "action": action_name,
            "title": c["title"], "score": round(score, 1), "connected": c["connected"],
        })
    return out


def best(need: str) -> dict | None:
    """Лучший кандидат, если он уверенно лидирует; иначе None (нужна развилка)."""
    cands = route(need, top=2)
    if not cands:
        return None
    if len(cands) == 1 or cands[0]["score"] >= cands[1]["score"] + 1.0:
        return cands[0]
    return None  # неоднозначно — пусть решает агент/уточнение
