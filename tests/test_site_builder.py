"""
Unit-тесты Site Builder — детект/кеш/гейт БЕЗ реального npm (сборка проверяется
отдельным живым смоуком). Запуск:

    python tests/test_site_builder.py
"""

import os
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.office import site_builder as sb
from src.office import workspace, critic
from src.saas import context as ctx, context


def _wipe(tid: str):
    ctx.set_tenant(tid)
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


def test_detect_static_vs_build_vs_none():
    ctx.set_tenant("sb_detect")
    assert sb.detect()["kind"] == "none"
    workspace.write_file("site/index.html", "<html><body>hi</body></html>")
    assert sb.detect() == {"kind": "static", "root": "site"}
    workspace.write_file("site/package.json", '{"scripts": {"build": "vite build"}}')
    assert sb.detect() == {"kind": "build", "root": "site"}
    # package.json БЕЗ build-скрипта — не сборочный проект, остаёмся статикой
    workspace.write_file("site/package.json", '{"name": "x"}')
    assert sb.detect()["kind"] == "static"
    _wipe("sb_detect")


def test_list_files_ignores_node_modules():
    ctx.set_tenant("sb_ignore")
    workspace.write_file("site/index.html", "<html></html>")
    workspace.write_file("site/node_modules/react/index.js", "module.exports={}")
    workspace.write_file("site/.vite/cache.json", "{}")
    paths = {f["path"] for f in workspace.list_files()}
    assert "site/index.html" in paths
    assert not any("node_modules" in p or ".vite" in p for p in paths), paths
    _wipe("sb_ignore")


def test_fingerprint_ignores_out_dir():
    ctx.set_tenant("sb_fp")
    workspace.write_file("site/package.json", '{"scripts": {"build": "vite build"}}')
    workspace.write_file("site/src/main.js", "console.log(1)")
    fp1 = sb._src_fingerprint("site")
    time.sleep(0.05)
    # Появление ВЫХОДА сборки не должно менять отпечаток исходников
    workspace.write_file("site/dist/index.html", "<html>built</html>")
    assert sb._src_fingerprint("site") == fp1
    time.sleep(0.05)
    workspace.write_file("site/src/main.js", "console.log(2)")
    assert sb._src_fingerprint("site") > fp1
    _wipe("sb_fp")


def test_gate_disabled_gives_actionable_problem():
    ctx.set_tenant("sb_gate")
    os.environ["ALLOW_SITE_BUILD"] = "0"
    try:
        workspace.write_file("site/package.json", '{"scripts": {"build": "vite build"}}')
        workspace.write_file("site/index.html", "<html>entry</html>")
        import asyncio
        res = asyncio.run(sb.ensure_built())
        assert res["kind"] == "build" and res["ok"] is False
        assert "отключена оператором" in res["reason"]
        # Приёмка/критик видят структурную critical-проблему с ПОНЯТНЫМ выходом
        prob = sb.cached_problem()
        assert prob and prob["severity"] == "critical" and prob["code"] == "build_disabled"
        assert "React + Vite + Framer Motion" in prob["text"]  # агенту предложен путь деградации (в скилле)
        # published_root: публиковать нечего (исходники Vite — не сайт)
        assert sb.published_root() is None
        # критик отдаёт её первой критической проблемой
        site_problems = critic.check_site()
        assert site_problems and site_problems[0]["code"] == "build_disabled"
        assert critic.is_critical(site_problems[0])
    finally:
        os.environ.pop("ALLOW_SITE_BUILD", None)
    _wipe("sb_gate")


def test_static_project_is_noop():
    ctx.set_tenant("sb_static")
    workspace.write_file(
        "site/index.html",
        "<html lang='ru'><head><title>x</title><meta name='viewport' content='w'>"
        "<style>a{}</style></head><body><form action='/api/site-lead' method='post'>"
        "<input name='contact'><button>OK</button></form>" + "текст " * 60 + "</body></html>")
    import asyncio
    res = asyncio.run(sb.ensure_built())
    assert res["ok"] is True and res["kind"] == "static"
    assert sb.published_root() == "site"
    assert sb.cached_problem() is None
    assert critic.site_dir() == "site"  # статика — прежнее поведение не сломано
    _wipe("sb_static")


def test_published_root_uses_fresh_build_cache():
    ctx.set_tenant("sb_cache")
    workspace.write_file("site/package.json", '{"scripts": {"build": "vite build"}}')
    workspace.write_file("site/index.html", "<html>entry</html>")
    workspace.write_file("site/dist/index.html", "<html>built output</html>")
    fp = sb._src_fingerprint("site")
    # Эмулируем успешную сборку, актуальную для текущих исходников
    context.write_json("site_build.json",
                       {"ok": True, "out_dir": "site/dist", "fingerprint": fp,
                        "ts": time.time(), "log_tail": "", "reason": ""})
    assert sb.published_root() == "site/dist"
    assert sb.cached_problem() is None
    assert critic.site_dir() == "site/dist"  # критик смотрит на ВЫХОД сборки
    # Исходники изменились → кеш устарел → публиковать нечего до пересборки
    time.sleep(0.05)
    workspace.write_file("site/src/App.jsx", "export default () => null")
    assert sb.published_root() is None
    prob = sb.cached_problem()
    assert prob and prob["code"] == "build_pending" and prob["severity"] == "cosmetic"
    _wipe("sb_cache")


def _run():
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ✓ {name}")
            passed += 1
    print(f"ВСЕ {passed} ТЕСТОВ ПРОШЛИ")


if __name__ == "__main__":
    # Windows-консоль часто в cp1251 — "✓" ронял ЛЮБОЙ тест этого файла
    # UnicodeEncodeError ДО единой строки реального результата (found: весь
    # набор tests/*.py был непроверяем из этой сессии на Windows).
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    _run()
