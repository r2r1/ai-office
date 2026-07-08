"""
Система инициатив — BOS §5: идея ДО решения. Предлагает либо CEO (по
наблюдённой opportunity), либо сам предприниматель (propose()). Прежде чем
показать пользователю решение accept/reject, инициатива проходит стадию
глубокого исследования (research) — офис не просит решить вслепую, решение
принимается по анализу, не по одной строке заголовка.

Статусы: researching (идёт анализ) → pending (ждёт решения) → accepted/rejected/expired.
При accept — задачи инициативы добавляются в план (см. server.py accept_initiative,
который дополнительно заводит/переименовывает Work под неё — BOS §3).
"""

import time
import uuid
from src.saas import context as ctx

_MAX = 50
_EXPIRE_SECS = 7 * 24 * 3600  # 7 дней


class InitiativeBlocked(Exception):
    """accept() отказал без override=True — исследование дало явный отрицательный
    вердикт (docs/product-capability-gaps.md п.6). Раньше research был только
    текстом ДЛЯ ЧТЕНИЯ: владелец мог принять инициативу вопреки любому выводу
    анализа, потому что технически ничего этому не мешало — «AI Office проверит
    жизнеспособность» не блокировало запуск, даже когда сам ответ был «не стоит»."""
    def __init__(self, recommendation: str, research: str):
        self.recommendation = recommendation
        self.research = research
        super().__init__(f"initiative blocked: recommendation={recommendation}")


def _load() -> list:
    return ctx.read_json("initiatives", None) or []


def _save(items: list) -> None:
    ctx.write_json("initiatives", items[-_MAX:])


def add(
    title: str,
    rationale: str,
    expected_outcome: str,
    estimated_effort: str = "1-2 цикла",
    tasks: list | None = None,
    source: str = "ceo",  # "ceo" | "event" | "auto" | "user"
    needs_research: bool = True,
) -> str:
    """Добавить инициативу. Дедуп по title. needs_research=True — статус
    "researching" (ждёт глубокого анализа, ещё не показывается на решение);
    False — сразу "pending" (для путей, где анализ уже включён в rationale)."""
    items = _load()
    for item in items:
        if item["status"] in ("pending", "researching") and item["title"].lower() == title.lower():
            return item["id"]

    iid = f"i_{uuid.uuid4().hex[:8]}"
    items.append({
        "id": iid,
        "ts": time.time(),
        "title": title,
        "rationale": rationale,
        "expected_outcome": expected_outcome,
        "estimated_effort": estimated_effort,
        "tasks": tasks or [],
        "source": source,
        "research": "",
        "recommendation": "unclear",  # go | no-go | unclear — см. set_research()
        "status": "researching" if needs_research else "pending",
        "expires_at": time.time() + _EXPIRE_SECS,
    })
    _save(items)
    return iid


def propose(title: str, idea: str) -> str:
    """Предприниматель сам предлагает инициативу (не только AI) — минимальный
    ввод (название + мысль), глубокий анализ офис делает сам (see server.py:
    планировщик запускает research в фоне сразу после создания)."""
    return add(title, idea, "", "1-2 цикла", [], source="user", needs_research=True)


def get(iid: str) -> dict | None:
    for item in _load():
        if item["id"] == iid:
            return dict(item)
    return None


def set_research(iid: str, research: str, tasks: list | None = None,
                  recommendation: str = "unclear") -> dict | None:
    """Фиксирует результат глубокого исследования и переводит инициативу в
    pending — только теперь она показывается пользователю на решение.
    `recommendation` ∈ go | no-go | unclear (см. initiative_research._parse_verdict —
    детерминированный разбор явного маркера "ВЕРДИКТ: ..." в конце текста
    исследования, не доверие свободной форме целиком)."""
    if recommendation not in ("go", "no-go", "unclear"):
        recommendation = "unclear"
    items = _load()
    for item in items:
        if item["id"] == iid:
            item["research"] = (research or "").strip()[:3000]
            item["recommendation"] = recommendation
            if tasks:
                item["tasks"] = tasks
            item["status"] = "pending"
            _save(items)
            return dict(item)
    return None


def researching() -> list:
    return [i for i in _load() if i["status"] == "researching"]


def pending() -> list:
    expire_old()
    items = _load()
    return [i for i in items if i["status"] == "pending"]


def active() -> list:
    """Всё, что пользователь ещё увидит (идёт анализ + ждёт решения) —
    для UI, который должен показать «идёт исследование», а не молчать."""
    expire_old()
    items = _load()
    return [i for i in items if i["status"] in ("researching", "pending")]


def accept(iid: str, override: bool = False) -> list:
    """Принять инициативу. Возвращает список задач для добавления в план.
    Бросает InitiativeBlocked, если исследование дало вердикт "no-go" и
    override не передан явно — «последнее слово у владельца» (BOS §2) остаётся
    в силе, но требует ОСОЗНАННОГО подтверждения вопреки рекомендации, а не
    тихого прохождения мимо неё."""
    items = _load()
    tasks = []
    for item in items:
        if item["id"] == iid:
            if item.get("recommendation") == "no-go" and not override:
                raise InitiativeBlocked(item["recommendation"], item.get("research", ""))
            item["status"] = "accepted"
            tasks = item.get("tasks") or []
            break
    _save(items)
    return tasks


def reject(iid: str) -> None:
    items = _load()
    for item in items:
        if item["id"] == iid:
            item["status"] = "rejected"
            break
    _save(items)


def snooze(iid: str, days: int = 3) -> None:
    """Отложить инициативу на N дней."""
    items = _load()
    for item in items:
        if item["id"] == iid:
            item["expires_at"] = time.time() + days * 86400
            break
    _save(items)


def expire_old() -> None:
    now = time.time()
    items = _load()
    changed = False
    for item in items:
        if item["status"] == "pending" and item.get("expires_at", 0) < now:
            item["status"] = "expired"
            changed = True
    if changed:
        _save(items)


def has_pending_similar(title: str) -> bool:
    for item in pending():
        words_new = set(title.lower().split())
        words_old = set(item["title"].lower().split())
        overlap = len(words_new & words_old) / max(len(words_new), len(words_old), 1)
        if overlap > 0.5:
            return True
    return False


def payload() -> dict:
    p = pending()
    r = researching()
    all_items = _load()
    return {
        "pending": p,
        "researching": r,
        "pending_count": len(p),
        "total": len(all_items),
    }
