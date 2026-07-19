"""
Intent — единый вход намерений в компанию (см. docs/bos-architecture.md §1, §12).

Intent — это неструктурированная воля ДО интерпретации: сообщение владельца из
чата, идея онбординга, инициатива офиса. Он не управляет компанией напрямую —
сначала интерпретация (сегодня — CEO-триаж interpret_directive, завтра — полный
пайплайн Intent → Goal → Project), и только потом работа.

v1 намеренно примитивна: важен ВХОД (все директивы проходят через capture и
остаются в журнале с результатом интерпретации), а не ум интерпретатора.
Хранилище: data/tenants/<tid>/intents.json — {"items": [...]}.

Multi-user (docs/product-portrait-2026-07-19.md §12): `source` больше не
ограничен owner|onboarding|company — директива домен-пользователя проходит
ТОТ ЖЕ capture(), просто source — конкретный человек (`f"member:{user_id}"`).
Реальный риск (сформулирован в интервью): несколько людей независимо дают
поручения, конфликт обнаруживается позже, чем стоило бы. `capture()` сам
проверяет НЕДАВНИЕ директивы от ДРУГИХ source на пересечение содержания
(тот же word-overlap эвристика, что уже есть в initiatives.has_pending_
similar) — при реальном пересечении поднимает `events.raise_event("blocker",
...)`, эскалация основателю, тот же паттерн, что конфликт отделов внутри
офиса (портрет §11), не отдельный механизм обнаружения конфликтов.
"""

import time

from src.saas import context as ctx

_FILE = "intents.json"
_MAX = 200

# Окно, в котором две директивы РАЗНЫХ людей о пересекающемся содержании
# считаются потенциальным конфликтом, не совпадением по случаю недели.
_CONFLICT_WINDOW_SECS = 24 * 3600
_CONFLICT_OVERLAP = 0.5  # тот же порог, что initiatives.has_pending_similar


def _data() -> dict:
    return ctx.read_json(_FILE, {"items": []})


def _save(d: dict) -> None:
    d["items"] = d.get("items", [])[-_MAX:]
    ctx.write_json(_FILE, d)


def _overlap(a: str, b: str) -> float:
    wa, wb = set(a.lower().split()), set(b.lower().split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / max(len(wa), len(wb))


def _check_conflict(text: str, source: str) -> None:
    """Реальное пересечение с недавней директивой ДРУГОГО человека — не тихо
    перезаписываем и не молча копим — поднимаем blocker для основателя."""
    if not source.startswith("member:") and source != "owner":
        return  # директивы офиса/онбординга сами с собой не конфликтуют
    now = time.time()
    for it in reversed(_data().get("items", [])):
        other_source = it.get("source", "")
        if other_source == source or (now - it.get("ts", 0)) > _CONFLICT_WINDOW_SECS:
            continue
        if other_source not in ("owner",) and not other_source.startswith("member:"):
            continue
        if _overlap(text, it.get("text", "")) > _CONFLICT_OVERLAP:
            try:
                from src.office import events as events_mod
                events_mod.raise_event(
                    "blocker",
                    f"Противоречащие поручения от разных людей: «{it.get('text','')[:80]}» "
                    f"({other_source}) vs «{text[:80]}» ({source}) — нужно решение основателя",
                )
            except Exception:
                pass
            return


def capture(text: str, source: str = "owner") -> dict:
    """Фиксирует намерение в журнале. `source`: owner | onboarding | company |
    f"member:{user_id}" (портрет §12). Возвращает созданный Intent
    (status=received). Конфликт с недавней директивой другого человека —
    см. `_check_conflict`, не блокирует запись, только эскалирует."""
    text = (text or "").strip()
    if not text:
        return {}
    _check_conflict(text, source)
    d = _data()
    items = d.get("items", [])
    iid = f"in{len(items) + 1}_{int(time.time()) % 100000}"
    it = {"id": iid, "text": text[:600], "source": source,
          "status": "received", "interpretation": {}, "ts": time.time()}
    items.append(it)
    d["items"] = items
    _save(d)
    return it


def set_interpretation(iid: str, scope: str = "", directive: str = "",
                       tasks_added: int = 0) -> None:
    """Результат интерпретации (CEO-триаж): как компания поняла намерение."""
    d = _data()
    for it in d.get("items", []):
        if it["id"] == iid:
            it["status"] = "interpreted"
            it["interpretation"] = {"scope": scope, "directive": directive[:300],
                                    "tasks_added": tasks_added}
            it["interpreted_ts"] = time.time()
            break
    _save(d)


def recent(n: int = 30) -> list[dict]:
    return list(reversed(_data().get("items", [])))[:n]


def reset() -> None:
    ctx.delete_file(_FILE)
