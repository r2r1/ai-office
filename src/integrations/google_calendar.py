"""
Интеграция с Google Calendar.

Авторизация: Google OAuth 2.0 — нажми «Подключить Google» в разделе Доступы.
Один вход — доступ к Sheets, Gmail и Calendar сразу.

Действия: список событий, создание, обновление, удаление, поиск по свободному времени.
"""

from datetime import datetime, timezone, timedelta

import httpx

from src.integrations.base import Action, Integration
from src.integrations import google_oauth

_API = "https://www.googleapis.com/calendar/v3"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _list_calendars(creds: dict, params: dict) -> str:
    token = await google_oauth.get_valid_token()
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(f"{_API}/users/me/calendarList",
                             headers={"Authorization": f"Bearer {token}"})
    data = r.json()
    if "error" in data:
        raise RuntimeError(data["error"].get("message", str(data["error"])))
    items = data.get("items", [])
    if not items:
        return "Нет доступных календарей."
    lines = [f"• {c['summary']} (id: {c['id']})" for c in items]
    return "Ваши календари:\n" + "\n".join(lines)


async def _list_events(creds: dict, params: dict) -> str:
    token      = await google_oauth.get_valid_token()
    cal_id     = (params.get("calendar_id") or "primary").strip()
    max_res    = int(params.get("max_results") or 10)
    time_min   = (params.get("time_min") or _now_iso()).strip()
    time_max   = params.get("time_max", "")
    query      = params.get("query", "")

    api_params: dict = {
        "timeMin":      time_min,
        "maxResults":   max_res,
        "singleEvents": "true",
        "orderBy":      "startTime",
    }
    if time_max:
        api_params["timeMax"] = time_max
    if query:
        api_params["q"] = query

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(
            f"{_API}/calendars/{cal_id}/events",
            headers={"Authorization": f"Bearer {token}"},
            params=api_params,
        )
    data = r.json()
    if "error" in data:
        raise RuntimeError(data["error"].get("message", str(data["error"])))

    events = data.get("items", [])
    if not events:
        return "Нет событий в указанном периоде."

    lines = []
    for e in events:
        start = e.get("start", {})
        dt    = start.get("dateTime", start.get("date", "?"))[:16].replace("T", " ")
        title = e.get("summary", "Без названия")
        eid   = e.get("id", "")
        loc   = f" 📍{e['location']}" if e.get("location") else ""
        lines.append(f"• {dt} — {title}{loc} [id: {eid}]")

    return f"События ({len(events)}):\n" + "\n".join(lines)


async def _create_event(creds: dict, params: dict) -> str:
    token      = await google_oauth.get_valid_token()
    cal_id     = (params.get("calendar_id") or "primary").strip()
    title      = (params.get("title") or "").strip()
    start      = (params.get("start") or "").strip()
    end        = (params.get("end") or "").strip()
    desc       = params.get("description", "")
    location   = params.get("location", "")
    attendees  = params.get("attendees", [])  # список email
    tz         = params.get("timezone", "Europe/Moscow")
    all_day    = params.get("all_day", False)

    if not title:
        raise RuntimeError("Нужно название события (title).")
    if not start:
        raise RuntimeError("Нужна дата/время начала (start) в формате ISO 8601.")

    if all_day:
        # Для событий на весь день — только дата без времени
        body: dict = {
            "summary": title,
            "start":   {"date": start[:10]},
            "end":     {"date": (end or start)[:10]},
        }
    else:
        if not end:
            # По умолчанию 1 час
            from dateutil.parser import parse as _parse
            dt_start = _parse(start)
            end = (dt_start + timedelta(hours=1)).isoformat()
        body = {
            "summary": title,
            "start":   {"dateTime": start, "timeZone": tz},
            "end":     {"dateTime": end,   "timeZone": tz},
        }

    if desc:
        body["description"] = desc
    if location:
        body["location"] = location
    if attendees:
        lst = attendees if isinstance(attendees, list) else [attendees]
        body["attendees"] = [{"email": e} for e in lst]

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            f"{_API}/calendars/{cal_id}/events",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=body,
            params={"sendUpdates": "all"},
        )
    data = r.json()
    if "error" in data:
        raise RuntimeError(data["error"].get("message", str(data["error"])))

    link = data.get("htmlLink", "")
    eid  = data.get("id", "")
    return f"✅ Событие создано: «{title}»\nID: {eid}\nСсылка: {link}"


