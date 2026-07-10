"""
Провайдер способности «CRM» — Bitrix24 через входящий вебхук (REST API).

В отличие от crm.py (TEST-режим, mock, всегда "подключён") — это РЕАЛЬНЫЙ
провайдер: требует входящий вебхук клиента (Bitrix24 → Настройки → Вебхуки →
Входящий вебхук, права crm) и реально пишет лид через crm.lead.add.json.

Обе интеграции закрывают ОДНУ способность (capability "crm", office/capability.py,
backed_by=("crm", "crm_bitrix24") — "have", если подключён хотя бы один). Какая
из двух реально отвечает на use_capability("сохранить лида в CRM"), решает
tool_router обычным скорингом (needs.py): если подключены обе — агент видит
двух кандидатов и либо получает явного лидера, либо развилку (см. tests/
test_tool_router.py — та же логика, что для любых двух провайдеров одной
способности, ничего специфичного для CRM тут нет).
"""

import httpx

from src.integrations.base import Action, CredField, Integration
from src.office import leads as leads_module


def _webhook(creds: dict) -> str:
    url = (creds.get("webhook_url") or "").strip().rstrip("/")
    if not url:
        raise RuntimeError(
            "Нет входящего вебхука Bitrix24. Запроси у пользователя через ask_user "
            "(Bitrix24 → Настройки → Вебхуки → Входящий вебхук, права crm)."
        )
    return url


async def _call(webhook: str, method: str, payload: dict) -> dict:
    url = f"{webhook}/{method}.json"
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(url, json=payload)
    try:
        data = resp.json()
    except ValueError:
        raise RuntimeError(f"Bitrix24 вернул не-JSON (HTTP {resp.status_code})")
    if "error" in data:
        raise RuntimeError(f"Bitrix24 API: {data.get('error_description', data['error'])}")
    return data


async def _export_lead(creds: dict, params: dict) -> str:
    webhook = _webhook(creds)
    lead_id = (params.get("lead_id") or "").strip()
    lead = leads_module.get(lead_id)
    if not lead:
        raise RuntimeError(f"Лид {lead_id} не найден во внутренней CRM.")
    payload = {"fields": {
        "TITLE": lead.get("name") or "Заявка с сайта",
        "NAME": lead.get("name") or "",
        "PHONE": [{"VALUE": lead.get("contact") or "", "VALUE_TYPE": "WORK"}],
        "COMMENTS": lead.get("message") or "",
        "SOURCE_ID": "WEB",
    }}
    data = await _call(webhook, "crm.lead.add", payload)
    bitrix_id = data.get("result")
    return f"Лид «{lead.get('name', '')}» создан в Bitrix24, ID: {bitrix_id}."


INTEGRATION = Integration(
    name="crm_bitrix24",
    title="Bitrix24 CRM",
    category="other",
    icon="🧱",
    description="Реальный экспорт лида в Bitrix24 через входящий вебхук (crm.lead.add).",
    how_to="Bitrix24 → Настройки → Вебхуки → Входящий вебхук → права crm. "
           "Скопируй итоговый URL (…/rest/1/xxxxxxxx/) целиком.",
    cred_fields=[CredField(key="webhook_url", label="URL входящего вебхука Bitrix24")],
    actions={
        "export_lead": Action(
            name="export_lead",
            description="Создать лид/сделку в Bitrix24 по данным внутреннего лида.",
            handler=_export_lead,
            params={"lead_id": {"type": "string", "description": "id лида из внутренней CRM"}},
            required=["lead_id"],
            synonyms=["bitrix", "битрикс", "bitrix24", "crm", "экспортировать лида"],
        ),
    },
)
