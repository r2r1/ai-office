"""
Интеграция с Google Sheets.

Авторизация: Google OAuth 2.0 — нажми «Подключить Google» в разделе Доступы.
Одна кнопка даёт доступ сразу к Sheets, Gmail и Calendar.
"""

import httpx

from src.integrations.base import Action, CredField, Integration
from src.integrations import google_oauth

_API = "https://sheets.googleapis.com/v4/spreadsheets"


def _sheet_id_from_url(raw: str) -> str:
    """Если передан URL таблицы — извлекаем ID."""
    if "spreadsheets/d/" in raw:
        part = raw.split("spreadsheets/d/")[1]
        return part.split("/")[0]
    return raw.strip()


async def _get_token(creds: dict) -> str:
    return await google_oauth.get_valid_token()


async def _list_sheets(creds: dict, params: dict) -> str:
    token    = await _get_token(creds)
    sheet_id = _sheet_id_from_url(params.get("sheet_id") or "")
    if not sheet_id:
        raise RuntimeError("Нужен sheet_id — ID таблицы из URL (между /d/ и /edit).")
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(
            f"{_API}/{sheet_id}",
            headers={"Authorization": f"Bearer {token}"},
            params={"fields": "properties,sheets.properties"},
        )
    data = r.json()
    if "error" in data:
        raise RuntimeError(data["error"].get("message", str(data["error"])))
    title  = data.get("properties", {}).get("title", "Без названия")
    sheets = [s["properties"]["title"] for s in data.get("sheets", [])]
    return f"Таблица: «{title}»\nЛисты: {', '.join(sheets) or '(нет листов)'}"


async def _read_sheet(creds: dict, params: dict) -> str:
    token    = await _get_token(creds)
    sheet_id = _sheet_id_from_url(params.get("sheet_id") or "")
    range_   = (params.get("range") or "A1:Z100").strip()
    if not sheet_id:
        raise RuntimeError("Нужен sheet_id.")
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
    lines = ["\t".join(str(c) for c in row) for row in rows[:100]]
    return f"Данные {range_} ({len(rows)} строк):\n" + "\n".join(lines)


async def _write_sheet(creds: dict, params: dict) -> str:
    token    = await _get_token(creds)
    sheet_id = _sheet_id_from_url(params.get("sheet_id") or "")
    range_   = (params.get("range") or "A1").strip()
    values   = params.get("values")
    if not sheet_id:
        raise RuntimeError("Нужен sheet_id.")
    if not values or not isinstance(values, list):
        raise RuntimeError("Нужен 'values' — список строк: [[col1,col2],[col3,col4]]")
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
    return f"✅ Записано {data.get('updatedCells', '?')} ячеек в {range_}."


async def _append_rows(creds: dict, params: dict) -> str:
    token    = await _get_token(creds)
    sheet_id = _sheet_id_from_url(params.get("sheet_id") or "")
    range_   = (params.get("range") or "Sheet1").strip()
    values   = params.get("values")
    if not sheet_id:
        raise RuntimeError("Нужен sheet_id.")
    if not values or not isinstance(values, list):
        raise RuntimeError("Нужен 'values' — список строк: [[col1,col2],...]")
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
    return f"✅ Добавлено {updates.get('updatedRows', len(values))} строк."


async def _create_spreadsheet(creds: dict, params: dict) -> str:
    token = await _get_token(creds)
    title = (params.get("title") or "Новая таблица").strip()
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            _API,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"properties": {"title": title}},
        )
    data = r.json()
    if "error" in data:
        raise RuntimeError(data["error"].get("message", str(data["error"])))
    sid  = data.get("spreadsheetId", "")
    link = data.get("spreadsheetUrl", f"https://docs.google.com/spreadsheets/d/{sid}")
    return f"✅ Таблица создана: «{title}»\nID: {sid}\nСсылка: {link}"


INTEGRATION = Integration(
    name="google_sheets",
    title="Google Sheets",
    category="productivity",
    icon="📊",
    description="Читать, записывать и создавать Google Таблицы. Авторизация через Google OAuth.",
    how_to="Нажми «Подключить Google» — это даёт доступ сразу к Sheets, Gmail и Calendar.",
    cred_fields=[],      # OAuth — поля вводить не нужно
    oauth_url="/auth/google/start",
    actions={
        "list_sheets": Action(
            name="list_sheets",
            description="Показать листы таблицы.",
            handler=_list_sheets,
            params={"sheet_id": {"type": "string", "description": "ID таблицы (из URL) или полный URL"}},
            required=["sheet_id"],
        ),
        "read_sheet": Action(
            name="read_sheet",
            description="Прочитать данные из диапазона таблицы.",
            handler=_read_sheet,
            params={
                "sheet_id": {"type": "string", "description": "ID таблицы или URL"},
                "range":    {"type": "string", "description": "Диапазон: 'Sheet1!A1:D50' или 'A1:Z100'"},
            },
            required=["sheet_id"],
        ),
        "write_sheet": Action(
            name="write_sheet",
            description="Записать данные в диапазон (перезаписывает существующие).",
            handler=_write_sheet,
            params={
                "sheet_id": {"type": "string"},
                "range":    {"type": "string", "description": "Например 'Sheet1!A1'"},
                "values":   {"type": "array",  "description": "Строки: [[val1,val2],[val3,val4]]"},
            },
            required=["sheet_id", "values"],
        ),
        "append_rows": Action(
            name="append_rows",
            description="Добавить строки в конец таблицы.",
            handler=_append_rows,
            params={
                "sheet_id": {"type": "string"},
                "range":    {"type": "string", "description": "Лист, например 'Sheet1'"},
                "values":   {"type": "array",  "description": "Строки: [[val1,val2],...]"},
            },
            required=["sheet_id", "values"],
        ),
        "create_spreadsheet": Action(
            name="create_spreadsheet",
            description="Создать новую Google Таблицу.",
            handler=_create_spreadsheet,
            params={"title": {"type": "string", "description": "Название таблицы"}},
            required=["title"],
        ),
    },
)
