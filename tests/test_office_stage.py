"""
Office Stage — визуальная проекция роста офиса (docs/product-portrait-2026-07-19.md
§10): чистая функция от уже существующих чисел, 0 нового хранилища. Проверяем
пороги стадий и что стадия действительно растёт с командой/отделами/доверием.

    python tests/test_office_stage.py
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

    _fresh("office_stage_test")
    from src.office import office_stage, org, registry, autonomy, trust

    # 1) Пустой офис — стадия 0, ничего не хранится (повторный вызов не меняет ответ)
    s0 = office_stage.stage()
    check("пустой офис — стадия 0", s0["level"] == 0)
    check("stage() детерминирована (два вызова подряд равны)", office_stage.stage() == s0)

    # 2) Нанят агент, но отделов нет — стадия 1 (комната)
    registry.register("developer_1", "developer")
    s1 = office_stage.stage()
    check("есть команда, нет отделов — стадия 1", s1["level"] == 1)
    check("team_size отражает реальный registry", s1["team_size"] == 1)

    # 3) Один отдел открыт — стадия 2
    org.open_department("tech", reason="test")
    s2 = office_stage.stage()
    check("один открытый отдел — стадия 2", s2["level"] == 2)
    check("rooms содержит id открытого отдела", "tech" in s2["rooms"])

    # 4) Два отдела, низкое доверие/автономия — стадия 3
    org.open_department("sales", reason="test")
    s3 = office_stage.stage()
    check("два отдела, дефолтные доверие/автономия — стадия 3", s3["level"] == 3)

    # 5) Высокая автономия ИЛИ высокое доверие на той же структуре — стадия 4
    autonomy.set_level("trusted")
    s4 = office_stage.stage()
    check("два отдела + trusted-автономия — стадия 4 (интерьер дозрел)", s4["level"] == 4)

    # 6) Ничего не пишет в постоянное хранилище сверх уже существующих модулей —
    #    world.snapshot() подхватывает то же значение без расхождений (CQRS).
    from src.office import world
    world.invalidate_cache()
    snap = world.snapshot()
    check("world.snapshot()['business_state']['office_stage'] совпадает с office_stage.stage()",
          snap["business_state"]["office_stage"] == office_stage.stage())

    ctx.wipe()
    print()
    if failures:
        print(f"ПРОВАЛЕНО: {len(failures)}")
        return 1
    print("Все проверки office_stage прошли.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
