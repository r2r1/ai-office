"""
Индикатор «Понимание компании» — насколько офис знает бизнес клиента.

Считается из заполненности брифа, подключённых интеграций, наличия документов
в workspace и завершённых этапов анализа. Возвращает score 0–100 и разбивку
для попапа «Что нужно для роста понимания».
"""

from src.saas import context as ctx


def payload() -> dict:
    """Возвращает score (0–100) + items (что есть) + missing (чего не хватает)."""
    from src.office import brief as brief_module, connections as conn_module, workspace

    items: list[dict] = []
    missing: list[dict] = []
    score = 0

    b = brief_module.get()

    # Бриф: базовое описание бизнеса
    if b.get("summary"):
        score += 20
        items.append({"label": "Описание бизнеса", "icon": "✅"})
    else:
        missing.append({"label": "Описание бизнеса", "icon": "⬜",
                        "hint": "Расскажи CEO о своём бизнесе в чате"})

    # Мусорная цель («не знаю») не считается понятой — тот же сигнал качества, что
    # у effective_goal (brief.is_junk_goal), иначе индикатор врёт «цель ясна».
    if brief_module.has_meaningful_goal():
        score += 10
        items.append({"label": "Цель компании", "icon": "✅"})
    else:
        missing.append({"label": "Цель компании", "icon": "⬜",
                        "hint": "Укажи конкретную цель — что хочешь достичь"})

    if b.get("niche") or b.get("industry"):
        score += 5
        items.append({"label": "Ниша / рынок", "icon": "✅"})
    else:
        missing.append({"label": "Ниша / рынок", "icon": "⬜",
                        "hint": "Добавь отрасль и целевой рынок"})

    # Документы офиса в workspace
    td = ctx.tenant_dir()
    ws_docs = (td / "workspace" / "docs")
    has_research = (ws_docs / "research.md").exists()
    has_strategy = (ws_docs / "strategy.md").exists() or (td / "strategy.md").exists()
    has_tech = (ws_docs / "tech_design.md").exists() or (td / "tech_design.md").exists()

    if has_research:
        score += 10
        items.append({"label": "Исследование рынка", "icon": "✅"})
    else:
        missing.append({"label": "Исследование рынка", "icon": "🟡",
                        "hint": "Офис исследует рынок во время Bootstrap"})

    if has_strategy:
        score += 10
        items.append({"label": "Бизнес-стратегия", "icon": "✅"})
    else:
        missing.append({"label": "Бизнес-стратегия", "icon": "🟡",
                        "hint": "Стратег строит план после исследования"})

    if has_tech:
        score += 5
        items.append({"label": "Техническое задание", "icon": "✅"})
    else:
        missing.append({"label": "Техническое задание", "icon": "🟡",
                        "hint": "Архитектор проектирует стек после стратегии"})

    # Подключённые интеграции
    from src.integrations import registry as int_registry
    catalog = int_registry.catalog_payload()
    connected = [s for s in catalog if s.get("connected")]
    conn_score = min(20, len(connected) * 5)
    score += conn_score
    if connected:
        names = ", ".join(s.get("name", "") for s in connected[:3])
        items.append({"label": f"Интеграции: {names}", "icon": "✅"})

    not_connected = [s for s in catalog if not s.get("connected")][:3]
    for s in not_connected:
        missing.append({"label": f"Подключить {s.get('name','')}", "icon": "⬜",
                        "hint": s.get("description", "Интеграция с внешним сервисом")})

    # Код в рабочей папке
    files = workspace.list_files()
    code_files = [f for f in files if not f["path"].startswith("docs/")]
    if code_files:
        score += 10
        items.append({"label": f"Код: {len(code_files)} файл(ов)", "icon": "✅"})
    else:
        missing.append({"label": "Написан рабочий код", "icon": "⬜",
                        "hint": "Разработчик пишет код по ТЗ"})

    score = min(100, score)

    # Разбивка по доменам (Company Understanding Score по 5 измерениям) — тот же
    # набор сигналов, сгруппированный иначе, чтобы клиент видел, ЧТО именно
    # непонятно ("Продажи 12%" сильнее мотивирует подключить CRM, чем общий %).
    has_scan = bool(b.get("scan") and b["scan"].get("ok"))
    # ⚠️ Реальная CRM-интеграция (amocrm/bitrix24 — cred_fields/oauth_url непустые),
    # НЕ абстрактная Tool Router-заглушка способности "crm" (src/integrations/
    # crm.py, cred_fields=[]) — та всегда "connected" независимо от клиента и
    # раньше давала ЛЮБОМУ тенанту +60 к домену "sales" без единого реального
    # подключения (реальный баг, найден при добавлении Confidence — тот же
    # сигнал использует и она).
    crm_connected = any(s.get("connected") for s in catalog
                        if (s.get("cred_fields") or s.get("oauth_url"))
                        and any(k in s.get("name", "").lower() for k in ("crm", "amo", "bitrix")))
    domains = {
        "business": 40 + (30 if b.get("summary") else 0) + (30 if has_scan else 0),
        "marketing": 20 + (20 if has_scan else 0) + (20 if has_strategy else 0) +
                     (20 if any(s.get("connected") for s in catalog if s.get("name", "").lower()
                                in ("google sheets", "gmail")) else 0) + (20 if code_files else 0),
        "sales": 10 + (60 if crm_connected else 0) + (20 if b.get("avg_check_usd") else 0),
        "finance": 10 + (30 if b.get("budget_usd") or b.get("avg_check_usd") else 0),
        "team": 5 + (15 if has_tech else 0),
    }
    domains = {k: min(100, v) for k, v in domains.items()}

    # Интеграции БЕЗ cred_fields (website, и Tool Router-заглушки capability-
    # провайдеров crm/ads/payments/deploy/invoicing — cred_fields=[], см. их
    # модули в src/integrations/) всегда "подключены" независимо от реальных
    # действий клиента (registry.is_connected: "без кредов → True") — не
    # засчитываются как верифицированный внешний сигнал для Confidence, иначе
    # пустой бриф БЕЗ единого реального подключения уже давал бы бонусные очки.
    verified_connections = [s for s in connected if s.get("cred_fields") or s.get("oauth_url")]
    confidence, confidence_reasons = _confidence(b, verified_connections, crm_connected, has_research)

    return {
        "score": score,
        "items": items,
        "missing": missing[:6],
        "domains": domains,
        "confidence": confidence,
        "confidence_reasons": confidence_reasons,
    }


