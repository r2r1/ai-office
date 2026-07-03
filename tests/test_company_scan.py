"""
Instant Learning (Company Scan): автоскан сайта клиента по URL за секунды
онбординга, без LLM и без единого вопроса — вау-эффект «мы уже кое-что знаем
о вас» (project memory: company-understanding-vision). Проверяет офлайн-логику
парсинга (без сети) + сериализацию в бриф.

    python tests/test_company_scan.py
"""

import asyncio
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.office import company_scan
from src.agents import onboarding
from src.saas import context as ctx


def test_normalize_url_adds_scheme():
    assert company_scan._normalize_url("example.com") == "https://example.com"
    assert company_scan._normalize_url("http://example.com") == "http://example.com"
    assert company_scan._normalize_url("") == ""


def test_scan_unreachable_host_returns_ok_false_not_exception():
    """Провайдер может DNS-хайджекать несуществующие домены (редиректят на свою
    страницу вместо разрыва соединения) — поэтому бьём в заведомо закрытый порт,
    а не полагаемся на то, что сеть вернёт connection error для fake-домена."""
    result = asyncio.run(company_scan.scan("http://127.0.0.1:1"))
    assert result["ok"] is False
    assert result["findings"], "недоступный сайт тоже должен дать понятный findings"


def test_summary_line_empty_for_failed_scan():
    assert company_scan.summary_line({"ok": False, "findings": []}) == ""
    assert company_scan.summary_line(None) == ""


def test_summary_line_for_successful_scan():
    fake = {"ok": True, "url": "https://example.com",
            "detected": {"cms": "WordPress", "emails": ["a@b.com"]}}
    line = company_scan.summary_line(fake)
    assert "WordPress" in line
    assert "example.com" in line


def test_build_brief_structured_merges_scan_into_constraints_and_summary():
    """Прод-требование (пользователь): онбординг не должен становиться длиннее —
    скан подмешивается ДОПОЛНИТЕЛЬНО к тем же 5 вопросам, не как новый вопрос."""
    answers = [
        {"dimension": "product", "answer": "Кухни на заказ"},
        {"dimension": "client", "answer": "Семьи"},
        {"dimension": "revenue", "answer": "1000000"},
        {"dimension": "goal", "answer": "Больше лидов"},
        {"dimension": "constraints", "answer": "Бюджет ограничен"},
    ]
    scan_result = {"ok": True, "url": "https://kuhni.ru",
                   "detected": {"cms": "Tilda", "emails": ["info@kuhni.ru"]}}
    brief = onboarding.build_brief_structured("business", answers, scan_result=scan_result)
    assert "Tilda" in brief["constraints"]
    assert "Бюджет ограничен" in brief["constraints"]
    assert "Tilda" in brief["summary"]
    assert brief["summary"].count("Автоскан") == 1, "скан не должен дублироваться в summary"
    assert brief["scan"] == scan_result


def test_build_brief_structured_without_scan_unaffected():
    answers = [{"dimension": "product", "answer": "Кухни"}]
    brief = onboarding.build_brief_structured("business", answers, scan_result=None)
    assert brief["scan"] is None
    assert "Автоскан" not in brief["summary"]


def test_understanding_domains_present_and_bounded():
    from src.office import understanding
    ctx.set_tenant("understanding_domains_unit")
    from src.saas import context
    context.write_json("brief.json", {"niche": "потолки", "goal": "сайт", "summary": "тест"})
    payload = understanding.payload()
    assert "domains" in payload
    for key in ("business", "marketing", "sales", "finance", "team"):
        assert key in payload["domains"]
        assert 0 <= payload["domains"][key] <= 100
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


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
