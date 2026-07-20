"""
Morning Digest (src/office/digest.py) — дебаунс повторного вызова
(production-readiness worklist п.27): два почти одновременных вызова
get_and_mark_seen() (два открытых таба одного тенанта) не должны оба строить
и показывать один и тот же дайджест.

    python tests/test_digest.py
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.saas import context as ctx
from src.office import digest, plan


def _fresh(name: str) -> None:
    ctx.set_tenant(name)
    ctx.wipe()
    ctx.set_tenant(name)


def test_first_call_returns_first_visit_digest():
    _fresh("digest_test_first")
    d = digest.get_and_mark_seen()
    assert d["is_first"] is True


def test_immediate_second_call_is_debounced():
    _fresh("digest_test_debounce")
    digest.get_and_mark_seen()
    d2 = digest.get_and_mark_seen()
    assert d2 == {"items": [], "count": 0, "since": "", "is_first": False}


def test_call_after_debounce_window_recomputes():
    _fresh("digest_test_after_window")
    digest.get_and_mark_seen()
    digest._last_call[ctx.get_tenant()] -= digest._DEBOUNCE_SECS + 1  # симулируем прошедшее время
    d2 = digest.get_and_mark_seen()
    assert d2 != {"items": [], "count": 0, "since": "", "is_first": False}


def test_debounce_is_per_tenant():
    _fresh("digest_test_tenant_a")
    digest.get_and_mark_seen()
    _fresh("digest_test_tenant_b")
    d = digest.get_and_mark_seen()  # чужой дебаунс не должен влиять
    assert d["is_first"] is True


def test_peek_last_empty_by_default():
    """round2 audit U3: без единого непустого дайджеста peek_last() честно пуст."""
    _fresh("digest_test_peek_empty")
    assert digest.peek_last() == {"items": [], "count": 0, "since": "", "is_first": False}


def test_peek_last_returns_last_nonempty_digest_without_consuming_it():
    _fresh("digest_test_peek_nonempty")
    t = plan.add_task("Собрать бренд-бук", "designer")
    plan.assign(t["id"], "designer_1")
    plan.complete(t["id"])
    d1 = digest.get_and_mark_seen()  # last_seen=0 → is_first, count всё равно есть
    assert d1["count"] >= 1
    peeked = digest.peek_last()
    assert peeked["count"] == d1["count"]
    assert peeked["items"] == d1["items"]
    # peek_last НЕ продвигает last_seen — обычный get_and_mark_seen (после debounce)
    # больше не должен повторно показать тот же самый пункт.
    digest._last_call[ctx.get_tenant()] -= digest._DEBOUNCE_SECS + 1
    d2 = digest.get_and_mark_seen()
    assert d2["count"] == 0
    # но peek_last всё ещё отдаёт прежний, ничего не потеряно
    assert digest.peek_last()["count"] == d1["count"]


def _cleanup_test_tenants() -> None:
    for d in ctx.ROOT.glob("digest_test_*"):
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
        _cleanup_test_tenants()
    print(f"ВСЕ {passed} ТЕСТОВ ПРОШЛИ")


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    _run()
