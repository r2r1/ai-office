"""
Юнит-тесты per-project Specification (src/office/specification.py) —
реальный кейс из лога прогона 2026-07-09: второй параллельный проект
(принятая инициатива) получал 100% задач с warning "работа вне
согласованного объёма", потому что спецификация была ОДНА на тенанта,
собранная из задач первого проекта. Теперь у каждого Work — свой контракт.

    python tests/test_specification.py
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.saas import context as ctx
from src.office import specification, plan, projects, brief


def _fresh(name: str) -> None:
    ctx.set_tenant(name)
    ctx.wipe()
    ctx.set_tenant(name)
    brief.set_brief({"goal": "тестовая цель", "niche": "тест", "audience": "тест"})


def test_ensure_builds_spec_from_own_project_tasks_only():
    _fresh("spec_test_isolation")
    p1 = projects.create("Проект 1", "цель 1")
    p2 = projects.create("Проект 2", "цель 2")
    plan.add_task("Задача проекта 1", "developer", "критерий 1", project_id=p1["id"])
    plan.add_task("Задача проекта 2", "marketer", "критерий 2", project_id=p2["id"])

    spec1 = specification.ensure(p1["id"])
    spec2 = specification.ensure(p2["id"])

    assert spec1["success_criteria"] == ["критерий 1"]
    assert spec2["success_criteria"] == ["критерий 2"]


def test_covers_checks_against_own_project_spec_not_others():
    _fresh("spec_test_covers")
    p1 = projects.create("Проект 1", "цель 1")
    p2 = projects.create("Проект 2", "цель 2")
    plan.add_task("Задача 1", "developer", "Собрать лендинг с формой заявки", project_id=p1["id"])
    plan.add_task("Задача 2", "marketer", "Написать 2 продуктовых пакета", project_id=p2["id"])
    specification.ensure(p1["id"])
    specification.ensure(p2["id"])

    # Критерий проекта 2 покрыт ЕГО спекой...
    assert specification.covers("Написать 2 продуктовых пакета", p2["id"])
    # ...но НЕ спекой проекта 1 (разный объём работы — раньше это не проверялось,
    # реальный кейс: 100% задач второго проекта получали ложный warning)
    assert not specification.covers("Написать 2 продуктовых пакета", p1["id"])


def test_confirm_only_affects_its_own_project():
    _fresh("spec_test_confirm")
    p1 = projects.create("Проект 1", "цель 1")
    p2 = projects.create("Проект 2", "цель 2")
    plan.add_task("Задача 1", "developer", "критерий 1", project_id=p1["id"])
    plan.add_task("Задача 2", "marketer", "критерий 2", project_id=p2["id"])
    specification.ensure(p1["id"])
    specification.ensure(p2["id"])

    specification.confirm("ok", p1["id"])

    assert specification.status(p1["id"]) == "confirmed"
    assert specification.status(p2["id"]) == "draft"  # второй проект не затронут


def test_all_specs_lists_every_project():
    _fresh("spec_test_all")
    p1 = projects.create("Проект 1", "цель 1")
    p2 = projects.create("Проект 2", "цель 2")
    plan.add_task("Задача 1", "developer", "критерий 1", project_id=p1["id"])
    plan.add_task("Задача 2", "marketer", "критерий 2", project_id=p2["id"])
    specification.ensure(p1["id"])
    specification.ensure(p2["id"])

    all_specs = specification.all_specs()
    assert set(all_specs.keys()) == {p1["id"], p2["id"]}


def test_ensure_idempotent_per_project():
    _fresh("spec_test_idempotent")
    p1 = projects.create("Проект 1", "цель 1")
    plan.add_task("Задача 1", "developer", "критерий 1", project_id=p1["id"])
    first = specification.ensure(p1["id"])
    plan.add_task("Задача добавлена позже", "marketer", "критерий 2", project_id=p1["id"])
    second = specification.ensure(p1["id"])
    # Повторный ensure() не перестраивает уже существующий контракт
    assert first == second
    assert second["success_criteria"] == ["критерий 1"]


def test_default_project_id_uses_active_project():
    _fresh("spec_test_default")
    p1 = projects.ensure_active()
    plan.add_task("Задача 1", "developer", "критерий 1", project_id=p1["id"])
    spec_explicit = specification.ensure(p1["id"])
    spec_default = specification.get()  # без project_id — активный проект
    assert spec_default["success_criteria"] == spec_explicit["success_criteria"]


def _cleanup_test_tenants() -> None:
    for d in ctx.ROOT.glob("spec_test_*"):
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)


def _run():
    passed = 0
    try:
        for name, fn in sorted(globals().items()):
            if name.startswith("test_") and callable(fn):
                fn()
                print(f"  ✓ {name}")
                passed += 1
    finally:
        _cleanup_test_tenants()
    print(f"ВСЕ {passed} ТЕСТОВ ПРОШЛИ")


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    _run()