async def _update_event(creds: dict, params: dict) -> str:
    token    = await google_oauth.get_valid_token()
    cal_id   = (params.get("calendar_id") or "primary").strip()
    event_id = (params.get("event_id") or "").strip()
    if not event_id:
        raise RuntimeError("Нужен event_id (из list_events).")

    # Получаем текущее событие
    async with httpx.AsyncClient(timeout=20) as client:
        existing = (await client.get(
            f"{_API}/calendars/{cal_id}/events/{event_id}",
            headers={"Authorization": f"Bearer {token}"},
        )).json()

    if "error" in existing:
        raise RuntimeError(existing["error"].get("message", "Событие не найдено"))

    # Патчим только переданные поля
    patch: dict = {}
    if params.get("title"):
        patch["summary"] = params["title"]
    if params.get("description") is not None:
        patch["description"] = params["description"]
    if params.get("location") is not None:
        patch["location"] = params["location"]
    if params.get("start"):
        tz = params.get("timezone", "Europe/Moscow")
        patch["start"] = {"dateTime": params["start"], "timeZone": tz}
    if params.get("end"):
        tz = params.get("timezone", "Europe/Moscow")
        patch["end"] = {"dateTime": params["end"], "timeZone": tz}

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.patch(
            f"{_API}/calendars/{cal_id}/events/{event_id}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=patch,
        )
    data = r.json()
    if "error" in data:
        raise RuntimeError(data["error"].get("message", str(data["error"])))

    return f"✅ Событие обновлено: «{data.get('summary', event_id)}»"


async def _delete_event(creds: dict, params: dict) -> str:
    token    = await google_oauth.get_valid_token()
    cal_id   = (params.get("calendar_id") or "primary").strip()
    event_id = (params.get("event_id") or "").strip()
    if not event_id:
        raise RuntimeError("Нужен event_id.")

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.delete(
            f"{_API}/calendars/{cal_id}/events/{event_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
    if r.status_code in (200, 204):
        return f"✅ Событие {event_id} удалено."
    try:
        raise RuntimeError(r.json().get("error", {}).get("message", f"HTTP {r.status_code}"))
    except (ValueError, AttributeError):
        raise RuntimeError(f"Ошибка удаления: HTTP {r.status_code}")


async def _free_busy(creds: dict, params: dict) -> str:
    """Проверяет занятость в указанном промежутке (free/busy query)."""
    token    = await google_oauth.get_valid_token()
    time_min = (params.get("time_min") or _now_iso()).strip()
    time_max = (params.get("time_max") or "").strip()
    if not time_max:
        # По умолчанию следующие 24 часа
        from dateutil.parser import parse as _parse
        time_max = (_parse(time_min) + timedelta(days=1)).isoformat()
    cal_ids  = params.get("calendar_ids", ["primary"])
    if isinstance(cal_ids, str):
        cal_ids = [cal_ids]

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            f"{_API}/freeBusy",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "timeMin":  time_min,
                "timeMax":  time_max,
                "items":    [{"id": c} for c in cal_ids],
            },
        )
    data = r.json()
    if "error" in data:
        raise RuntimeError(data["error"].get("message", str(data["error"])))

    lines = []
    for cal_id, info in data.get("calendars", {}).items():
        busy = info.get("busy", [])
        if not busy:
            lines.append(f"• {cal_id}: свободен")
        else:
            for b in busy:
                s = b.get("start", "?")[:16].replace("T", " ")
                e = b.get("end", "?")[:16].replace("T", " ")
                lines.append(f"• {cal_id}: занят {s} – {e}")

    return "Занятость:\n" + "\n".join(lines) if lines else "Нет данных."


