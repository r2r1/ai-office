"""
Тест персистентности offset в bot_runtime.py — тот же класс бага, что был у
questions.py/agent_inbox.py (см. докстринг модуля): рестарт сервера сбрасывал
offset на 0, Telegram getUpdates(offset=0) заново отдавал старые апдейты —
дублирующаяся обработка уже обработанных сообщений.

    python tests/test_bot_runtime_offset.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.saas import context as ctx
from src.office import bot_runtime


def _wipe(tid: str):
    ctx.set_tenant(tid)
    ctx.wipe()
    ctx.set_tenant(tid)
    bot_runtime._loaded.discard(tid)
    bot_runtime._offsets.pop(tid, None)


def _simulate_restart(tid: str):
    bot_runtime._offsets.pop(tid, None)
    bot_runtime._loaded.discard(tid)


def test_fresh_tenant_offset_is_zero():
    tid = "bot_offset_fresh"
    _wipe(tid)
    assert bot_runtime._load_offset(tid) == 0
    _wipe(tid)


def test_save_persists_to_disk():
    tid = "bot_offset_save"
    _wipe(tid)
    bot_runtime._save_offset(tid, 42)
    data = ctx.read_json("bot_offset.json", {})
    assert data.get("offset") == 42
    _wipe(tid)


def test_offset_survives_restart():
    tid = "bot_offset_restart"
    _wipe(tid)
    bot_runtime._save_offset(tid, 777)
    _simulate_restart(tid)
    assert bot_runtime._load_offset(tid) == 777, "рестарт не должен сбрасывать offset на 0"
    _wipe(tid)


def test_tenants_are_isolated():
    _wipe("bot_offset_tenant_a")
    _wipe("bot_offset_tenant_b")
    ctx.set_tenant("bot_offset_tenant_a")
    bot_runtime._save_offset("bot_offset_tenant_a", 10)
    ctx.set_tenant("bot_offset_tenant_b")
    assert bot_runtime._load_offset("bot_offset_tenant_b") == 0
    _wipe("bot_offset_tenant_a")
    _wipe("bot_offset_tenant_b")


def _cleanup():
    import shutil
    for d in ctx.ROOT.glob("bot_offset_*"):
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
