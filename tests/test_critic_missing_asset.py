"""
Тест проверки локальных ассетов в critic.check_site() — форензик-аудит прогона
2026-07-18 («Кухни на заказ КМВ») нашёл сайт, опубликованный с
<link rel="stylesheet" href="styles.css">, а файла styles.css нигде не было —
страница уходила клиенту полностью без стилей, и ни одна проверка (только
целостность .html-ссылок) этого не ловила.

    python tests/test_critic_missing_asset.py
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.saas import context as ctx
from src.office import workspace, critic


def _wipe(tid: str):
    ctx.set_tenant(tid)
    ctx.wipe()
    ctx.set_tenant(tid)


def _html(head_extra: str) -> str:
    return ("<!DOCTYPE html><html lang='ru'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width'><title>Т</title>"
            f"{head_extra}</head><body>"
            "<form><input name='name'></form>"
            "<script>fetch('/api/site-lead')</script></body></html>")


def test_flags_missing_local_stylesheet():
    _wipe("critic_missing_css")
    workspace.write_file("site/index.html", _html('<link rel="stylesheet" href="styles.css">'))
    problems = critic.check_site()
    codes = {p["code"] for p in problems}
    assert "missing_asset" in codes
    _wipe("critic_missing_css")


def test_no_problem_when_stylesheet_exists():
    _wipe("critic_present_css")
    workspace.write_file("site/index.html", _html('<link rel="stylesheet" href="styles.css">'))
    workspace.write_file("site/styles.css", "body{margin:0}")
    problems = critic.check_site()
    codes = {p["code"] for p in problems}
    assert "missing_asset" not in codes
    _wipe("critic_present_css")


def test_external_stylesheet_not_flagged():
    """Внешние (http/https) ссылки — не наша забота, отдельная проверка (external_images
    для картинок) уже покрывает похожий случай; CDN-css/js — законный паттерн."""
    _wipe("critic_external_css")
    workspace.write_file("site/index.html",
                         _html('<link rel="stylesheet" href="https://cdn.example.com/x.css">'))
    problems = critic.check_site()
    codes = {p["code"] for p in problems}
    assert "missing_asset" not in codes
    _wipe("critic_external_css")


def test_flags_missing_local_script():
    _wipe("critic_missing_js")
    workspace.write_file("site/index.html", _html('<script src="app.js"></script>'))
    problems = critic.check_site()
    codes = {p["code"] for p in problems}
    assert "missing_asset" in codes
    _wipe("critic_missing_js")


def _cleanup():
    for d in ctx.ROOT.glob("critic_missing_*"):
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)
    for d in ctx.ROOT.glob("critic_present_*"):
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)
    for d in ctx.ROOT.glob("critic_external_*"):
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
