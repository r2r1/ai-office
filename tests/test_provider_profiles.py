"""
Тесты Provider/Profile для интеграций (Фаза 3): одна способность может
закрываться НЕСКОЛЬКИМИ провайдерами (crm — TEST-режим + crm_bitrix24 —
реальный), и у одного провайдера может быть НЕСКОЛЬКО одновременных профилей
(два портала Bitrix24 разных отделов). Раньше: интеграция 1:1 со способностью,
connections читались только по первому совпадению имени, и нечёткий матч
credentials_for/is_connected рисковал зацепить чужую интеграцию с похожим
префиксом ("crm" — подстрока "crm_bitrix24").

    python tests/test_provider_profiles.py
"""

import asyncio
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv()  # APP_SECRET и т.п. — connections.save() шифрует креды at-rest

from src.saas import context as ctx
from src.office import connections, capability
from src.integrations import registry as integrations_registry
from src.integrations import crm_bitrix24
from src.office import tool_router


def _fresh(name: str) -> None:
    ctx.set_tenant(name)
    ctx.wipe()
    ctx.set_tenant(name)


def _run_async(coro):
    return asyncio.run(coro)


# ── connections.py: точный матч + мульти-профиль ────────────────────────────

def test_get_exact_by_name_does_not_fuzzy_match_similar_prefix():
    """Реальный риск, который это закрывает: нечёткий get_by_name("crm") мог бы
    зацепить подключение "crm_bitrix24" (подстрока), если "crm" ровно не
    подключена. get_exact_by_name так не делает."""
    _fresh("prof_test_exact_no_fuzzy")
    connections.save({"name": "crm_bitrix24", "fields": {"webhook_url": "https://x/"}})
    assert connections.get_exact_by_name("crm") is None
    assert connections.get_exact_by_name("crm_bitrix24") is not None


def test_multiple_profiles_same_name_are_both_stored_and_readable():
    _fresh("prof_test_multi")
    connections.save({"name": "crm_bitrix24", "fields": {"webhook_url": "https://a.bitrix24.ru/rest/1/aaa/"}})
    connections.save({"name": "crm_bitrix24", "fields": {"webhook_url": "https://b.bitrix24.ru/rest/1/bbb/"}})
    profiles = connections.get_all_by_name("crm_bitrix24")
    assert len(profiles) == 2
    urls = {p["fields"]["webhook_url"] for p in profiles}
    assert urls == {"https://a.bitrix24.ru/rest/1/aaa/", "https://b.bitrix24.ru/rest/1/bbb/"}


def test_get_profile_by_id_returns_specific_connection():
    _fresh("prof_test_getprofile")
    c1 = connections.save({"name": "crm_bitrix24", "fields": {"webhook_url": "https://one/"}})
    c2 = connections.save({"name": "crm_bitrix24", "fields": {"webhook_url": "https://two/"}})
    got = connections.get_profile(c2["id"])
    assert got["fields"]["webhook_url"] == "https://two/"
    assert connections.get_profile(c1["id"])["fields"]["webhook_url"] == "https://one/"


def test_list_profiles_masks_values_for_ui():
    _fresh("prof_test_masked")
    connections.save({"name": "crm_bitrix24", "fields": {"webhook_url": "https://secret.example/rest/1/token123/"}})
    listed = connections.list_profiles("crm_bitrix24")
    assert len(listed) == 1
    assert "•" in listed[0]["fields"]["webhook_url"]


# ── registry.py: credentials_for(profile_id) ────────────────────────────────

def test_credentials_for_specific_profile():
    _fresh("prof_test_creds_profile")
    c1 = connections.save({"name": "crm_bitrix24", "fields": {"webhook_url": "https://one/"}})
    c2 = connections.save({"name": "crm_bitrix24", "fields": {"webhook_url": "https://two/"}})
    creds1 = integrations_registry.credentials_for(crm_bitrix24.INTEGRATION, profile_id=c1["id"])
    creds2 = integrations_registry.credentials_for(crm_bitrix24.INTEGRATION, profile_id=c2["id"])
    assert creds1["webhook_url"] == "https://one/"
    assert creds2["webhook_url"] == "https://two/"


def test_credentials_for_without_profile_id_falls_back_to_first():
    _fresh("prof_test_creds_default")
    connections.save({"name": "crm_bitrix24", "fields": {"webhook_url": "https://default/"}})
    creds = integrations_registry.credentials_for(crm_bitrix24.INTEGRATION)
    assert creds["webhook_url"] == "https://default/"


