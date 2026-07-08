"""
Интеграция «Внешняя CRM» — TEST-режим экспорта лидов (docs/product-capability-gaps.md п.7).

Внутренняя мини-CRM (`src/office/leads.py`) остаётся источником истины —
эта интеграция НЕ дублирует её, а имитирует то, что сделает реальный экспорт
в Pipedrive/HubSpot/amoCRM: отдаёт лиду внешний contact_id в форме, которую
вернул бы реальный сервис (crm_contacts.json — локальный "слепок" внешней CRM).
Когда появится реальный ключ — меняется тело `_export_lead` (реальный вызов
API вместо генерации записи), контракт действия для агента не меняется.
"""

import time
import uuid

from src.integrations.base import Action, Integration
from src.office import leads as leads_module
from src.saas import context as ctx

_FILE = "crm_contacts.json"


def _all() -> list[dict]:
    return ctx.read_json(_FILE, [])


def _save(items: list[dict]) -> None:
    ctx.write_json(_FILE, items)


def get_by_lead(lead_id: str) -> dict | None:
    for c in _all():
        if c["lead_id"] == lead_id:
            return c
    return None


def list_contacts() -> list[dict]:
    return sorted(_all(), key=lambda c: c.get("created_ts", 0), reverse=True)


async def _export_lead(creds: dict, params: dict) -> str:
    lead_id = (params.get("lead_id") or "").strip()
    lead = leads_module.get(lead_id)
    if lead is None:
        return f"Лид {lead_id} не найден."
    existing = get_by_lead(lead_id)
    if existing:
        return f"Лид {lead_id} уже экспортирован ранее: внешний contact_id {existing['contact_id']}."

    contact_id = f"test_crm_{uuid.uuid4().hex[:10]}"
    entry = {
        "contact_id": contact_id, "lead_id": lead_id, "name": lead.get("name", ""),
        "contact": lead.get("contact", ""), "created_ts": time.time(),
    }
    items = _all()
    items.append(entry)
    _save(items)
    return (f"Лид «{lead.get('name', '')}» экспортирован в тестовую внешнюю CRM: "
            f"contact_id {contact_id}. ⚠️ Реальная CRM (Pipedrive/HubSpot/amoCRM) не подключена — "
            f"запись живёт только внутри платформы, синхронизации с реальным сервисом нет.")


INTEGRATION = Integration(
    name="crm",
    title="Внешняя CRM",
    category="other",
    icon="🗂️",
    description="TEST-режим экспорта лидов во внешнюю CRM: присваивает external contact_id "
                "в форме реального ответа Pipedrive/HubSpot, пока сервис не подключён.",
    how_to="Сейчас работает в тестовом режиме без ключей. Реальная CRM (Pipedrive/HubSpot/"
           "amoCRM) подключится сюда, когда появится доступ.",
    cred_fields=[],
    actions={
        "export_lead": Action(
            name="export_lead",
            description="Экспортировать лида во внешнюю CRM (тестовый режим).",
            handler=_export_lead,
            params={"lead_id": {"type": "string", "description": "id лида из внутренней CRM"}},
            required=["lead_id"],
            synonyms=["crm", "внешняя crm", "pipedrive", "hubspot", "amocrm", "экспортировать лида"],
        ),
    },
)
