"""
Тест персистентности agent_inbox.py — тот же класс бага, что был у
questions.py (см. его докстринг): send() пишет сообщение коллеге в личном
чате, read() коллега читает его при СВОЁМ следующем, произвольно более
позднем чате. Рестарт сервера между send() и read() раньше терял сообщение
молча, без единого следа ни в одном json.

    python tests/test_agent_inbox_persistence.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.saas import context as ctx
from src.office import agent_inbox


def _wipe(tid: str):
    ctx.set_tenant(tid)
    ctx.wipe()
    ctx.set_tenant(tid)
    agent_inbox._loaded.discard(tid)
    agent_inbox._inboxes.pop(tid, None)


def _simulate_restart(tid: str):
    agent_inbox._inboxes.pop(tid, None)
    agent_inbox._loaded.discard(tid)


def test_send_persists_to_disk():
    tid = "inbox_persist_send"
    _wipe(tid)
    agent_inbox.send("developer_1", "orchestrator_1", "Проверь плагин оплаты")
    data = ctx.read_json("agent_inbox.json", {})
    assert data.get("developer_1") == [{"from": "orchestrator_1", "text": "Проверь плагин оплаты"}]
    _wipe(tid)


def test_message_survives_restart_before_read():
    tid = "inbox_persist_restart"
    _wipe(tid)
    agent_inbox.send("developer_1", "orchestrator_1", "Уточни сроки")
    _simulate_restart(tid)
    msgs = agent_inbox.read("developer_1")
    assert msgs == [{"from": "orchestrator_1", "text": "Уточни сроки"}]
    _wipe(tid)


def test_read_clears_inbox_and_persists_the_clear():
    tid = "inbox_persist_clear"
    _wipe(tid)
    agent_inbox.send("developer_1", "orchestrator_1", "Первое")
    agent_inbox.read("developer_1")
    _simulate_restart(tid)
    assert agent_inbox.read("developer_1") == []
    data = ctx.read_json("agent_inbox.json", {})
    assert "developer_1" not in data
    _wipe(tid)


def test_multiple_messages_accumulate_across_restart():
    tid = "inbox_persist_multi"
    _wipe(tid)
    agent_inbox.send("developer_1", "orchestrator_1", "Раз")
    _simulate_restart(tid)
    agent_inbox.send("developer_1", "marketer_1", "Два")
    msgs = agent_inbox.read("developer_1")
    assert [m["text"] for m in msgs] == ["Раз", "Два"]
    _wipe(tid)


def test_tenants_are_isolated():
    _wipe("inbox_persist_tenant_a")
    _wipe("inbox_persist_tenant_b")
    ctx.set_tenant("inbox_persist_tenant_a")
    agent_inbox.send("developer_1", "orchestrator_1", "A-сообщение")
    ctx.set_tenant("inbox_persist_tenant_b")
    assert agent_inbox.read("developer_1") == []
    ctx.set_tenant("inbox_persist_tenant_a")
    assert len(agent_inbox.read("developer_1")) == 1
    _wipe("inbox_persist_tenant_a")
    _wipe("inbox_persist_tenant_b")


def _cleanup():
    import shutil
    for d in ctx.ROOT.glob("inbox_persist_*"):
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
