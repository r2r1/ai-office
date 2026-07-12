"""
Тесты каталога готовых MCP-коннекторов (office/mcp_connectors.py) — растущая
без правки кода коллекция рецептов (по образцу builtin_skills), решает найденный
живым разговором кейс: без каталога модель сама выдумывала неверный npm-пакет
для Postiz вместо реального stdio↔SSE моста mcp-remote на удалённый эндпоинт.

    python tests/test_mcp_connectors.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.office import mcp_connectors


def test_postiz_loaded_from_builtin_dir():
    c = mcp_connectors.get("postiz")
    assert c is not None
    assert c.command == "npx"
    assert "mcp-remote" in c.args_template
    assert any(n["key"] == "POSTIZ_URL" for n in c.needs)
    assert any(n["key"] == "POSTIZ_API_KEY" for n in c.needs)
    assert c.allow_network is True


def test_match_finds_postiz_by_synonym():
    results = mcp_connectors.match("нужен кроспостинг в соцсети")
    assert any(c.id == "postiz" for c in results)


def test_match_returns_empty_for_unrelated_query():
    results = mcp_connectors.match("совершенно не связанный запрос про бухгалтерию xyz123")
    assert all(c.id != "postiz" for c in results)


def test_resolve_substitutes_placeholders():
    c = mcp_connectors.get("postiz")
    args, missing = c.resolve({"POSTIZ_URL": "http://host:4007", "POSTIZ_API_KEY": "secret"})
    assert missing == []
    assert "http://host:4007/mcp/secret" in args


def test_resolve_reports_missing_values():
    c = mcp_connectors.get("postiz")
    args, missing = c.resolve({"POSTIZ_URL": "http://host:4007"})
    assert "POSTIZ_API_KEY" in missing


def test_parse_md_rejects_missing_id_or_title():
    assert mcp_connectors._parse_md("---\ncommand: npx\n---\nbody") is None
    assert mcp_connectors._parse_md("no frontmatter at all") is None


def _run():
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ✓ {name}")
            passed += 1
    print(f"ВСЕ {passed} ТЕСТОВ ПРОШЛИ")


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    _run()