INTEGRATION = Integration(
    name="google_calendar",
    title="Google Calendar",
    category="productivity",
    icon="📅",
    description="Управление событиями в Google Calendar. Авторизация через Google OAuth.",
    how_to="Нажми «Подключить Google» — это даёт доступ сразу к Calendar, Gmail и Sheets.",
    cred_fields=[],
    oauth_url="/auth/google/start",
    actions={
        "list_calendars": Action(
            name="list_calendars",
            description="Показать список календарей пользователя.",
            handler=_list_calendars,
        ),
        "list_events": Action(
            name="list_events",
            description="Показать предстоящие события. Поддерживает фильтр по дате и поисковый запрос.",
            handler=_list_events,
            params={
                "calendar_id": {"type": "string",  "description": "ID календаря (default: primary)"},
                "max_results": {"type": "integer", "description": "Максимум событий (default: 10)"},
                "time_min":    {"type": "string",  "description": "С какой даты ISO 8601 (default: сейчас)"},
                "time_max":    {"type": "string",  "description": "По какую дату ISO 8601 (опц.)"},
                "query":       {"type": "string",  "description": "Поисковый запрос по тексту события"},
            },
        ),
        "create_event": Action(
            name="create_event",
            description="Создать событие в Google Calendar.",
            handler=_create_event,
            params={
                "title":       {"type": "string",  "description": "Название события"},
                "start":       {"type": "string",  "description": "Начало ISO 8601: '2024-06-10T10:00:00+03:00'"},
                "end":         {"type": "string",  "description": "Конец ISO 8601 (default: start + 1 час)"},
                "description": {"type": "string",  "description": "Описание"},
                "location":    {"type": "string",  "description": "Место проведения"},
                "calendar_id": {"type": "string",  "description": "ID календаря (default: primary)"},
                "timezone":    {"type": "string",  "description": "Часовой пояс (default: Europe/Moscow)"},
                "attendees":   {"type": "array",   "description": "Список email приглашённых"},
                "all_day":     {"type": "boolean", "description": "Событие на весь день (тогда start = YYYY-MM-DD)"},
            },
            required=["title", "start"],
        ),
        "update_event": Action(
            name="update_event",
            description="Изменить существующее событие (частичное обновление — PATCH).",
            handler=_update_event,
            params={
                "event_id":    {"type": "string", "description": "ID события (из list_events)"},
                "calendar_id": {"type": "string", "description": "ID календаря"},
                "title":       {"type": "string", "description": "Новое название"},
                "start":       {"type": "string", "description": "Новое время начала ISO 8601"},
                "end":         {"type": "string", "description": "Новое время конца ISO 8601"},
                "description": {"type": "string", "description": "Новое описание"},
                "location":    {"type": "string", "description": "Новое место"},
            },
            required=["event_id"],
        ),
        "delete_event": Action(
            name="delete_event",
            description="Удалить событие из Google Calendar.",
            handler=_delete_event,
            params={
                "event_id":    {"type": "string", "description": "ID события (из list_events)"},
                "calendar_id": {"type": "string", "description": "ID календаря (default: primary)"},
            },
            required=["event_id"],
        ),
        "free_busy": Action(
            name="free_busy",
            description="Проверить занятость в промежутке времени (free/busy).",
            handler=_free_busy,
            params={
                "time_min":     {"type": "string", "description": "Начало периода ISO 8601"},
                "time_max":     {"type": "string", "description": "Конец периода ISO 8601 (default: +24ч)"},
                "calendar_ids": {"type": "array",  "description": "ID календарей (default: ['primary'])"},
            },
        ),
    },
)
