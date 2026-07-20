"""
connections.get_by_name() — нечёткий фолбэк не угадывает при неоднозначности
(production-readiness worklist п.21): если подстрокой совпадает НЕСКОЛЬКО
подключений («crm» ⊂ «crm_bitrix24» И есть отдельное «crm»), раньше молча
брался первый попавшийся — реальный риск подсунуть агенту чужие креды.

    python tests/test_connections_ambiguous.py
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv()  # APP_SECRET и т.п. — connections.save() шифрует креды at-rest

from src.saas import context as ctx
from src.office import connections


def _fresh(name: str) -> None:
    ctx.set_tenant(name)
    ctx.wipe()
    ctx.set_tenant(name)


def test_exact_match_always_wins():
    _fresh("conn_amb_exact")
    connections.save({"name": "crm", "fields": {"token": "AAA"}})
    connections.save({"name": "crm_bitrix24", "fields": {"webhook_url": "BBB"}})
    got = connections.get_by_name("crm")
    assert got is not None
    assert got["name"] == "crm"
    assert got["fields"]["token"] == "AAA"


def test_single_fuzzy_candidate_still_resolves():
    """Единственный кандидат подстрокой — фолбэк по-прежнему работает
    (полезный случай, который фикс не должен был сломать)."""
    _fresh("conn_amb_single")
    connections.save({"name": "crm_bitrix24", "fields": {"webhook_url": "BBB"}})
    got = connections.get_by_name("bitrix24")
    assert got is not None
    assert got["name"] == "crm_bitrix24"


def test_ambiguous_fuzzy_match_returns_none_not_a_guess():
    """Ядро фикса: query «telegram» подстрокой совпадает и с «telegram»
    (это уже exact — не тест-кейс), и... реальный кейс из аудита — запрос
    коротким именем, когда И короткое, И составное имя оба существуют."""
    _fresh("conn_amb_multi")
    connections.save({"name": "crm_bitrix24", "fields": {"webhook_url": "BBB"}})
    connections.save({"name": "crm_pipedrive", "fields": {"api_key": "CCC"}})
    # "crm" — подстрока ОБОИХ, ни одно не совпадает точно → неоднозначность
    got = connections.get_by_name("crm")
    assert got is None


def test_no_match_returns_none():
    _fresh("conn_amb_none")
    connections.save({"name": "gmail", "fields": {}})
    assert connections.get_by_name("bitrix24") is None


def test_exact_by_name_ignores_fuzzy_entirely():
    """get_exact_by_name — строгий сосед, не должен подхватывать даже
    единственного нечёткого кандидата (контракт: только точное имя)."""
    _fresh("conn_amb_exact_only")
    connections.save({"name": "crm_bitrix24", "fields": {}})
    assert connections.get_exact_by_name("crm") is None
    assert connections.get_exact_by_name("crm_bitrix24") is not None


def _cleanup_test_tenants() -> None:
    for d in ctx.ROOT.glob("conn_amb_*"):
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
