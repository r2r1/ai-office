"""
Юнит-тесты дедупликации повторяющихся процессов (src/office/processes.py) —
реальный кейс из лога прогона 2026-07-09: salesman завёл ПЯТЬ отдельных
процессов "Лидогенерация и продажи внедрения ИИ-агентов" за один прогон,
каждый тикал каждый цикл независимо, впустую тратя бюджет.

    python tests/test_processes.py
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.saas import context as ctx
from src.office import processes


def _fresh(name: str) -> None:
    ctx.set_tenant(name)
    ctx.wipe()
    ctx.set_tenant(name)


def test_exact_duplicate_title_is_deduped():
    _fresh("proc_test_exact_dup")
    p1 = processes.create("Лидогенерация и продажи внедрения ИИ-агентов", "salesman",
                          "Искать лиды", project_id="p1")
    p2 = processes.create("Лидогенерация и продажи внедрения ИИ-агентов", "salesman",
                          "Искать лиды в LinkedIn", project_id="p1")
    assert p2.get("_deduped") is True
    assert p2["id"] == p1["id"]
    assert len(processes.all_processes()) == 1


def test_reworded_similar_title_is_still_deduped():
    _fresh("proc_test_reworded")
    processes.create("Лидогенерация и продажи внедрения ИИ-агентов", "salesman",
                     "Искать лиды", project_id="p1")
    p2 = processes.create("Лидогенерация и продажи внедрения ИИ-агентов для SMB", "salesman",
                          "Искать лиды в LinkedIn по критериям", project_id="p1")
    assert p2.get("_deduped") is True
    assert len(processes.all_processes()) == 1


def test_different_role_is_not_deduped():
    _fresh("proc_test_diff_role")
    processes.create("Лидогенерация", "salesman", "Искать лиды", project_id="p1")
    p2 = processes.create("Лидогенерация", "marketer", "Публиковать посты", project_id="p1")
    assert not p2.get("_deduped")
    assert len(processes.all_processes()) == 2


def test_different_project_is_not_deduped():
    _fresh("proc_test_diff_project")
    processes.create("Лидогенерация и продажи", "salesman", "Искать лиды", project_id="p1")
    p2 = processes.create("Лидогенерация и продажи", "salesman", "Искать лиды", project_id="p2")
    assert not p2.get("_deduped")
    assert len(processes.all_processes()) == 2


def test_unrelated_title_is_not_deduped():
    _fresh("proc_test_unrelated")
    processes.create("Лидогенерация и продажи внедрения ИИ-агентов", "salesman",
                     "Искать лиды", project_id="p1")
    p2 = processes.create("Еженедельный контент-план", "salesman",
                          "Публиковать посты", project_id="p1")
    assert not p2.get("_deduped")
    assert len(processes.all_processes()) == 2


def test_paused_process_does_not_block_new_one():
    _fresh("proc_test_paused")
    p1 = processes.create("Лидогенерация", "salesman", "Искать лиды", project_id="p1")
    processes.set_status(p1["id"], "paused")
    p2 = processes.create("Лидогенерация", "salesman", "Искать лиды", project_id="p1")
    assert not p2.get("_deduped")  # старый процесс на паузе — не считается активным дублем
    assert len(processes.all_processes()) == 2


def _cleanup_test_tenants() -> None:
    for d in ctx.ROOT.glob("proc_test_*"):
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
