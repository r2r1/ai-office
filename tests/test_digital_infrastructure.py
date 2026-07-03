"""
Digital Infrastructure (Instant Learning, уровень 2): единый список источников
данных о компании — платформенные интеграции (registry) + сигналы, увиденные
на сайте клиента (CRM/аналитика/соцсети), к которым платформа не подключена
напрямую. Пользовательский запрос: не только CRM, но и другие источники
(соцсети и т.д.) — проверяем, что все три категории реально попадают в вывод.

    python tests/test_digital_infrastructure.py
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.office import digital_infrastructure
from src.saas import context as ctx


def _fresh_tenant(name: str, scan: dict | None = None):
    ctx.set_tenant(name)
    from src.saas import context
    brief = {"niche": "тест", "goal": "тест"}
    if scan is not None:
        brief["scan"] = scan
    context.write_json("brief.json", brief)


def test_platform_integrations_always_present():
    _fresh_tenant("di_unit_platform")
    payload = digital_infrastructure.payload()
    categories = {s["category"] for s in payload["sources"]}
    assert "platform" in categories
    names = {s["key"] for s in payload["sources"]}
    assert "telegram" in names and "github" in names
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


def test_no_scan_yields_missing_crm_analytics_social():
    """Без скана — CRM/аналитика/соцсети должны быть category-присутствующими
    как 'missing', не отсутствовать молча из вывода."""
    _fresh_tenant("di_unit_no_scan")
    payload = digital_infrastructure.payload()
    categories = {s["category"] for s in payload["sources"]}
    assert {"crm", "analytics", "social"} <= categories
    assert all(s["status"] == "missing" for s in payload["sources"]
              if s["category"] in ("analytics", "social"))
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


def test_detected_crm_and_social_surface_as_detected_external():
    scan = {
        "ok": True,
        "detected": {
            "analytics": {"ga4": True, "yandex_metrika": False, "vk_pixel": False, "meta_pixel": False},
            "crm_widgets": {"amocrm": True, "bitrix24": False},
            "socials": {"instagram": "instagram.com/test", "vk": "vk.com/test"},
        },
    }
    _fresh_tenant("di_unit_detected", scan=scan)
    payload = digital_infrastructure.payload()
    by_key = {s["key"]: s for s in payload["sources"]}
    assert by_key["ga4"]["status"] == "detected_external"
    assert by_key["yandex_metrika"]["status"] == "missing"
    assert by_key["amocrm"]["status"] == "detected_external"
    assert by_key["social_instagram"]["status"] == "detected_external"
    assert by_key["social_facebook"]["status"] == "missing"
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


def test_analytics_and_crm_markers_detected_from_html():
    detected = {}
    html = "<html><script>gtag('config','x')</script><div class='amocrm_id'></div></html>".lower()
    from src.office import company_scan
    detected["analytics"] = {name: any(m.lower() in html for m in markers)
                             for name, markers in company_scan._ANALYTICS_MARKERS.items()}
    detected["crm_widgets"] = {name: any(m.lower() in html for m in markers)
                               for name, markers in company_scan._CRM_MARKERS.items()}
    assert detected["analytics"]["ga4"] is True
    assert detected["crm_widgets"]["amocrm"] is True
    assert detected["analytics"]["yandex_metrika"] is False


def _run():
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ✓ {name}")
            passed += 1
    print(f"ВСЕ {passed} ТЕСТОВ ПРОШЛИ")


if __name__ == "__main__":
    _run()
