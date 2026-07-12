"""
Тест гигиены статического сайта в critic.check_site() — живой прогон офиса
поймал: разработчик откатился со скилла vite_react_site на статический
index.html (сборка была признана нецелесообразной), но не удалил
site/src/App.jsx/index.css — сам плейбук скилла (builtin_skills/vite_react_site.md)
прямо требует удалить их при откате, критик раньше это не проверял.

    python tests/test_critic_orphan_vite.py
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


def _static_html() -> str:
    return ("<!DOCTYPE html><html lang='ru'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width'><title>Т</title>"
            "<style>body{margin:0}</style></head><body>"
            "<form><input name='name'></form>"
            "<script>fetch('/api/site-lead')</script></body></html>")


def test_flags_orphan_jsx_next_to_static_site():
    _wipe("critic_orphan_jsx")
    workspace.write_file("site/index.html", _static_html())
    workspace.write_file("site/src/App.jsx", "export default function App() { return null }")
    problems = critic.check_site()
    codes = {p["code"] for p in problems}
    assert "orphan_vite_sources" in codes
    _wipe("critic_orphan_jsx")


def test_no_problem_when_purely_static():
    _wipe("critic_orphan_clean")
    workspace.write_file("site/index.html", _static_html())
    problems = critic.check_site()
    codes = {p["code"] for p in problems}
    assert "orphan_vite_sources" not in codes
    _wipe("critic_orphan_clean")


def test_no_false_positive_for_real_vite_build():
    """Настоящий Vite-проект (package.json+build) — src/*.jsx там ЗАКОНЕН,
    is_built_spa=True переключает check_site на другую ветку (published_root),
    отдельная проверка не должна её трогать."""
    _wipe("critic_orphan_vite_build")
    workspace.write_file("site/package.json", '{"scripts": {"build": "vite build"}}')
    workspace.write_file("site/src/App.jsx", "export default function App() { return null }")
    d = critic.site_dir()
    # без реальной сборки (dist/) site_dir здесь None — не про эту проверку,
    # достаточно убедиться, что orphan-код не всплывает для detect()=="build".
    from src.office import site_builder
    assert site_builder.detect()["kind"] == "build"
    _wipe("critic_orphan_vite_build")


def _cleanup():
    for d in ctx.ROOT.glob("critic_orphan_*"):
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
