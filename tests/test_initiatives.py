"""
Юнит-тесты гейта вердикта по инициативе (src/office/initiatives.py,
src/office/initiative_research.py) — docs/product-capability-gaps.md п.6:
исследование "не стоит" больше не проходит мимо молча, требует override.

    python tests/test_initiatives.py
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.saas import context as ctx
from src.office import initiatives
from src.office.initiative_research import _parse_verdict


def _fresh(name: str) -> None:
    ctx.set_tenant(name)
    ctx.wipe()
    ctx.set_tenant(name)


def test_parse_verdict_go():
    assert _parse_verdict("Всё выполнимо.\n\nВЕРДИКТ: go") == "go"


def test_parse_verdict_no_go_case_insensitive():
    assert _parse_verdict("Слишком рискованно.\n\nвердикт: NO-GO") == "no-go"


def test_parse_verdict_missing_marker_is_unclear():
    assert _parse_verdict("Просто текст без маркера.") == "unclear"


def test_parse_verdict_empty_is_unclear():
    assert _parse_verdict("") == "unclear"


def test_new_initiative_defaults_to_unclear_recommendation():
    _fresh("init_test_default")
    iid = initiatives.add("Тест", "обоснование", "", needs_research=False)
    item = initiatives.get(iid)
    assert item["recommendation"] == "unclear"


def test_set_research_stores_recommendation():
    _fresh("init_test_store")
    iid = initiatives.add("Тест", "обоснование", "", needs_research=True)
    initiatives.set_research(iid, "Анализ...\n\nВЕРДИКТ: go", recommendation="go")
    item = initiatives.get(iid)
    assert item["recommendation"] == "go"
    assert item["status"] == "pending"


def test_accept_go_recommendation_succeeds_without_override():
    _fresh("init_test_accept_go")
    iid = initiatives.add("Тест", "обоснование", "", tasks=[{"role": "developer", "title": "t"}],
                          needs_research=False)
    initiatives.set_research(iid, "ВЕРДИКТ: go", recommendation="go")
    tasks = initiatives.accept(iid)  # не должно бросить исключение
    assert len(tasks) == 1
    assert initiatives.get(iid)["status"] == "accepted"


def test_accept_no_go_blocked_without_override():
    _fresh("init_test_blocked")
    iid = initiatives.add("Тест", "обоснование", "", needs_research=False)
    initiatives.set_research(iid, "ВЕРДИКТ: no-go", recommendation="no-go")
    try:
        initiatives.accept(iid)
        assert False, "должно было бросить InitiativeBlocked"
    except initiatives.InitiativeBlocked as e:
        assert e.recommendation == "no-go"
    # статус НЕ поменялся — блок не имеет побочных эффектов
    assert initiatives.get(iid)["status"] == "pending"


def test_accept_no_go_succeeds_with_override():
    _fresh("init_test_override")
    iid = initiatives.add("Тест", "обоснование", "", tasks=[{"role": "developer", "title": "t"}],
                          needs_research=False)
    initiatives.set_research(iid, "ВЕРДИКТ: no-go", recommendation="no-go")
    tasks = initiatives.accept(iid, override=True)
    assert len(tasks) == 1
    assert initiatives.get(iid)["status"] == "accepted"


def _cleanup_test_tenants() -> None:
    for d in ctx.ROOT.glob("init_test_*"):
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
