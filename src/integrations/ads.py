"""
Интеграция «Реклама» — TEST-режим без реального рекламного кабинета.

Ни Google Ads, ни Meta Ads ключа сегодня нет (docs/product-capability-gaps.md
п.7). Как и в payments.py/deploy.py/invoicing.py — рабочая песочница: заводит
кампанию (ad_campaigns.json) и отдаёт статистику в форме, которую вернёт
реальный рекламный кабинет (показы/клики/расход), детерминированно растущую
от времени с момента создания — не случайные числа при каждом запросе (агент
должен видеть последовательный рост, а не дёргающиеся цифры туда-сюда).
Когда появится реальный ключ — меняется тело `_create_campaign`/`_get_stats`,
контракт действия не меняется.
"""

import hashlib
import time
import uuid

from src.integrations.base import Action, Integration
from src.saas import context as ctx

_FILE = "ad_campaigns.json"
_PLATFORMS = ("google_ads", "meta_ads")


def _all() -> list[dict]:
    return ctx.read_json(_FILE, [])


def _save(items: list[dict]) -> None:
    ctx.write_json(_FILE, items)


def get(campaign_id: str) -> dict | None:
    for c in _all():
        if c["id"] == campaign_id:
            return c
    return None


def list_campaigns() -> list[dict]:
    return sorted(_all(), key=lambda c: c.get("created_ts", 0), reverse=True)


def _deterministic_stats(campaign_id: str, budget: float, age_hours: float) -> dict:
    """Псевдо-статистика: детерминированная (по id кампании — не меняется между
    вызовами при том же возрасте), растёт со временем, масштабируется бюджетом.
    Не случайные числа: одинаковый запрос в одну и ту же минуту даёт тот же ответ."""
    seed = int(hashlib.sha256(campaign_id.encode()).hexdigest()[:8], 16)
    ctr_base = 0.008 + (seed % 30) / 1000  # 0.8%-3.7% CTR — правдоподобный разброс
    impressions = int(budget * 40 * min(age_hours, 24 * 14))  # плато после 2 недель
    clicks = int(impressions * ctr_base)
    spend = round(min(budget * min(age_hours / 24, 14), budget * 14), 2)
    return {"impressions": impressions, "clicks": clicks, "ctr": round(ctr_base * 100, 2), "spend": spend}


async def _create_campaign(creds: dict, params: dict) -> str:
    platform = (params.get("platform") or "google_ads").strip().lower()
    if platform not in _PLATFORMS:
        platform = "google_ads"
    headline = (params.get("headline") or "").strip()
    if not headline:
        return "Нужен headline (заголовок объявления)."
    try:
        budget = round(float(params.get("budget") or 0), 2)
    except (TypeError, ValueError):
        return "Нужен budget — число больше нуля (дневной бюджет)."
    if budget <= 0:
        return "budget должен быть больше нуля."

    cid = f"test_camp_{uuid.uuid4().hex[:8]}"
    entry = {
        "id": cid, "platform": platform, "headline": headline, "budget": budget,
        "status": "active", "created_ts": time.time(),
    }
    items = _all()
    items.append(entry)
    _save(items)
    platform_ru = {"google_ads": "Google Ads", "meta_ads": "Meta Ads"}[platform]
    return (f"Тестовая кампания создана: id {cid}, платформа {platform_ru}, "
            f"«{headline}», дневной бюджет {budget}. "
            f"⚠️ Реальный рекламный кабинет не подключён — показов и кликов в интернете "
            f"не будет; get_campaign_stats вернёт правдоподобную тестовую динамику, чтобы "
            f"агент и владелец видели форму отчёта заранее.")


async def _get_campaign_stats(creds: dict, params: dict) -> str:
    cid = (params.get("campaign_id") or "").strip()
    c = get(cid)
    if c is None:
        return f"Кампания {cid} не найдена."
    age_hours = (time.time() - c["created_ts"]) / 3600
    stats = _deterministic_stats(cid, c["budget"], age_hours)
    return (f"Кампания «{c['headline']}» ({c['platform']}): показов {stats['impressions']}, "
            f"кликов {stats['clicks']} (CTR {stats['ctr']}%), потрачено {stats['spend']} "
            f"из дневного бюджета {c['budget']}. [TEST-данные]")


INTEGRATION = Integration(
    name="ads",
    title="Реклама",
    category="other",
    icon="📢",
    description="TEST-режим рекламных кампаний (Google Ads/Meta Ads): заводит кампанию "
                "и отдаёт правдоподобную тестовую статистику, пока нет реального кабинета.",
    how_to="Сейчас работает в тестовом режиме без ключей — реальных показов не будет. "
           "Google Ads/Meta Ads подключится сюда, когда появится доступ к рекламному кабинету.",
    cred_fields=[],
    actions={
        "create_campaign": Action(
            name="create_campaign",
            description="Создать рекламную кампанию (тестовый режим, пока нет доступа к кабинету).",
            handler=_create_campaign,
            params={
                "platform": {"type": "string", "description": "google_ads или meta_ads"},
                "headline": {"type": "string", "description": "Заголовок объявления"},
                "budget": {"type": "number", "description": "Дневной бюджет"},
            },
            required=["headline", "budget"],
            synonyms=["реклама", "рекламная кампания", "google ads", "meta ads", "таргет", "продвижение"],
        ),
        "get_campaign_stats": Action(
            name="get_campaign_stats",
            description="Статистика кампании: показы, клики, расход.",
            handler=_get_campaign_stats,
            params={"campaign_id": {"type": "string", "description": "id кампании"}},
            required=["campaign_id"],
        ),
    },
)
