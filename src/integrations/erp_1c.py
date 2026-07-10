"""
Провайдер способности «ERP» — 1С через OData Standard Interface.

ERP — ОТДЕЛЬНАЯ способность от CRM (office/capability.py): 1С у клиента —
не альтернатива внешней CRM, а система учёта (контрагенты/документы), и
задача агента к ней принципиально другая («создать контрагента в 1С»,
не «сохранить лида в CRM»). Заводить как ещё один провайдер способности
"crm" было бы неверно семантически, даже если механика вызова похожа.

Два реальных отличия от crm_bitrix24.py (не косметика — структурные):

1. НЕТ фиксированной схемы полей. У Bitrix24 `crm.lead.add` с TITLE/NAME/PHONE
   одинаков у всех клиентов — у 1С каждая конфигурация (УТ/БП/ERP/Розница)
   называет сущности и поля по-своему (`Catalog_Контрагенты` у одного,
   `Catalog_Клиенты` у другого). Поэтому вместо захардкоженных полей —
   `entity` (имя сущности OData) и `field_map` (JSON-строка: наши поля лида →
   имена полей 1С), которые клиент/интегратор вводит при подключении. Это и
   есть Слой маппинга домена, которого не хватало генерическому провайдеру.

2. 1С почти всегда on-premise, не облачный SaaS. База должна быть ОПУБЛИКОВАНА
   (IIS/Apache, HTTPS, доступна снаружи) — без этого интеграция физически
   невозможна независимо от того, как написан код здесь. how_to предупреждает
   явно, чтобы агент не тратил попытки на заведомо недостижимую цель, а сразу
   спросил владельца, опубликована ли база.
"""

import json

import httpx

from src.integrations.base import Action, CredField, Integration
from src.office import leads as leads_module

# Поля лида, которые МОГУТ быть в field_map (наша сторона соответствия).
_LEAD_FIELDS = ("name", "contact", "message")


def _creds(creds: dict) -> tuple[str, str, str, str, dict]:
    base_url = (creds.get("base_url") or "").strip().rstrip("/")
    login = (creds.get("login") or "").strip()
    password = (creds.get("password") or "").strip()
    entity = (creds.get("entity") or "").strip()
    if not (base_url and login and password and entity):
        raise RuntimeError(
            "Нет полной настройки 1С (base_url/login/password/entity). Запроси у "
            "пользователя через ask_user: URL опубликованной базы, логин/пароль "
            "пользователя API и имя сущности OData (например Catalog_Контрагенты). "
            "⚠️ База должна быть опубликована и доступна по HTTPS ИЗВНЕ — если 1С "
            "работает только в локальной сети клиента, без публикации (IIS/Apache) "
            "или туннеля интеграция невозможна в принципе, спроси об этом отдельно."
        )
    raw_map = (creds.get("field_map") or "").strip()
    try:
        field_map = json.loads(raw_map) if raw_map else {}
    except ValueError:
        raise RuntimeError(
            f"field_map — не валидный JSON: {raw_map!r}. Ожидается вида "
            '{"name": "Description", "contact": "Телефон"}.'
        )
    return base_url, login, password, entity, field_map


def _map_fields(lead: dict, field_map: dict) -> dict:
    """Наши поля лида → поля 1С по field_map. Поле лида без соответствия в
    field_map просто не передаётся (не гадаем чужое имя сущности)."""
    out = {}
    for our_key in _LEAD_FIELDS:
        their_key = field_map.get(our_key)
        if their_key:
            out[their_key] = lead.get(our_key) or ""
    return out


async def _create_counterparty(creds: dict, params: dict) -> str:
    base_url, login, password, entity, field_map = _creds(creds)
    lead_id = (params.get("lead_id") or "").strip()
    lead = leads_module.get(lead_id)
    if not lead:
        raise RuntimeError(f"Лид {lead_id} не найден во внутренней CRM.")
    if not field_map:
        raise RuntimeError(
            "field_map пуст — не знаю, в какие поля 1С писать имя/телефон. "
            "Запроси у пользователя соответствие полей через ask_user."
        )
    payload = _map_fields(lead, field_map)
    url = f"{base_url}/{entity}"
    async with httpx.AsyncClient(timeout=20, auth=(login, password)) as client:
        resp = await client.post(url, json=payload, headers={"Content-Type": "application/json"})
    if resp.status_code >= 400:
        raise RuntimeError(f"1С OData вернул HTTP {resp.status_code}: {resp.text[:300]}")
    try:
        data = resp.json()
    except ValueError:
        raise RuntimeError(f"1С вернул не-JSON (HTTP {resp.status_code})")
    ref = data.get("Ref_Key", "")
    return f"Контрагент «{lead.get('name', '')}» создан в 1С ({entity}), Ref_Key: {ref}."


async def _check_connection(creds: dict, params: dict) -> str:
    """Лёгкая проверка: GET метаданных OData без создания записей — чтобы
    агент/владелец мог убедиться, что база вообще доступна извне, ДО того как
    пытаться писать в неё (частая точка провала — база не опубликована)."""
    base_url, login, password, _entity, _field_map = _creds(creds)
    url = f"{base_url}/$metadata"
    async with httpx.AsyncClient(timeout=15, auth=(login, password)) as client:
        resp = await client.get(url)
    if resp.status_code >= 400:
        return f"1С недоступна: HTTP {resp.status_code}. Проверь, опубликована ли база и верны ли логин/пароль."
    return "1С доступна: OData отвечает."


INTEGRATION = Integration(
    name="erp_1c",
    title="1С (ERP)",
    category="other",
    icon="🧾",
    description="Учёт через опубликованный OData-интерфейс 1С (контрагенты/документы). "
                "Схема полей у каждой конфигурации своя — настраивается field_map при подключении.",
    how_to="1С → Администрирование → Публикация на веб-сервере → включить OData "
           "(галочка 'Standard OData Interface'). Скопируй URL вида "
           "https://ваш-сервер/база/odata/standard.odata/. Нужен пользователь 1С "
           "с правами на нужную сущность (Catalog_Контрагенты и т.п.) и REST/API-доступ. "
           "⚠️ Если 1С только в локальной сети — без публикации наружу (IIS/Apache) "
           "или туннеля (ngrok/Cloudflare Tunnel) интеграция невозможна.",
    cred_fields=[
        CredField(key="base_url", label="URL OData базы (…/odata/standard.odata/)"),
        CredField(key="login", label="Логин пользователя 1С", secret=False),
        CredField(key="password", label="Пароль"),
        CredField(key="entity", label="Сущность OData (напр. Catalog_Контрагенты)", secret=False),
        CredField(key="field_map", label='Соответствие полей JSON, напр. {"name":"Description","contact":"Телефон"}',
                  secret=False),
    ],
    actions={
        "create_counterparty": Action(
            name="create_counterparty",
            description="Создать контрагента в 1С из внутреннего лида (по настроенному field_map).",
            handler=_create_counterparty,
            params={"lead_id": {"type": "string", "description": "id лида из внутренней CRM"}},
            required=["lead_id"],
            synonyms=["1с", "1c", "erp", "контрагент", "создать в 1с"],
        ),
        "check_connection": Action(
            name="check_connection",
            description="Проверить, доступна ли база 1С по сети (без создания записей).",
            handler=_check_connection,
            params={},
            required=[],
            synonyms=["проверить 1с", "проверить erp", "доступна ли 1с"],
        ),
    },
)