def _confidence(b: dict, connected: list, crm_connected: bool, has_research: bool) -> tuple[int, list[str]]:
    """Confidence ≠ Understanding score выше. Score — СКОЛЬКО данных есть (широта:
    заполнен ли бриф, написаны ли документы). Confidence — НАСКОЛЬКО ИМ МОЖНО
    ДОВЕРЯТЬ: самоотчёт клиента в текстовом поле ("сказал сам") весит меньше, чем
    факт, который офис ПРОВЕРИЛ САМ (автоскан сайта — реальные детектированные
    маркеры, не пересказ; подключённая интеграция — реальный аккаунт, не текст
    "у нас есть CRM"). Цель метрики — product-тезис "не ради продукта, а ради
    качества рекомендаций": владелец должен понимать, ПОЧЕМУ подключение CRM
    поднимает число, а не просто механику ради механики.
    """
    reasons: list[str] = []
    conf = 10  # база: хоть что-то заполнено в брифе — уже не полный ноль
    if b.get("summary"):
        reasons.append("есть описание бизнеса (со слов клиента)")
    if b.get("scan") and b["scan"].get("ok"):
        conf += 25
        reasons.append("автоскан сайта подтвердил реальные факты (не пересказ клиента)")
    conf += min(40, len(connected) * 10)
    if connected:
        reasons.append(f"подключено интеграций: {len(connected)} (реальные данные, не слова)")
    if crm_connected:
        conf += 10
        reasons.append("CRM-виджет обнаружен на сайте — видно, что клиент реально ведёт продажи")
    if has_research:
        conf += 15
        reasons.append("рынок исследован через внешние источники, не только со слов клиента")
    return min(100, conf), reasons[:5]