def test_is_connected_false_without_creds_true_with():
    _fresh("prof_test_is_connected")
    assert integrations_registry.is_connected(crm_bitrix24.INTEGRATION) is False
    connections.save({"name": "crm_bitrix24", "fields": {"webhook_url": "https://x/"}})
    assert integrations_registry.is_connected(crm_bitrix24.INTEGRATION) is True


def test_profiles_for_lists_all_masked_profiles():
    _fresh("prof_test_profiles_for")
    connections.save({"name": "crm_bitrix24", "fields": {"webhook_url": "https://a/"}})
    connections.save({"name": "crm_bitrix24", "fields": {"webhook_url": "https://b/"}})
    profiles = integrations_registry.profiles_for(crm_bitrix24.INTEGRATION)
    assert len(profiles) == 2


# ── capability.py: backed_by = кортеж (любой из) ────────────────────────────

def test_capability_have_if_any_of_multiple_backing_providers_connected():
    orig = capability._CATALOG.get("__test_multi")
    capability._CATALOG["__test_multi"] = {"label": "Тест", "backed_by": ("svc_a", "svc_b"), "hint": ""}
    orig_get = integrations_registry.get
    orig_connected = integrations_registry.is_connected

    class _Fake:
        def __init__(self, name):
            self.name = name

    integrations_registry.get = lambda name: _Fake(name) if name in ("svc_a", "svc_b") else None
    integrations_registry.is_connected = lambda integ: integ.name == "svc_b"
    try:
        assert capability._backing_status("__test_multi") == "have"
    finally:
        integrations_registry.get = orig_get
        integrations_registry.is_connected = orig_connected
        if orig is not None:
            capability._CATALOG["__test_multi"] = orig
        else:
            capability._CATALOG.pop("__test_multi", None)


def test_capability_available_if_none_of_multiple_providers_connected():
    orig = capability._CATALOG.get("__test_multi2")
    capability._CATALOG["__test_multi2"] = {"label": "Тест", "backed_by": ("svc_a", "svc_b"), "hint": ""}
    orig_get = integrations_registry.get
    orig_connected = integrations_registry.is_connected
    integrations_registry.get = lambda name: None
    integrations_registry.is_connected = lambda integ: False
    try:
        assert capability._backing_status("__test_multi2") == "available"
    finally:
        integrations_registry.get = orig_get
        integrations_registry.is_connected = orig_connected
        if orig is not None:
            capability._CATALOG["__test_multi2"] = orig
        else:
            capability._CATALOG.pop("__test_multi2", None)


def test_acquire_offers_all_provider_options_when_multiple():
    orig = capability._CATALOG.get("__test_multi3")
    capability._CATALOG["__test_multi3"] = {"label": "Тест", "backed_by": ("svc_a", "svc_b"), "hint": ""}
    try:
        acquire = capability._acquire("__test_multi3")
        assert acquire["method"] == "connect_integration"
        assert set(acquire["options"]) == {"svc_a", "svc_b"}
    finally:
        if orig is not None:
            capability._CATALOG["__test_multi3"] = orig
        else:
            capability._CATALOG.pop("__test_multi3", None)


def test_crm_capability_registered_with_two_providers():
    spec = capability._CATALOG["crm"]
    assert set(spec["backed_by"]) == {"crm", "crm_bitrix24"}


# ── crm_bitrix24.py: обработчик без сети (только путь "нет кредов") ─────────

def test_export_lead_without_webhook_raises_clear_error():
    async def _go():
        try:
            await crm_bitrix24._export_lead({}, {"lead_id": "x"})
            assert False, "должно было упасть без вебхука"
        except RuntimeError as e:
            assert "вебхук" in str(e).lower()
    _run_async(_go())


def test_export_lead_unknown_lead_id_fails_gracefully():
    _fresh("prof_test_bitrix_unknown_lead")
    async def _go():
        try:
            await crm_bitrix24._export_lead({"webhook_url": "https://x.bitrix24.ru/rest/1/aaa/"},
                                            {"lead_id": "does-not-exist"})
            assert False, "должно было упасть без такого лида"
        except RuntimeError as e:
            assert "не найден" in str(e).lower()
    _run_async(_go())


# ── tool_router.py: оба провайдера видны как отдельные кандидаты ────────────

def test_tool_router_sees_both_crm_providers_as_candidates():
    cands = tool_router.route("экспортировать лида в crm bitrix", top=5)
    integs = {c["integration"] for c in cands}
    assert "crm" in integs
    assert "crm_bitrix24" in integs


def _cleanup_test_tenants() -> None:
    for d in ctx.ROOT.glob("prof_test_*"):
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
