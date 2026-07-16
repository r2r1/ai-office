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
from unittest.mock import patch

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


def test_pain_points_speak_business_not_tech():
    """Прод-фидбек (пользователь): «Нашёл WordPress» ничего не говорит владельцу
    бизнеса — pain_points обязаны быть на языке пользы/потерь, а не техники."""
    detected_bad = {
        "has_cta": False, "has_form": False, "emails": [], "phones": [],
        "response_ms": 2000, "has_reviews": False, "socials": {},
        "meta_description": None, "https": False, "has_viewport": False,
    }
    points = company_scan._pain_points(detected_bad)
    assert len(points) == 6  # обрезается до топ-6
    joined = " ".join(points).lower()
    assert "wordpress" not in joined and "cms" not in joined and "robots" not in joined
    assert any("призыв" in p.lower() for p in points)


def test_pain_points_empty_when_all_good():
    detected_good = {
        "has_cta": True, "has_form": True, "response_ms": 200,
        "has_reviews": True, "socials": {"vk": "vk.com/x"},
        "meta_description": "x", "https": True, "has_viewport": True,
    }
    assert company_scan._pain_points(detected_good) == []


def test_scan_result_has_headline_and_pain_points_keys():
    result = asyncio.run(company_scan.scan(""))
    assert result["pain_points"] == []
    assert result["headline"] == ""


# ── SSRF-защита (эндпоинт публичный — см. server.py _PUBLIC_API) ────────────

def test_is_private_host_blocks_localhost_and_loopback():
    assert company_scan._is_private_host("localhost")
    assert company_scan._is_private_host("127.0.0.1")
    assert company_scan._is_private_host("0.0.0.0")


def test_is_private_host_blocks_link_local_metadata():
    assert company_scan._is_private_host("169.254.169.254")  # облачный metadata-эндпоинт


def test_is_private_host_blocks_private_ranges():
    assert company_scan._is_private_host("10.0.0.5")
    assert company_scan._is_private_host("192.168.1.1")


def test_is_private_host_allows_public_ip():
    assert not company_scan._is_private_host("8.8.8.8")


def test_is_private_host_blocks_unresolvable():
    assert company_scan._is_private_host("этот-домен-точно-не-существует-xyzzy123.invalid")


def test_scan_rejects_localhost_without_network_call():
    result = asyncio.run(company_scan.scan("http://localhost:8000/"))
    assert result["ok"] is False
    assert "нельзя" in result["findings"][0].lower()


# ── Гипотеза о стадии бизнеса (LLM с фолбэком на эвристику, см. company_scan.py) ─

def test_stage_heuristic_mature_when_crm_analytics_reviews():
    detected = {"crm_widgets": {"amocrm": True}, "analytics": {"ga4": True}, "has_reviews": True}
    stage = company_scan._stage_heuristic(detected)
    assert stage["key"] == "mature"


def test_stage_heuristic_growth_when_only_analytics():
    detected = {"crm_widgets": {}, "analytics": {"ga4": True}, "has_reviews": False}
    stage = company_scan._stage_heuristic(detected)
    assert stage["key"] == "growth"


def test_stage_heuristic_launch_when_form_but_no_tracking():
    detected = {"crm_widgets": {}, "analytics": {}, "has_form": True}
    stage = company_scan._stage_heuristic(detected)
    assert stage["key"] == "launch"


def test_stage_heuristic_idea_when_no_signals():
    detected = {"crm_widgets": {}, "analytics": {}, "has_form": False, "has_cta": False}
    stage = company_scan._stage_heuristic(detected)
    assert stage["key"] == "idea"


def test_stage_heuristic_none_when_detected_empty():
    assert company_scan._stage_heuristic({}) is None


def test_stage_heuristic_always_carries_inferred_confidence():
    """Фаза 2 (docs/first-investigation-plan-2026-07-16.md): стадия НИКОГДА не
    выставляется без явной пометки уверенности — эвристика по сайту не факт из
    брифа, пока владелец сам не подтвердит."""
    for detected in (
        {"crm_widgets": {"amocrm": True}, "analytics": {"ga4": True}, "has_reviews": True},
        {"crm_widgets": {}, "analytics": {"ga4": True}, "has_reviews": False},
        {"crm_widgets": {}, "analytics": {}, "has_form": True},
        {"crm_widgets": {}, "analytics": {}, "has_form": False, "has_cta": False},
    ):
        assert company_scan._stage_heuristic(detected)["confidence"] == "inferred"


