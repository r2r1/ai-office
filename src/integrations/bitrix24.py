"""
Провайдер способности «CRM» — Bitrix24 через OAuth-приложение (см.
bitrix24_oauth.py), а не входящий вебхук. Отдельный provider от
crm_bitrix24.py (там — вебхук, проще для клиента, но ограничен правами
вебхука): обе закрывают одну способность "crm" (office/capability.py,
backed_by), какая реально отвечает на use_capability — решает tool_router
обычным скорингом, как для любых двух провайдеров одной способности.
"""

import httpx

from src.integrations.base import Action, CredField, Integration
from src.integrations import bitrix24_oauth
from src.office import leads as leads_module


async def _call(method: str, payload: dict) -> dict:
    token, domain = await bitrix24_oauth.get_valid_token()
    url = f"https://{domain}/rest/{method}.json"
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(url, params={"auth": token}, json=payload)
    try:
        data = resp.json()
    except ValueError:
        raise RuntimeError(f"Bitrix24 вернул не-JSON (HTTP {resp.status_code})")
    if "error" in data:
        raise RuntimeError(f"Bitrix24 API: {data.get('error_description', data['error'])}")
    return data


async def _export_lead(creds: dict, params: dict) -> str:
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
    data = await _call("crm.lead.add", payload)
    bitrix_id = data.get("result")
    return f"Лид «{lead.get('name', '')}» создан в Bitrix24, ID: {bitrix_id}."


INTEGRATION = Integration(
    name="bitrix24",
    title="Bitrix24 (OAuth)",
    category="other",
    icon="🧱",
    description="Экспорт лида в Bitrix24 через OAuth-приложение (полный REST API портала, не только вебхук).",
    how_to="Нажми «Войти через Bitrix24» и введи домен своего портала (например my-company.bitrix24.ru).",
    oauth_url="/auth/bitrix24/login",
    cred_fields=[CredField(key="access_token", label="Bitrix24 access token")],
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
