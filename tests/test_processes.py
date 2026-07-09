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
from src.office import processes, plan, events, brief


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


# ── tick() + авто-пауза на повторяющемся блокере ───────────────────────────
# Реальный кейс из лога прогона 2026-07-09: процесс лидогенерации 92 цикла
# подряд натыкался на один и тот же блокер ("нет LinkedIn-лидов"), сигнал CEO
# поднимался один раз (дедуп Event Layer сработал верно), но САМ процесс
# продолжал тикать вхолостую каждый цикл без остановки.

def _close_process_task(role: str) -> None:
    """Закрывает текущую задачу процесса (как это делает Acceptance после
    сдачи) — иначе следующий tick() увидит её как pending и не создаст новую."""
    for t in plan.all_tasks():
        if t.get("role") == role and t.get("status") in ("pending", "in_progress"):
            plan.mark(t["id"], "done")


def test_tick_creates_task_then_dedups_while_pending():
    _fresh("proc_test_tick_dedup")
    brief.set_brief({"goal": "тест"})
    processes.create("Лидогенерация", "salesman", "Искать лиды", project_id="")
    r1 = processes.tick()
    assert len(r1["created"]) == 1
    r2 = processes.tick()  # предыдущая задача ещё не закрыта — новую не создаёт
    assert len(r2["created"]) == 0


def test_tick_pauses_after_consecutive_blockers():
    _fresh("proc_test_tick_pause")
    brief.set_brief({"goal": "тест"})
    proc = processes.create("Лидогенерация", "salesman", "Искать лиды", project_id="")

    for i in range(processes.BLOCKER_PAUSE_THRESHOLD):
        r = processes.tick()
        assert r["paused"] == []  # ещё не достигли порога
        assert len(r["created"]) == 1
        _close_process_task("salesman")
        events.raise_event("blocker", "Нет актуальных LinkedIn-лидов для outreach",
                           from_role="salesman")

    r_final = processes.tick()
    assert len(r_final["paused"]) == 1
    assert r_final["paused"][0]["id"] == proc["id"]
    assert processes.get(proc["id"])["status"] == "paused"
    # На паузе — новых задач для него больше не ставим
    assert r_final["created"] == []


def test_tick_resets_blocker_streak_on_success():
    _fresh("proc_test_tick_reset")
    brief.set_brief({"goal": "тест"})
    processes.create("Лидогенерация", "salesman", "Искать лиды", project_id="")

    # Один блокер, потом успешный цикл без блокера — счётчик должен сброситься
    processes.tick()
    _close_process_task("salesman")
    events.raise_event("blocker", "Нет лидов", from_role="salesman")

    processes.tick()  # видит блокер прошлого запуска → consecutive_blockers=1
    _close_process_task("salesman")  # успешно закрыт, БЕЗ нового блокера

    r = processes.tick()
    assert r["paused"] == []
    all_procs = processes.all_processes()
    assert all_procs[0]["consecutive_blockers"] == 0


def test_tick_ignores_blocker_from_different_role():
    _fresh("proc_test_tick_other_role")
    brief.set_brief({"goal": "тест"})
    processes.create("Лидогенерация", "salesman", "Искать лиды", project_id="")

    for _ in range(processes.BLOCKER_PAUSE_THRESHOLD + 1):
        processes.tick()
        _close_process_task("salesman")
        events.raise_event("blocker", "Не связано с этим процессом", from_role="marketer")

    r = processes.tick()
    assert r["paused"] == []  # блокер от другой роли не считается


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
