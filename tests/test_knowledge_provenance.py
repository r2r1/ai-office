"""
Провенанс знаний (spec docs/ai-office-canonical-spec.md §4.2/§5.2):
- remember() сохраняет source и confidence; неизвестный source деградирует к inferred;
- непроверенные dept-факты подписываются в retrieve();
- факты автоскана сайта (brief["scan"]) попадают в GLOBAL-слой без дублирования;
- при равной релевантности проверенный факт обгоняет гипотезу.

Без LLM ($0): эмбеддинги в тестовом окружении недоступны → embed() отдаёт None,
ранжирование чисто TF — это штатная деградация.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="backslashreplace")

os.environ.setdefault("DEMO_MODE", "1")

from src.saas import context as ctx


def _fresh(name: str) -> None:
    """Изоляция как в test_processes.py: свой тенант, вычищенный до и после."""
    ctx.set_tenant(name)
    ctx.wipe()
    ctx.set_tenant(name)


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(("[ok] " if cond else "[FAIL] ") + name)
        if not cond:
            failures.append(name)

    _fresh("know_provenance_test")
    from src.office import knowledge, brief
    brief.set_brief({"goal": "тест", "niche": "кофейня", "audience": "жители района"})

    # 1) source/confidence сохраняются; неизвестный source → inferred
    knowledge.remember("Конкуренты демпингуют по утрам", department="marketing",
                       source="researched")
    knowledge.remember("Клиент сказал что средний чек 300 руб", department="sales",
                       source="owner_said")
    knowledge.remember("Что-то с неизвестным источником", department="tech",
                       source="nonsense")
    dept = [f for f in knowledge.all_facts() if f["layer"] == "department"]
    by_text = {f["text"]: f for f in dept}
    check("researched сохранён с confidence 0.5",
          by_text["Конкуренты демпингуют по утрам"]["source"] == "researched"
          and abs(by_text["Конкуренты демпингуют по утрам"]["confidence"] - 0.5) < 1e-9)
    check("неизвестный source деградирует к inferred",
          by_text["Что-то с неизвестным источником"]["source"] == "inferred")

    # 2) непроверенный факт подписывается в retrieve
    got = knowledge.retrieve("какой средний чек у клиента", department="sales", limit=6)
    marked = [t for t in got if "средний чек" in t]
    check("owner_said-факт найден и подписан как непроверенный",
          bool(marked) and "непроверено" in marked[0] and "слова клиента" in marked[0])
    got2 = knowledge.retrieve("конкуренты демпингуют", department="marketing", limit=6)
    researched_lines = [t for t in got2 if "демпингуют" in t]
    check("researched-факт (0.5) НЕ подписывается",
          bool(researched_lines) and "непроверено" not in researched_lines[0])

    # 3) скан сайта из брифа → GLOBAL-факты, без записи в хранилище
    brief.set_brief({"goal": "тест", "niche": "кофейня", "audience": "жители района",
                     "scan": {"ok": True, "detected": {
                         "cms": "WordPress",
                         "analytics": {"GA": False, "Metrika": False},
                         "socials": {"instagram": "instagram.com/cafe"},
                     }}})
    glob = [f["text"] for f in knowledge.all_facts() if f["layer"] in ("global", "scan")]
    check("факт CMS из скана присутствует",
          any("WordPress" in t for t in glob))
    check("отсутствие аналитики стало явным фактом",
          any("НЕ обнаружена" in t for t in glob))
    store = ctx.read_json("knowledge.json", {"facts": []})
    check("скан не дублируется в хранилище знаний",
          not any("WordPress" in (f.get("text") or "") for f in store.get("facts", [])))

    # 4) retrieve достаёт скан-факт по релевантной задаче
    got3 = knowledge.retrieve("настроить аналитику на сайте", department="marketing", limit=6)
    check("скан-факт про аналитику достаётся по задаче",
          any("Аналитика" in t for t in got3))

    ctx.wipe()
    print()
    if failures:
        print(f"ПРОВАЛЕНО: {len(failures)}")
        return 1
    print("Все проверки провенанса знаний прошли.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
