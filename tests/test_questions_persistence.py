"""
Тест персистентности вопросов (questions.py) — форензик-аудит живого прогона
2026-07-18: рестарт сервера во время открытого ask_user убивал live future,
но thread.json уже показал вопрос владельцу под конкретным question_id.
Следующая попытка того же гейта плодила ДРУГОЙ id, а старый вечно висел
«неотвеченным»; ответ владельца на старый id уходил не туда.

    python tests/test_questions_persistence.py
"""

import asyncio
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.saas import context as ctx
from src.office import questions


def _wipe(tid: str):
    ctx.set_tenant(tid)
    ctx.wipe()
    ctx.set_tenant(tid)
    questions._loaded.discard(tid)
    questions._pending.pop(tid, None)
    questions._meta.pop(tid, None)
    questions._by_text.pop(tid, None)


def _simulate_restart(tid: str):
    """Живые future этого тенанта пропадают (новый процесс), но модуль ещё
    не тронут — как будто это первое обращение к нему после рестарта."""
    questions._pending.pop(tid, None)
    questions._meta.pop(tid, None)
    questions._by_text.pop(tid, None)
    questions._loaded.discard(tid)


async def test_meta_persists_to_disk():
    tid = "q_persist_meta"
    _wipe(tid)
    qid, fut = questions.ask("Опубликовать сайт?", agent_id="orchestrator_1")
    data = ctx.read_json("questions.json", {})
    assert qid in data.get("pending", {})
    assert data["pending"][qid]["text"] == "Опубликовать сайт?"
    _wipe(tid)


async def test_restart_reopens_same_qid_not_a_duplicate():
    tid = "q_persist_restart"
    _wipe(tid)
    qid1, fut1 = questions.ask("Стиль подобран автоматически — опубликовать?", agent_id="orchestrator_1")
    _simulate_restart(tid)
    qid2, fut2 = questions.ask("Стиль подобран автоматически — опубликовать?", agent_id="orchestrator_1")
    assert qid2 == qid1, "рестарт не должен плодить новый id для того же вопроса"
    assert fut2 is not fut1
    assert not fut2.done()
    _wipe(tid)


async def test_answer_after_restart_unblocks_new_future():
    tid = "q_persist_answer"
    _wipe(tid)
    qid1, fut1 = questions.ask("Публиковать как есть?", agent_id="orchestrator_1")
    _simulate_restart(tid)
    qid2, fut2 = questions.ask("Публиковать как есть?", agent_id="orchestrator_1")
    ok = questions.answer(qid2, "да")
    assert ok is True
    assert fut2.done() and fut2.result() == "да"
    assert questions.pending_for("orchestrator_1") == ""
    _wipe(tid)


async def test_answer_orphaned_question_still_clears_pending():
    """Рестарт случился, а гейт больше НЕ ретраился (ask() второй раз не звали) —
    запись осталась только в meta, живого future нет вообще. answer() всё
    равно обязана снять её из pending, иначе она висит вечно."""
    tid = "q_persist_orphan"
    _wipe(tid)
    qid, _fut = questions.ask("Вопрос без ретрая", agent_id="orchestrator_1")
    _simulate_restart(tid)
    questions._ensure_loaded(tid)  # только meta, без live future — как после рестарта
    ok = questions.answer(qid, "да")
    assert ok is True
    assert questions.list_pending() == []
    _wipe(tid)


def _cleanup():
    for d in ctx.ROOT.glob("q_persist_*"):
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)


def _run():
    passed = 0
    try:
        for name, fn in sorted(globals().items()):
            if name.startswith("test_") and callable(fn):
                asyncio.run(fn())
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
