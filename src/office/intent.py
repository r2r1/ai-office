"""
Intent — единый вход намерений в компанию (см. docs/bos-architecture.md §1, §12).

Intent — это неструктурированная воля ДО интерпретации: сообщение владельца из
чата, идея онбординга, инициатива офиса. Он не управляет компанией напрямую —
сначала интерпретация (сегодня — CEO-триаж interpret_directive, завтра — полный
пайплайн Intent → Goal → Project), и только потом работа.

v1 намеренно примитивна: важен ВХОД (все директивы проходят через capture и
остаются в журнале с результатом интерпретации), а не ум интерпретатора.
Хранилище: data/tenants/<tid>/intents.json — {"items": [...]}.
"""

import time

from src.saas import context as ctx

_FILE = "intents.json"
_MAX = 200


def _data() -> dict:
    return ctx.read_json(_FILE, {"items": []})


def _save(d: dict) -> None:
    d["items"] = d.get("items", [])[-_MAX:]
    ctx.write_json(_FILE, d)


def capture(text: str, source: str = "owner") -> dict:
    """Фиксирует намерение в журнале. `source`: owner | onboarding | company.
    Возвращает созданный Intent (status=received)."""
    text = (text or "").strip()
    if not text:
        return {}
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