def test_stage_hypothesis_uses_llm_result_when_valid_json():
    """Мокаем llm.run_agent — реальный API не вызываем ни разу, проверяем только
    что валидный JSON-ответ используется вместо эвристики."""
    async def fake_run_agent(**kwargs):
        return '{"key": "growth", "label": "растёте быстро", "reason": "аналитика уже подключена"}'
    detected = {"crm_widgets": {}, "analytics": {"ga4": True}, "has_reviews": False}
    with patch("src.core.llm.run_agent", side_effect=fake_run_agent):
        stage = asyncio.run(company_scan._stage_hypothesis(detected, [], []))
    assert stage == {"key": "growth", "label": "растёте быстро", "reason": "аналитика уже подключена",
                     "confidence": "inferred"}


def test_stage_hypothesis_falls_back_to_heuristic_on_llm_error():
    async def failing_call(**kwargs):
        raise RuntimeError("нет баланса")
    detected = {"crm_widgets": {}, "analytics": {}, "has_form": True}
    with patch("src.core.llm.run_agent", side_effect=failing_call):
        stage = asyncio.run(company_scan._stage_hypothesis(detected, [], []))
    assert stage["key"] == "launch"  # эвристика для этих сигналов


def test_stage_hypothesis_falls_back_when_llm_too_slow():
    """Живой замер в этой сессии: обычный run_agent для этой классификации занял
    156.9с (apinet под нагрузкой) — недопустимо для лендинга. _STAGE_LLM_TIMEOUT
    должен оборвать вызов и вернуть эвристику, а не ждать."""
    async def slow_call(**kwargs):
        await asyncio.sleep(5)
        return '{"key": "mature", "label": "не должно попасть сюда", "reason": "..."}'
    detected = {"crm_widgets": {}, "analytics": {}, "has_form": True}
    with patch("src.office.company_scan._STAGE_LLM_TIMEOUT", 0.05), \
         patch("src.core.llm.run_agent", side_effect=slow_call):
        stage = asyncio.run(company_scan._stage_hypothesis(detected, [], []))
    assert stage["key"] == "launch"  # эвристика, не "mature" из медленного LLM-ответа


def test_stage_hypothesis_falls_back_when_llm_returns_garbage():
    async def garbage_call(**kwargs):
        return "не могу определить"
    detected = {"crm_widgets": {}, "analytics": {}, "has_form": False, "has_cta": False}
    with patch("src.core.llm.run_agent", side_effect=garbage_call):
        stage = asyncio.run(company_scan._stage_hypothesis(detected, [], []))
    assert stage["key"] == "idea"


def test_ru_plural_agrees_with_number():
    assert company_scan._ru_plural(1) == "точку роста"
    assert company_scan._ru_plural(2) == "точки роста"
    assert company_scan._ru_plural(5) == "точек роста"
    assert company_scan._ru_plural(11) == "точек роста"
    assert company_scan._ru_plural(21) == "точку роста"


def test_sales_domain_not_inflated_by_crm_router_stub():
    """Реальный баг, найден при добавлении Confidence: Tool Router capability-
    заглушка "crm" (src/integrations/crm.py, cred_fields=[]) всегда "connected"
    независимо от клиента — раньше ЛЮБОЙ тенант получал +60 к домену "sales" без
    единого реального подключения CRM."""
    from src.office import understanding
    ctx.set_tenant("understanding_sales_no_stub_unit")
    from src.saas import context
    context.write_json("brief.json", {})
    payload = understanding.payload()
    assert payload["domains"]["sales"] < 60
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


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


# ── Гранулярный чек-лист Company Understanding (Фаза 3, docs/first-investigation-plan-2026-07-16.md) ──

def test_checklist_has_11_items_all_tagged_with_existing_domain():
    from src.office import understanding
    ctx.set_tenant("understanding_checklist_unit1")
    from src.saas import context
    context.write_json("brief.json", {"niche": "потолки", "goal": "сайт", "summary": "тест"})
    checklist = understanding.payload()["checklist"]
    assert len(checklist) == 11
    for item in checklist:
        assert item["domain"] in ("business", "marketing", "sales", "finance", "team")
        assert isinstance(item["done"], bool)
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


