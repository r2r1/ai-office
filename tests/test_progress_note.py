"""
Тест progress_note — заметка агента о прогрессе внутри задачи, переживающая
переназначение (Корень 8, форензик-аудит прогона 2026-07-18: скилл
«Бренд-бук» перезапускался с нуля 5 раз подряд, потому что каждое повторное
взятие той же задачи не знало, на каком шаге агент уже был).

    python tests/test_progress_note.py
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.saas import context as ctx
from src.office import plan, prompt_builder


def _wipe(tid: str):
    ctx.set_tenant(tid)
    ctx.wipe()
    ctx.set_tenant(tid)


def test_set_progress_note_persists():
    _wipe("progress_note_set")
    t = plan.add_task("Собрать бренд-бук", "designer", project_id="p1")
    assert plan.set_progress_note(t["id"], "Спросил владельца про направление, жду ответ")
    got = plan.get_task(t["id"])
    assert got["progress_note"] == "Спросил владельца про направление, жду ответ"
    _wipe("progress_note_set")


def test_set_progress_note_unknown_task_returns_false():
    _wipe("progress_note_unknown")
    assert plan.set_progress_note("t_does_not_exist", "что угодно") is False
    _wipe("progress_note_unknown")


def test_revert_keeps_progress_note():
    """revert() — это ровно тот момент, когда задача уходит от одного агента
    и может достаться другому (или тому же после паузы) — прогресс ДОЛЖЕН
    пережить именно этот переход."""
    _wipe("progress_note_revert")
    t = plan.add_task("Собрать бренд-бук", "designer", project_id="p1")
    plan.set_progress_note(t["id"], "Зафиксировал 3 кандидата, жду выбор владельца")
    plan.assign(t["id"], "designer_1")
    plan.revert(t["id"])
    got = plan.get_task(t["id"])
    assert got["progress_note"] == "Зафиксировал 3 кандидата, жду выбор владельца"
    _wipe("progress_note_revert")


def test_complete_clears_progress_note():
    _wipe("progress_note_complete")
    t = plan.add_task("Собрать бренд-бук", "designer", project_id="p1")
    plan.set_progress_note(t["id"], "почти готово")
    plan.complete(t["id"])
    got = plan.get_task(t["id"])
    assert got["progress_note"] == ""
    _wipe("progress_note_complete")


def test_unblock_clears_progress_note():
    _wipe("progress_note_unblock")
    t = plan.add_task("Собрать бренд-бук", "designer", project_id="p1")
    plan.set_progress_note(t["id"], "застряло")
    plan.block(t["id"], "не удаётся получить ответ владельца")
    plan.unblock(t["id"])
    got = plan.get_task(t["id"])
    assert got["progress_note"] == ""
    _wipe("progress_note_unblock")


def test_task_context_shows_progress_note_when_set():
    _wipe("progress_note_prompt")
    t = plan.add_task("Собрать бренд-бук", "designer", project_id="p1")
    plan.set_progress_note(t["id"], "Спросил CTO про направление, жду ответ")
    text = prompt_builder.task_context("designer", "Собрать бренд-бук", task_id=t["id"])
    assert "ТВОЙ ПРОГРЕСС" in text
    assert "Спросил CTO про направление, жду ответ" in text
    _wipe("progress_note_prompt")


def test_task_context_no_progress_section_when_empty():
    _wipe("progress_note_prompt_empty")
    t = plan.add_task("Собрать бренд-бук", "designer", project_id="p1")
    text = prompt_builder.task_context("designer", "Собрать бренд-бук", task_id=t["id"])
    assert "ТВОЙ ПРОГРЕСС" not in text
    _wipe("progress_note_prompt_empty")


def _cleanup():
    for d in ctx.ROOT.glob("progress_note_*"):
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
        _cleanup()
    print(f"ВСЕ {passed} ТЕСТОВ ПРОШЛИ")


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    _run()
