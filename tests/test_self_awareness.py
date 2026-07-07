"""
Юнит-тесты Platform Self-Knowledge, узкая версия (BOS §6.1, src/office/
self_awareness.py) — агент видит СВОЮ роль/скилл/список СВОИХ инструментов,
без доступа к исходному коду платформы.

    python tests/test_self_awareness.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.office import self_awareness


def test_describe_includes_role():
    text = self_awareness.describe("developer", ["write_file", "read_file"])
    assert "developer" in text


def test_describe_includes_all_tool_names():
    tools = ["write_file", "read_file", "describe_self"]
    text = self_awareness.describe("designer", tools)
    for t in tools:
        assert t in text


def test_describe_includes_skill_when_given():
    text = self_awareness.describe("developer", ["write_file"], skill="vite_react_site")
    assert "vite_react_site" in text


def test_describe_omits_skill_line_when_absent():
    text = self_awareness.describe("developer", ["write_file"])
    assert "Активный скилл" not in text


def test_describe_includes_department_when_given():
    text = self_awareness.describe("developer", ["write_file"], department="tech")
    assert "tech" in text


def test_describe_does_not_expose_platform_source_paths():
    """Регресс: узкая версия self-awareness НЕ должна упоминать доступ к
    исходникам платформы (auth.py/crypto.py и т.п.) — только к своей роли/тулам."""
    text = self_awareness.describe("architect", ["write_file"])
    for forbidden in ("auth.py", "crypto.py", "src/office", "read_platform_file"):
        assert forbidden not in text


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
