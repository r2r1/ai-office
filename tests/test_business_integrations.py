"""
Юнит-тесты TEST-режима недостающих бизнес-интеграций
(src/integrations/invoicing.py, ads.py, crm.py) —
docs/product-capability-gaps.md п.7.

    python tests/test_business_integrations.py
"""

import asyncio
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.saas import context as ctx
from src.office import leads
from src.integrations import invoicing, ads, crm
from src.integrations import registry as integrations_registry


def _fresh(name: str) -> None:
    ctx.set_tenant(name)
    ctx.wipe()
    ctx.set_tenant(name)


def _run_async(coro):
    return asyncio.run(coro)


# ── invoicing ─────────────────────────────────────────────────────────────

def test_create_invoice_computes_total_from_items():
    _fresh("biz_test_invoice")
    result = _run_async(invoicing._create_invoice({}, {
        "client_name": "ООО Ромашка",
        "items": [{"name": "Разработка сайта", "amount": 30000}, {"name": "SEO", "amount": 5000}],
    }))
    assert "35000" in result or "35000.0" in result
    inv = invoicing.list_invoices()[0]
    assert inv["total"] == 35000
    assert inv["status"] == "issued"


def test_invoice_string_items_parsed():
    _fresh("biz_test_invoice_str")
    _run_async(invoicing._create_invoice({}, {
        "client_name": "Иван", "items": "Консультация - 2000\nВыезд - 1500",
    }))
    inv = invoicing.list_invoices()[0]
    assert inv["total"] == 3500


def test_mark_paid_changes_status():
    _fresh("biz_test_invoice_paid")
    _run_async(invoicing._create_invoice({}, {"client_name": "А", "items": [{"name": "X", "amount": 100}]}))
    inv = invoicing.list_invoices()[0]
    updated = invoicing.mark_paid(inv["id"])
    assert updated["status"] == "paid"


# ── ads ───────────────────────────────────────────────────────────────────

def test_create_campaign_rejects_zero_budget():
    _fresh("biz_test_ads_zero")
    result = _run_async(ads._create_campaign({}, {"headline": "Скидки!", "budget": 0}))
    assert "больше нуля" in result


def test_campaign_stats_are_deterministic_for_same_age():
    _fresh("biz_test_ads_stats")
    _run_async(ads._create_campaign({}, {"headline": "Скидки!", "budget": 500, "platform": "meta_ads"}))
    c = ads.list_campaigns()[0]
    s1 = ads._deterministic_stats(c["id"], c["budget"], 48)
    s2 = ads._deterministic_stats(c["id"], c["budget"], 48)
    assert s1 == s2  # тот же возраст → тот же ответ, не случайные числа
    s3 = ads._deterministic_stats(c["id"], c["budget"], 96)
    assert s3["impressions"] >= s1["impressions"]  # растёт со временем


def test_unknown_platform_falls_back_to_google_ads():
    _fresh("biz_test_ads_platform")
    _run_async(ads._create_campaign({}, {"headline": "H", "budget": 10, "platform": "tiktok_ads"}))
    c = ads.list_campaigns()[0]
    assert c["platform"] == "google_ads"


# ── crm ───────────────────────────────────────────────────────────────────

def test_export_lead_assigns_external_contact_id():
    _fresh("biz_test_crm_export")
    lead = leads.add("site", "Пётр", "+79990000000", "")
    result = _run_async(crm._export_lead({}, {"lead_id": lead["id"]}))
    assert "экспортирован" in result
    contact = crm.get_by_lead(lead["id"])
    assert contact is not None
    assert contact["contact_id"].startswith("test_crm_")


def test_export_same_lead_twice_does_not_duplicate():
    _fresh("biz_test_crm_dedup")
    lead = leads.add("site", "Пётр", "+79990000000", "")
    _run_async(crm._export_lead({}, {"lead_id": lead["id"]}))
    result2 = _run_async(crm._export_lead({}, {"lead_id": lead["id"]}))
    assert "уже экспортирован" in result2
    assert len(crm.list_contacts()) == 1


def test_export_unknown_lead_fails_gracefully():
    _fresh("biz_test_crm_unknown")
    result = _run_async(crm._export_lead({}, {"lead_id": "no_such_lead"}))
    assert "не найден" in result


# ── регистрация в каталоге ───────────────────────────────────────────────

def test_all_three_registered_and_always_connected():
    for name in ("invoicing", "ads", "crm"):
        integ = integrations_registry.get(name)
        assert integ is not None, f"{name} не зарегистрирован в registry._ALL"
        assert integrations_registry.is_connected(integ)  # test-режим без кредов = всегда доступна


def _cleanup_test_tenants() -> None:
    for d in ctx.ROOT.glob("biz_test_*"):
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
