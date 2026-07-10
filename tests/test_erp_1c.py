"""
Тесты erp_1c.py — новая способность "erp", ОТДЕЛЬНАЯ от "crm" (1С не
альтернатива внешней CRM, а система учёта — другой класс задач агента).

Реальное отличие от crm_bitrix24.py: у 1С нет фиксированной схемы полей
(каждая конфигурация называет сущности/поля по-своему), поэтому провайдер
требует field_map (JSON-соответствие) вместо захардкоженных TITLE/NAME/PHONE.
Сеть не мокается (реальный вызов не проверяется — как и у crm_bitrix24.py),
тестируется контракт ошибок и маппинга полей.

    python tests/test_erp_1c.py
"""

import asyncio
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv()

from src.saas import context as ctx
from src.office import leads as leads_module
from src.office import capability
from src.integrations import erp_1c
from src.integrations import registry as integrations_registry
from src.office import tool_router


def _fresh(name: str) -> None:
    ctx.set_tenant(name)
    ctx.wipe()
    ctx.set_tenant(name)


def _run_async(coro):
    return asyncio.run(coro)


def test_create_counterparty_without_creds_raises_clear_error():
    async def _go():
        try:
            await erp_1c._create_counterparty({}, {"lead_id": "x"})
            assert False, "должно было упасть без настройки"
        except RuntimeError as e:
            assert "base_url" in str(e) or "1С" in str(e) or "публикован" in str(e).lower()
    _run_async(_go())


def test_create_counterparty_without_field_map_raises_clear_error():
    _fresh("erp_test_no_map")
    lead = leads_module.add("site1", "Иван Иванов", "+79990000000")
    creds = {"base_url": "https://x.example.ru/base/odata/standard.odata",
             "login": "api", "password": "secret", "entity": "Catalog_Контрагенты"}
    async def _go():
        try:
            await erp_1c._create_counterparty(creds, {"lead_id": lead["id"]})
            assert False, "должно было упасть без field_map"
        except RuntimeError as e:
            assert "field_map" in str(e)
    _run_async(_go())


def test_create_counterparty_unknown_lead_fails_gracefully():
    creds = {"base_url": "https://x.example.ru/base/odata/standard.odata",
             "login": "api", "password": "secret", "entity": "Catalog_Контрагенты",
             "field_map": '{"name": "Description"}'}
    async def _go():
        try:
            await erp_1c._create_counterparty(creds, {"lead_id": "does-not-exist"})
            assert False, "должно было упасть без такого лида"
        except RuntimeError as e:
            assert "не найден" in str(e).lower()
    _run_async(_go())


def test_invalid_field_map_json_raises_clear_error():
    creds = {"base_url": "https://x.example.ru/base/odata/standard.odata",
             "login": "api", "password": "secret", "entity": "Catalog_Контрагенты",
             "field_map": "не json{{{"}
    async def _go():
        try:
            await erp_1c._create_counterparty(creds, {"lead_id": "whatever"})
            assert False, "должно было упасть на невалидном JSON"
        except RuntimeError as e:
            assert "JSON" in str(e)
    _run_async(_go())


def test_map_fields_only_translates_declared_mapping():
    lead = {"name": "Иван", "contact": "+7999", "message": "звонить вечером"}
    field_map = {"name": "Description", "contact": "Телефон"}
    mapped = erp_1c._map_fields(lead, field_map)
    assert mapped == {"Description": "Иван", "Телефон": "+7999"}
    assert "message" not in mapped and "звонить вечером" not in mapped.values()  # не в field_map — не передано


def test_erp_capability_registered_separately_from_crm():
    """Ключевое: ERP — НЕ провайдер способности crm."""
    assert "erp" in capability._CATALOG
    assert set(capability._CATALOG["erp"]["backed_by"]) == {"erp_1c"}
    assert "erp_1c" not in set(capability._CATALOG["crm"]["backed_by"])


def test_erp_integration_registered_in_registry():
    integ = integrations_registry.get("erp_1c")
    assert integ is not None
    assert integ.title == "1С (ERP)"


def test_tool_router_finds_erp_1c_for_1c_intent():
    cands = tool_router.route("создать контрагента в 1с", top=5)
    integs = {c["integration"] for c in cands}
    assert "erp_1c" in integs
    assert "crm" not in integs  # не путается с CRM-намерением


def _cleanup_test_tenants() -> None:
    for d in ctx.ROOT.glob("erp_test_*"):
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
