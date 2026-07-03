"""
Digital Infrastructure (Instant Learning, уровень 2) — единый список источников
данных о компании клиента: что уже подключено к платформе, что видно на сайте,
но платформа туда пока не пишет (capability-gap), и что не найдено вообще.

Три источника сигнала объединяются в одну картину:
  - registry.catalog_payload()  — реальные интеграции платформы (Telegram/GitHub/
    Google Sheets/Gmail/Calendar) — статус connected/available.
  - brief.get()["scan"]["detected"] — то, что company_scan.py увидел на САЙТЕ
    клиента (соцсети, CRM-виджеты, аналитика) — платформа туда не пишет, но
    видит, что клиент этим пользуется (или НЕ пользуется).

Не изобретает новых интеграций (реальный amoCRM/Bitrix24-модуль — отдельная
фича, см. docs/handoff.md); для detected_external источников действие —
попросить офис обратить внимание (raise_event/ask_user), не «подключить».
"""

_ANALYTICS_LABELS = {
    "ga4": "Google Analytics (GA4)",
    "yandex_metrika": "Яндекс.Метрика",
    "vk_pixel": "VK Pixel",
    "meta_pixel": "Meta Pixel",
}
_CRM_LABELS = {
    "amocrm": "amoCRM",
    "bitrix24": "Битрикс24",
}
_SOCIAL_LABELS = {
    "instagram": "Instagram",
    "vk": "VK",
    "telegram": "Telegram",
    "whatsapp": "WhatsApp",
    "youtube": "YouTube",
    "facebook": "Facebook",
}


def payload() -> dict:
    """Возвращает {"sources": [{key, label, category, icon, status, hint}]}.
    status: connected | available | detected_external | missing."""
    from src.integrations import registry as int_registry
    from src.office import brief as brief_module

    sources: list[dict] = []

    for integ in int_registry.catalog_payload():
        sources.append({
            "key": integ["name"], "label": integ.get("title") or integ["name"],
            "category": "platform", "icon": integ.get("icon") or "🔌",
            "status": "connected" if integ.get("connected") else "available",
            "hint": integ.get("description", ""),
        })

    b = brief_module.get()
    scan = (b or {}).get("scan") or {}
    detected = scan.get("detected") or {} if scan.get("ok") else {}

    analytics = detected.get("analytics") or {}
    for key, label in _ANALYTICS_LABELS.items():
        found = analytics.get(key, False)
        sources.append({
            "key": key, "label": label, "category": "analytics", "icon": "📊",
            "status": "detected_external" if found else "missing",
            "hint": ("Найден на сайте — офис не подключён к нему напрямую, но видит, что он есть"
                     if found else "Не найден на сайте — данные о посетителях не собираются"),
        })

    crm_widgets = detected.get("crm_widgets") or {}
    any_crm = any(crm_widgets.values())
    for key, label in _CRM_LABELS.items():
        found = crm_widgets.get(key, False)
        sources.append({
            "key": key, "label": label, "category": "crm", "icon": "🗂",
            "status": "detected_external" if found else "missing",
            "hint": ("Найден на сайте — попросите офис проанализировать сделки и воронку"
                     if found else ""),
        })
    if not any_crm:
        sources.append({
            "key": "crm_unknown", "label": "CRM не обнаружена", "category": "crm", "icon": "🗂",
            "status": "missing",
            "hint": "Если вы ведёте клиентов в CRM, скажите об этом офису в чате — он учтёт это в работе",
        })

    socials = detected.get("socials") or {}
    for key, label in _SOCIAL_LABELS.items():
        found = key in socials
        sources.append({
            "key": f"social_{key}", "label": label, "category": "social", "icon": "📱",
            "status": "detected_external" if found else "missing",
            "hint": (f"Ссылка найдена на сайте: {socials.get(key, '')}" if found else ""),
        })

    return {"sources": sources}