def test_checklist_marks_product_and_region_from_brief_fields():
    from src.office import understanding
    ctx.set_tenant("understanding_checklist_unit2")
    from src.saas import context
    context.write_json("brief.json", {"niche": "потолки", "audience": "жители КМВ", "summary": "тест"})
    checklist = {item["label"]: item["done"] for item in understanding.payload()["checklist"]}
    assert checklist["продукты"] is True
    assert checklist["регион"] is True
    assert checklist["рынок"] is False  # research.md ещё не написан
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


def test_checklist_marks_site_and_analytics_from_real_scan():
    from src.office import understanding
    ctx.set_tenant("understanding_checklist_unit3")
    from src.saas import context
    context.write_json("brief.json", {
        "niche": "потолки", "summary": "тест",
        "scan": {"ok": True, "detected": {"analytics": {"ga4": True}}},
    })
    checklist = {item["label"]: item["done"] for item in understanding.payload()["checklist"]}
    assert checklist["сайт"] is True
    assert checklist["аналитика"] is True
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


def test_checklist_sales_marked_only_by_real_leads_not_bare_summary():
    from src.office import understanding
    ctx.set_tenant("understanding_checklist_unit4")
    from src.saas import context
    context.write_json("brief.json", {"niche": "потолки", "summary": "тест"})
    checklist = {item["label"]: item["done"] for item in understanding.payload()["checklist"]}
    assert checklist["продажи"] is False
    assert checklist["CRM"] is False
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


# ── Confidence ≠ Understanding score (issue #24) ─────────────────────────────

def test_confidence_present_and_bounded():
    from src.office import understanding
    ctx.set_tenant("understanding_confidence_unit1")
    from src.saas import context
    context.write_json("brief.json", {"niche": "потолки", "goal": "сайт", "summary": "тест"})
    payload = understanding.payload()
    assert "confidence" in payload
    assert 0 <= payload["confidence"] <= 100
    assert isinstance(payload["confidence_reasons"], list)
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


def test_confidence_higher_with_verified_scan_than_bare_summary():
    """Self-report ("сказал сам") должно весить МЕНЬШЕ, чем проверенный автоскан —
    это и есть весь смысл Confidence, отдельный от Understanding score."""
    from src.office import understanding
    from src.saas import context

    ctx.set_tenant("understanding_confidence_unit2")
    context.write_json("brief.json", {"summary": "тест"})
    conf_bare = understanding.payload()["confidence"]
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)

    ctx.set_tenant("understanding_confidence_unit3")
    context.write_json("brief.json", {"summary": "тест", "scan": {"ok": True, "url": "https://x.com"}})
    conf_scanned = understanding.payload()["confidence"]
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)

    assert conf_scanned > conf_bare


def test_confidence_zero_signals_stays_low():
    from src.office import understanding
    from src.saas import context
    ctx.set_tenant("understanding_confidence_unit4")
    context.write_json("brief.json", {})
    payload = understanding.payload()
    assert payload["confidence"] <= 20
    shutil.rmtree(ctx.tenant_dir(), ignore_errors=True)


# ── Первое расследование: search_company (docs/first-investigation-plan-2026-07-16.md, Фаза 1) ──

def test_investigation_queries_orders_by_specificity_and_dedups():
    qs = company_scan._investigation_queries("корпусная мебель", "КМВ", "Мебель+")
    assert qs[0] == "Мебель+ корпусная мебель КМВ"
    assert "Мебель+ КМВ" in qs
    assert "корпусная мебель КМВ" in qs
    assert "корпусная мебель" in qs
    assert len(qs) == len(set(qs))


def test_investigation_queries_without_name_uses_niche_only():
    qs = company_scan._investigation_queries("корпусная мебель", "КМВ", "")
    assert qs == ["корпусная мебель КМВ", "корпусная мебель"]


def test_search_company_empty_input_returns_unconfirmed_without_search():
    result = asyncio.run(company_scan.search_company("", "", ""))
    assert result["ok"] is False
    assert result["stage"]["confidence"] == "unconfirmed"
    assert result["queries_tried"] == []


def test_search_company_no_results_is_honest_not_confirmed():
    with patch("src.core.search.web_search_raw", return_value=[]):
        result = asyncio.run(company_scan.search_company("корпусная мебель", "КМВ", ""))
    assert result["ok"] is False
    assert result["stage"]["confidence"] == "unconfirmed"
    assert len(result["queries_tried"]) > 1  # пробовал несколько формулировок, не одну


