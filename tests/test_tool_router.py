"""
Тесты tool_router.py — раньше был покрыт только "счастливый путь" с явным
лидером (см. tests/test_agent_tool_handlers.py). Ветка неоднозначности
(best() == None, route() отдаёт топ-N без победителя) не проверялась вообще —
если скоринг в needs.py сломается при росте реестра интеграций, это не
заметил бы ни один тест.

    python tests/test_tool_router.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.office import tool_router


def test_clear_synonym_leader_is_best():
    """Реальный каталог интеграций: явный лидер по synonyms — website.publish_site."""
    best = tool_router.best("опубликовать лендинг клиенту")
    assert best is not None
    assert best["integration"] == "website"
    assert best["action"] == "publish_site"


def test_ambiguous_candidates_return_none():
    """Два кандидата с одинаковым score — best() должен отдать None (развилка
    агенту), а не произвольно выбрать одного."""
    fake_caps = [
        {"integration": "svc_a", "action": "do_x", "title": "Сервис A",
         "tokens": {"обработать", "запрос", "клиента"}, "connected": True, "synonyms": []},
        {"integration": "svc_b", "action": "do_y", "title": "Сервис B",
         "tokens": {"обработать", "запрос", "клиента"}, "connected": True, "synonyms": []},
    ]
    orig = tool_router._capabilities
    tool_router._capabilities = lambda: fake_caps
    try:
        cands = tool_router.route("обработать запрос клиента", top=2)
        assert len(cands) == 2
        assert cands[0]["score"] == cands[1]["score"]
        assert tool_router.best("обработать запрос клиента") is None
    finally:
        tool_router._capabilities = orig


def test_clear_score_gap_wins_over_tie():
    """Кандидат с явным отрывом (>=1.0) побеждает — best() не None."""
    fake_caps = [
        {"integration": "svc_a", "action": "do_x", "title": "Сервис A",
         "tokens": {"обработать", "запрос", "клиента", "срочно", "лично"},
         "connected": True, "synonyms": []},
        {"integration": "svc_b", "action": "do_y", "title": "Сервис B",
         "tokens": {"обработать"}, "connected": True, "synonyms": []},
    ]
    orig = tool_router._capabilities
    tool_router._capabilities = lambda: fake_caps
    try:
        best = tool_router.best("обработать запрос клиента срочно лично")
        assert best is not None
        assert best["integration"] == "svc_a"
    finally:
        tool_router._capabilities = orig


def test_no_match_returns_empty_and_none():
    fake_caps = [
        {"integration": "svc_a", "action": "do_x", "title": "Сервис A",
         "tokens": {"совершенно", "другое"}, "connected": True, "synonyms": []},
    ]
    orig = tool_router._capabilities
    tool_router._capabilities = lambda: fake_caps
    try:
        assert tool_router.route("непересекающийся запрос про погоду") == []
        assert tool_router.best("непересекающийся запрос про погоду") is None
    finally:
        tool_router._capabilities = orig


def test_route_respects_top_limit():
    fake_caps = [
        {"integration": f"svc_{i}", "action": "do", "title": f"Сервис {i}",
         "tokens": {"общий", "токен"}, "connected": True, "synonyms": []}
        for i in range(5)
    ]
    orig = tool_router._capabilities
    tool_router._capabilities = lambda: fake_caps
    try:
        cands = tool_router.route("общий токен запрос", top=2)
        assert len(cands) == 2
    finally:
        tool_router._capabilities = orig


def test_synonym_bonus_breaks_a_tie():
    """При равном пересечении токенов synonyms — решающий голос (это уже было
    покрыто косвенно тестом ниже уровня, фиксируем явно)."""
    fake_caps = [
        {"integration": "svc_a", "action": "do_x", "title": "Сервис A",
         "tokens": {"обработать", "клиента"}, "connected": True, "synonyms": ["клиент"]},
        {"integration": "svc_b", "action": "do_y", "title": "Сервис B",
         "tokens": {"обработать", "клиента"}, "connected": True, "synonyms": []},
    ]
    orig = tool_router._capabilities
    tool_router._capabilities = lambda: fake_caps
    try:
        best = tool_router.best("обработать клиента")
        assert best is not None
        assert best["integration"] == "svc_a"
    finally:
        tool_router._capabilities = orig


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
