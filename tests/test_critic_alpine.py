"""
Юнит-тесты детерминированной проверки Alpine.js-плагинов в critic.check_site()
(порядок скриптов + обязательность плагина под директиву) — реальный кейс
живого прогона: скилл alpine_tailwind_landing сгенерировал сайт с core Alpine
раньше плагина intersect и без плагина collapse вовсе — x-intersect/x-collapse
молча не работали, ни verify_code, ни визуальный обзор HTML этого не ловили.

    python tests/test_critic_alpine.py
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.saas import context as ctx
from src.office import workspace, critic

_ALPINE = '<script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.14.1/dist/cdn.min.js"></script>'
_INTERSECT = '<script defer src="https://cdn.jsdelivr.net/npm/@alpinejs/intersect@3.14.1/dist/cdn.min.js"></script>'
_COLLAPSE = '<script defer src="https://cdn.jsdelivr.net/npm/@alpinejs/collapse@3.14.1/dist/cdn.min.js"></script>'


def _wipe(tid: str):
    ctx.set_tenant(tid)
    ctx.wipe()
    ctx.set_tenant(tid)


def _page(head_scripts: str, body: str) -> str:
    return (f"<!DOCTYPE html><html lang='ru'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width'><title>Т</title>"
            f"{head_scripts}</head><body>{body}"
            f"<form><input name='name'></form>"
            f"<script>fetch('/api/site-lead')</script></body></html>")


def test_flags_plugin_loaded_after_core():
    _wipe("critic_alpine_order")
    html = _page(_ALPINE + _INTERSECT, "<div x-data x-intersect></div>")
    workspace.write_file("site/index.html", html)
    problems = critic.check_site()
    codes = {p["code"] for p in problems}
    assert "alpine_plugin_order" in codes
    _wipe("critic_alpine_order")


def test_flags_missing_collapse_plugin():
    _wipe("critic_alpine_missing")
    html = _page(_INTERSECT + _ALPINE, "<div x-data x-collapse></div>")
    workspace.write_file("site/index.html", html)
    problems = critic.check_site()
    codes = {p["code"] for p in problems}
    assert "alpine_plugin_missing" in codes
    _wipe("critic_alpine_missing")


def test_correct_order_no_problem():
    _wipe("critic_alpine_ok")
    html = _page(_INTERSECT + _COLLAPSE + _ALPINE,
                 "<div x-data x-intersect x-collapse></div>")
    workspace.write_file("site/index.html", html)
    problems = critic.check_site()
    codes = {p["code"] for p in problems}
    assert "alpine_plugin_order" not in codes
    assert "alpine_plugin_missing" not in codes
    _wipe("critic_alpine_ok")


def test_no_alpine_used_no_problem():
    _wipe("critic_alpine_unused")
    html = _page(_ALPINE, "<div x-data x-show='true'></div>")
    workspace.write_file("site/index.html", html)
    problems = critic.check_site()
    codes = {p["code"] for p in problems}
    assert "alpine_plugin_order" not in codes
    assert "alpine_plugin_missing" not in codes
    _wipe("critic_alpine_unused")


def _cleanup():
    for d in ctx.ROOT.glob("critic_alpine_*"):
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
