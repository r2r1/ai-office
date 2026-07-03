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
    crm_connected = any(s.get("connected") for s in catalog if "crm" in s.get("name", "").lower()
                        or "amo" in s.get("name", "").lower() or "bitrix" in s.get("name", "").lower())
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

    return {
        "score": score,
        "items": items,
        "missing": missing[:6],
        "domains": domains,
    }
