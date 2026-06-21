"""
Интеграция с Google Sheets — чтение и запись таблиц.

Авторизация: сервисный аккаунт Google (JSON-ключ).
Как получить:
  1. console.cloud.google.com → APIs → Enable "Google Sheets API"
  2. IAM → Service Accounts → Create → скачать JSON-ключ
  3. Открой таблицу → «Настройки доступа» → добавь email сервис-аккаунта

Credential: поле "service_account_json" — полное содержимое JSON-ключа.
"""

import json
import time
import base64
import hashlib
import hmac

import httpx

from src.integrations.base import Action, CredField, Integration

_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_API = "https://sheets.googleapis.com/v4/spreadsheets"


def _make_jwt(sa: dict) -> str:
    """Создаёт JWT для Google service account без внешних библиотек."""
    from cryptography.hazmat.primitives import serialization, hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    now = int(time.time())
    header = base64.urlsafe_b64encode(json.dumps({"alg": "RS256", "typ": "JWT"}).encode()).rstrip(b"=")
    payload = base64.urlsafe_b64encode(json.dumps({
        "iss": sa["client_email"],
        "scope": _SCOPE,
        "aud": _TOKEN_URL,
        "iat": now,
        "exp": now + 3600,
    }).encode()).rstrip(b"=")
    signing_input = header + b"." + payload

    private_key = serialization.load_pem_private_key(sa["private_key"].encode(), password=None)
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    sig_b64 = base64.urlsafe_b64encode(signature).rstrip(b"=")
    return (signing_input + b"." + sig_b64).decode()


async def _access_token(creds: dict) -> str:
    raw = (creds.get("service_account_json") or creds.get("key") or creds.get("value") or "").strip()
    if not raw:
        raise RuntimeError("Нет service_account_json. Вставь содержимое JSON-ключа сервисного аккаунта.")
    try:
        sa = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError("service_account_json должен быть валидным JSON.")

    jwt = _make_jwt(sa)
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(_TOKEN_URL, data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": jwt,
        })
    data = r.json()
    token = data.get("access_token")
    if not token:
        raise RuntimeError(f"Не удалось получить токен: {data.get('error_description', data)}")
    return token


def _parse_range(params: dict) -> tuple[str, str]:
    sheet_id = (params.get("sheet_id") or "").strip()
    range_ = (params.get("range") or "A1:Z100").strip()
    if not sheet_id:
        raise RuntimeError("Нужен sheet_id — ID таблицы из URL: docs.google.com/spreadsheets/d/ID/")
    return sheet_id, range_


async def _read_sheet(creds: dict, params: dict) -> str:
    token = await _access_token(creds)
    sheet_id, range_ = _parse_range(params)
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(
            f"{_API}/{sheet_id}/values/{range_}",
            headers={"Authorization": f"Bearer {token}"},
        )
    data = r.json()
    if "error" in data:
        raise RuntimeError(data["error"].get("message", str(data["error"])))
    rows = data.get("values", [])
    if not rows:
        return "Таблица пуста (нет данных в указанном диапазоне)."
    lines = ["\t".join(str(c) for c in row) for row in rows]
    return f"Данные из {range_} ({len(rows)} строк):\n" + "\n".join(lines[:100])


async def _write_sheet(creds: dict, params: dict) -> str:
    token = await _access_token(creds)
    sheet_id, range_ = _parse_range(params)
    values = params.get("values")
    if not values or not isinstance(values, list):
        raise RuntimeError("Нужен 'values' — список строк [[col1,col2,...],...]")
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.put(
            f"{_API}/{sheet_id}/values/{range_}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"range": range_, "majorDimension": "ROWS", "values": values},
            params={"valueInputOption": "USER_ENTERED"},
        )
    data = r.json()
    if "error" in data:
        raise RuntimeError(data["error"].get("message", str(data["error"])))
    updated = data.get("updatedCells", 0)
    return f"✅ Записано {updated} ячеек в {range_}."


async def _append_rows(creds: dict, params: dict) -> str:
    token = await _access_token(creds)
    sheet_id, range_ = _parse_range(params)
    values = params.get("values")
    if not values or not isinstance(values, list):
        raise RuntimeError("Нужен 'values' — список строк [[col1,col2,...],...]")
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            f"{_API}/{sheet_id}/values/{range_}:append",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"values": values},
            params={"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"},
        )
    data = r.json()
    if "error" in data:
        raise RuntimeError(data["error"].get("message", str(data["error"])))
    updates = data.get("updates", {})
    return f"✅ Добавлено {updates.get('updatedRows', len(values))} строк в таблицу."


async def _list_sheets(creds: dict, params: dict) -> str:
    token = await _access_token(creds)
    sheet_id = (params.get("sheet_id") or "").strip()
    if not sheet_id:
        raise RuntimeError("Нужен sheet_id.")
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(
            f"{_API}/{sheet_id}",
            headers={"Authorization": f"Bearer {token}"},
            params={"fields": "properties,sheets.properties"},
        )
    data = r.json()
    if "error" in data:
        raise RuntimeError(data["error"].get("message", str(data["error"])))
    title = data.get("properties", {}).get("title", "Без названия")
    sheets = [s["properties"]["title"] for s in data.get("sheets", [])]
    return f"Таблица: «{title}»\nЛисты: {', '.join(sheets)}"


INTEGRATION = Integration(
    name="google_sheets",
    title="Google Sheets",
    icon="📊",
    description="Читать и записывать данные в Google Таблицы через сервисный аккаунт.",
    how_to=(
        "1. Откройте console.cloud.google.com\n"
        "2. APIs & Services → Enable API → «Google Sheets API»\n"
        "3. IAM & Admin → Service Accounts → Create Service Account\n"
        "4. Создайте ключ (JSON), скачайте файл\n"
        "5. Откройте нужную таблицу → Настройки доступа → добавьте email сервис-аккаунта как редактора\n"
        "6. Вставьте содержимое JSON-файла в поле ниже"
    ),
    cred_fields=[
        CredField(key="service_account_json", label="Service Account JSON (полное содержимое файла)", secret=True),
    ],
    actions={
        "list_sheets": Action(
            name="list_sheets",
            description="Показать листы таблицы.",
            handler=_list_sheets,
            params={"sheet_id": {"type": "string", "description": "ID таблицы из URL"}},
            required=["sheet_id"],
        ),
        "read_sheet": Action(
            name="read_sheet",
            description="Прочитать данные из диапазона таблицы.",
            handler=_read_sheet,
            params={
                "sheet_id": {"type": "string", "description": "ID таблицы из URL (между /d/ и /edit)"},
                "range": {"type": "string", "description": "Диапазон, например 'Sheet1!A1:D50' или просто 'A1:Z100'"},
            },
            required=["sheet_id"],
        ),
        "write_sheet": Action(
            name="write_sheet",
            description="Записать данные в диапазон (перезаписывает).",
            handler=_write_sheet,
            params={
                "sheet_id": {"type": "string"},
                "range": {"type": "string", "description": "Например 'Sheet1!A1'"},
                "values": {"type": "array", "description": "Массив строк: [[val1,val2],[val3,val4]]"},
            },
            required=["sheet_id", "values"],
        ),
        "append_rows": Action(
            name="append_rows",
            description="Добавить строки в конец таблицы.",
            handler=_append_rows,
            params={
                "sheet_id": {"type": "string"},
                "range": {"type": "string", "description": "Лист, например 'Sheet1'"},
                "values": {"type": "array", "description": "Массив строк: [[val1,val2],...]"},
            },
            required=["sheet_id", "values"],
        ),
    },
)