def test_search_company_tries_next_query_only_if_previous_empty():
    calls = []
    def fake_search(query, max_results=6, timeout=8):
        calls.append(query)
        return [] if len(calls) == 1 else [{"title": "Рынок мебели", "body": "обзор", "href": "https://example.com/a"}]
    with patch("src.core.search.web_search_raw", side_effect=fake_search):
        result = asyncio.run(company_scan.search_company("корпусная мебель", "КМВ", "Мебель+"))
    assert len(calls) == 2  # первая формулировка пустая → перешёл к следующей, не искал третью
    assert result["ok"] is True


def test_search_company_stops_after_first_successful_query():
    calls = []
    def fake_search(query, max_results=6, timeout=8):
        calls.append(query)
        return [{"title": "Нашли", "body": "", "href": "https://vk.com/mebelplus"}]
    with patch("src.core.search.web_search_raw", side_effect=fake_search):
        asyncio.run(company_scan.search_company("корпусная мебель", "КМВ", "Мебель+"))
    assert len(calls) == 1  # первая формулировка сразу дала результат — бюджет не тратим дальше


def test_search_company_without_name_finds_market_not_company():
    with patch("src.core.search.web_search_raw",
               return_value=[{"title": "Топ мебельных мастерских КМВ", "body": "обзор рынка", "href": "https://example.com"}]):
        result = asyncio.run(company_scan.search_company("корпусная мебель", "КМВ", ""))
    assert result["ok"] is True
    assert result["stage"]["confidence"] == "unconfirmed"
    assert "рынок" in result["stage"]["reason"]


def test_search_company_finds_vk_presence_with_reviews_infers_growth():
    with patch("src.core.search.web_search_raw",
               return_value=[{"title": "Мебель+ | VK", "body": "4.8 рейтинг, отзывы клиентов",
                              "href": "https://vk.com/mebelplus"}]):
        result = asyncio.run(company_scan.search_company("корпусная мебель", "КМВ", "Мебель+"))
    assert result["stage"]["key"] == "growth"
    assert result["stage"]["confidence"] == "inferred"
    assert result["detected"]["aggregators"].get("vk") == "VK"


def test_search_company_finds_presence_without_reviews_infers_launch():
    with patch("src.core.search.web_search_raw",
               return_value=[{"title": "Мебель+ | Instagram", "body": "новый профиль",
                              "href": "https://instagram.com/mebelplus"}]):
        result = asyncio.run(company_scan.search_company("корпусная мебель", "КМВ", "Мебель+"))
    assert result["stage"]["key"] == "launch"
    assert result["stage"]["confidence"] == "inferred"


def test_search_company_generic_web_hit_stays_unconfirmed():
    with patch("src.core.search.web_search_raw",
               return_value=[{"title": "Мебель+ упоминание в статье", "body": "просто текст",
                              "href": "https://news.example.com/article"}]):
        result = asyncio.run(company_scan.search_company("корпусная мебель", "КМВ", "Мебель+"))
    assert result["stage"]["confidence"] == "unconfirmed"


def test_classify_result_host_recognizes_aggregators_and_subdomains():
    assert company_scan._classify_result_host("https://vk.com/mebelplus") == ("vk", "VK")
    assert company_scan._classify_result_host("https://www.instagram.com/mebelplus") == ("instagram", "Instagram")
    assert company_scan._classify_result_host("https://2gis.ru/pyatigorsk/firm/1") == ("2gis", "2ГИС")
    assert company_scan._classify_result_host("https://news.example.com") is None


def test_search_company_respects_time_budget_stub():
    """Бюджет — по времени, не по числу вызовов: если первая попытка "съела"
    почти весь остаток бюджета, следующие формулировки не запускаются."""
    def slow_search(query, max_results=6, timeout=8):
        import time as _time
        _time.sleep(0.6)
        return []
    with patch("src.office.company_scan._SEARCH_BUDGET_SECONDS", 1.5), \
         patch("src.core.search.web_search_raw", side_effect=slow_search):
        result = asyncio.run(company_scan.search_company("корпусная мебель", "КМВ", "Мебель+"))
    assert result["ok"] is False
    assert len(result["queries_tried"]) == 1  # вторая формулировка не запущена — бюджет исчерпан


def _run():
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ✓ {name}")
            passed += 1
    print(f"ВСЕ {passed} ТЕСТОВ ПРОШЛИ")


if __name__ == "__main__":
    # Windows-консоль часто в cp1251 — "✓" ронял ЛЮБОЙ тест этого файла
    # UnicodeEncodeError ДО единой строки реального результата (found: весь
    # набор tests/*.py был непроверяем из этой сессии на Windows).
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    _run()
