"""
Юнит-тесты кастомных доменов (src/office/domains.py) —
docs/product-capability-gaps.md п.5: сайт клиента больше не заперт только на
/site/{tenant}/{slug} под доменом платформы.

Хранилище domains.py ГЛОБАЛЬНОЕ (data/domains.json, не per-tenant) — тесты
чистят за собой явно, не через ctx.wipe().

    python tests/test_domains.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.office import domains

_TEST_DOMAINS = ["mycompany-test.ru", "taken-test.ru", "bad domain", "notadomain"]


def _cleanup() -> None:
    for d in _TEST_DOMAINS:
        domains.unregister(d, "tenant_a")
        domains.unregister(d, "tenant_b")


def test_valid_domain_accepted():
    assert domains.is_valid_domain("mycompany-test.ru")
    assert domains.is_valid_domain("sub.mycompany-test.ru")


def test_invalid_domain_rejected():
    assert not domains.is_valid_domain("bad domain")
    assert not domains.is_valid_domain("notadomain")
    assert not domains.is_valid_domain("")


def test_register_and_resolve():
    _cleanup()
    try:
        entry = domains.register("mycompany-test.ru", "tenant_a", "landing-1")
        assert "error" not in entry
        resolved = domains.resolve("mycompany-test.ru")
        assert resolved is not None
        assert resolved["tenant"] == "tenant_a"
        assert resolved["slug"] == "landing-1"
    finally:
        _cleanup()


def test_resolve_is_case_insensitive_and_strips_dot():
    _cleanup()
    try:
        domains.register("mycompany-test.ru", "tenant_a", "landing-1")
        assert domains.resolve("MyCompany-Test.RU") is not None
        assert domains.resolve("mycompany-test.ru.") is not None
    finally:
        _cleanup()


def test_domain_taken_by_other_tenant_is_rejected():
    _cleanup()
    try:
        first = domains.register("taken-test.ru", "tenant_a", "landing-1")
        assert "error" not in first
        second = domains.register("taken-test.ru", "tenant_b", "landing-2")
        assert "error" in second
        # владелец не поменялся
        assert domains.resolve("taken-test.ru")["tenant"] == "tenant_a"
    finally:
        _cleanup()


def test_same_tenant_can_repoint_own_domain_to_new_slug():
    _cleanup()
    try:
        domains.register("mycompany-test.ru", "tenant_a", "landing-1")
        domains.register("mycompany-test.ru", "tenant_a", "landing-2")
        assert domains.resolve("mycompany-test.ru")["slug"] == "landing-2"
    finally:
        _cleanup()


def test_invalid_domain_format_returns_error():
    result = domains.register("bad domain", "tenant_a", "landing-1")
    assert "error" in result


def test_unregister_only_by_owner():
    _cleanup()
    try:
        domains.register("mycompany-test.ru", "tenant_a", "landing-1")
        assert domains.unregister("mycompany-test.ru", "tenant_b") is False
        assert domains.resolve("mycompany-test.ru") is not None
        assert domains.unregister("mycompany-test.ru", "tenant_a") is True
        assert domains.resolve("mycompany-test.ru") is None
    finally:
        _cleanup()


def test_for_tenant_lists_only_own_domains():
    _cleanup()
    try:
        domains.register("mycompany-test.ru", "tenant_a", "landing-1")
        own = domains.for_tenant("tenant_a")
        assert len(own) == 1 and own[0]["domain"] == "mycompany-test.ru"
        assert domains.for_tenant("tenant_b") == []
    finally:
        _cleanup()


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
