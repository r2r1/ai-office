"""
Переключатель "boost" (docs/product-portrait-2026-07-19.md §11) — НЕ то же
самое, что growth_style: growth_style — КАК офис растёт, boost — растит ли
офис сам ВООБЩЕ без запроса. Гейт применения (planning_engine.py «Блок 4») —
оркестрация с LLM-вызовами, тестируется только живым прогоном (см. докстринг
planning_engine.py: «поведенчески тестируются только живым прогоном»). Здесь —
единственная изолированно проверяемая часть: сам флаг, независимый от
growth_style, с правильным дефолтом.

    python tests/test_philosophy_boost.py
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
    ctx.set_tenant(name)
    ctx.wipe()
    ctx.set_tenant(name)


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(("[ok] " if cond else "[FAIL] ") + name)
        if not cond:
            failures.append(name)

    _fresh("philosophy_boost_test")
    from src.office import philosophy

    # 1) Дефолт — boost=True, независимо от того, что growth_style по умолчанию "stable"
    d = philosophy.load()
    check("дефолт boost=True", d["boost"] is True)
    check("дефолт growth_style='stable' (не путать с boost)", d["growth_style"] == "stable")

    # 2) Изменение growth_style НЕ трогает boost — независимые поля
    philosophy.save({"growth_style": "aggressive"})
    d2 = philosophy.load()
    check("growth_style сохранился отдельно", d2["growth_style"] == "aggressive")
    check("boost НЕ изменился от смены growth_style", d2["boost"] is True)

    # 3) boost можно выключить независимо, growth_style не трогается
    philosophy.save({"boost": False})
    d3 = philosophy.load()
    check("boost=False сохранился", d3["boost"] is False)
    check("growth_style не изменился при смене boost", d3["growth_style"] == "aggressive")

    # 4) boost участвует в is_set()? — не должен один менять "философия задана"
    #    (is_set() смотрит на mission/success_means/growth_style!=stable — boost
    #    не входит туда осознанно, режим поддержания сам по себе не "философия")
    _fresh("philosophy_boost_isset_test")
    from src.office import philosophy as philosophy2
    philosophy2.save({"boost": False})
    check("одно только boost=False не включает is_set()", not philosophy2.is_set())

    ctx.wipe()
    print()
    if failures:
        print(f"ПРОВАЛЕНО: {len(failures)}")
        return 1
    print("Все проверки boost-переключателя прошли.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
