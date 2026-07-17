"""
Юнит-тесты уровня автономии (src/office/autonomy.py).

Первое тестовое покрытие этого модуля — добавлено вместе с фиксом
docs/invariant-enforcement-audit-2026-07-17.md: push в GitHub раньше
классифицировался тем же action_type, что "создать пустой репозиторий"
(create_repo, порог "guided" — уровень по умолчанию), и потому пушил код
БЕЗ вопроса владельцу на дефолтных настройках, хотя CLAUDE.md §4 прямо
обещает обратное. Тесты фиксируют исправленное поведение и не дают ему
тихо откатиться при будущем рефакторинге.

    python tests/test_autonomy.py
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.saas import context as ctx
from src.office import autonomy


def _fresh(name: str) -> None:
    ctx.set_tenant(name)
    ctx.wipe()
    ctx.set_tenant(name)


def test_push_action_maps_to_push_code_type():
    assert autonomy._action_type_for("push") == "push_code"


def test_generic_repo_actions_still_map_to_create_repo():
    assert autonomy._action_type_for("create_repo") == "create_repo"
    assert autonomy._action_type_for("list_repos") == "create_repo"


def test_push_requires_approval_at_default_autonomy_level():
    """Дефолтный уровень — "guided" (autonomy._DEFAULT_LEVEL). push_code требует
    "trusted" — на дефолте система обязана спросить владельца, не пушить молча."""
    _fresh("aut_test_push_default")
    assert autonomy.get_level() == "guided"
    assert not autonomy.can_auto("push_code")
    assert autonomy.needs_approval("push_code")


def test_push_auto_allowed_at_trusted_level():
    _fresh("aut_test_push_trusted")
    ctx.write_json("autonomy", {"level": "trusted"})
    assert autonomy.can_auto("push_code")
    assert not autonomy.needs_approval("push_code")


def test_create_repo_still_auto_allowed_at_default_guided_level():
    """Создание пустого репозитория (не пуш кода) осталось на прежнем, менее
    строгом пороге — фикс не должен был затронуть этот тип действия."""
    _fresh("aut_test_create_repo_default")
    assert autonomy.get_level() == "guided"
    assert autonomy.can_auto("create_repo")
    assert not autonomy.needs_approval("create_repo")


def _cleanup_test_tenants() -> None:
    for d in ctx.ROOT.glob("aut_test_*"):
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
