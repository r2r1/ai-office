"""
Реальное бронирование слотов — защита от двойной записи БЕЗ внешнего календаря.

Раньше `bot_engine.py` в режиме "booking" был анкетой: собирал имя/телефон и
писал лид, ни разу не проверяя занятость времени (docs/product-capability-gaps.md
п.2). Здесь — собственный локальный реестр записей (`bookings.json`), который
работает уже сегодня без единого внешнего ключа: проверка конфликта слота,
подбор ближайшей свободной альтернативы, рабочие часы из конфига бота.

Когда появится доступ к `google_calendar.py` (реальный Google-календарь клиента),
этот модуль не выбрасывается — он становится источником истины ВНУТРИ платформы
(двойная защита: своя проверка + синхронизация с внешним календарём), а не
заменяется: внешний календарь может быть недоступен/отозван, а бронирование
не должно ломаться целиком из-за этого.
"""

import re
import time
import uuid
from datetime import datetime, timedelta

from src.saas import context as ctx

_FILE = "bookings.json"
_STATUSES = ("booked", "cancelled")

DEFAULT_SLOT_MIN = 60
DEFAULT_HOURS_START = "09:00"
DEFAULT_HOURS_END = "18:00"
DEFAULT_STEP_MIN = 30

# "15.07 14:00", "15.07.2026 14:00", "2026-07-15 14:00" — форматы, которые реально
# печатает человек в чате бота. Год опционален — берём текущий/следующий (см. _parse_dm).
_RE_DM = re.compile(r"^(\d{1,2})[.\-/](\d{1,2})(?:[.\-/](\d{2,4}))?\s+(\d{1,2}):(\d{2})$")
_RE_ISO = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2})$")


def _all() -> list[dict]:
    return ctx.read_json(_FILE, [])


def _save(items: list[dict]) -> None:
    ctx.write_json(_FILE, items)


def parse_datetime(text: str, now: datetime | None = None) -> tuple[str, str] | None:
    """Разбирает свободный ввод пользователя в (date_iso, time_iso) или None,
    если формат не распознан (бот должен переспросить с примером)."""
    text = (text or "").strip()
    now = now or datetime.now()
    m = _RE_ISO.match(text)
    if m:
        y, mo, d, h, mi = (int(x) for x in m.groups())
    else:
        m = _RE_DM.match(text)
        if not m:
            return None
        d, mo, y_raw, h, mi = m.groups()
        d, mo, h, mi = int(d), int(mo), int(h), int(mi)
        if y_raw:
            y = int(y_raw) if len(y_raw) == 4 else 2000 + int(y_raw)
        else:
            y = now.year
            # дата уже прошла в этом году без явного года — считаем, что про следующий
            try:
                if datetime(y, mo, d) < now.replace(hour=0, minute=0, second=0, microsecond=0):
                    y += 1
            except ValueError:
                return None
    try:
        dt = datetime(y, mo, d, h, mi)
    except ValueError:
        return None
    return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")


def _overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return a_start < b_end and b_start < a_end


def _booked_for_date(date_iso: str) -> list[dict]:
    return [b for b in _all() if b.get("date") == date_iso and b.get("status") == "booked"]


def is_free(date_iso: str, time_iso: str, duration_min: int = DEFAULT_SLOT_MIN) -> bool:
    """Свободен ли слот (без учёта рабочих часов — только конфликт с другими записями)."""
    try:
        start = datetime.strptime(f"{date_iso} {time_iso}", "%Y-%m-%d %H:%M")
    except ValueError:
        return False
    end = start + timedelta(minutes=duration_min)
    for b in _booked_for_date(date_iso):
        b_start = datetime.strptime(f"{b['date']} {b['time']}", "%Y-%m-%d %H:%M")
        b_end = b_start + timedelta(minutes=b.get("duration_min", DEFAULT_SLOT_MIN))
        if _overlaps(start, end, b_start, b_end):
            return False
    return True


def _day_slots(date_iso: str, duration_min: int, hours_start: str, hours_end: str,
                step_min: int, now: datetime | None = None) -> list[str]:
    now = now or datetime.now()
    day = datetime.strptime(date_iso, "%Y-%m-%d")
    h1, m1 = (int(x) for x in hours_start.split(":"))
    h2, m2 = (int(x) for x in hours_end.split(":"))
    cur = day.replace(hour=h1, minute=m1)
    end_of_day = day.replace(hour=h2, minute=m2)
    out = []
    while cur + timedelta(minutes=duration_min) <= end_of_day:
        if cur > now and is_free(date_iso, cur.strftime("%H:%M"), duration_min):
            out.append(cur.strftime("%H:%M"))
        cur += timedelta(minutes=step_min)
    return out


def suggest_alternatives(date_iso: str, duration_min: int = DEFAULT_SLOT_MIN, limit: int = 3,
                          hours_start: str = DEFAULT_HOURS_START, hours_end: str = DEFAULT_HOURS_END,
                          step_min: int = DEFAULT_STEP_MIN) -> list[str]:
    """Ближайшие свободные слоты начиная с запрошенного дня (тот же день, потом
    следующие) — то, что бот предложит вместо занятого времени."""
    out: list[str] = []
    day = datetime.strptime(date_iso, "%Y-%m-%d")
    for offset in range(0, 8):  # сама дата + неделя вперёд
        d = (day + timedelta(days=offset)).strftime("%Y-%m-%d")
        for slot in _day_slots(d, duration_min, hours_start, hours_end, step_min):
            out.append(f"{d} {slot}")
            if len(out) >= limit:
                return out
    return out


def book(date_iso: str, time_iso: str, name: str, contact: str, service: str = "",
         duration_min: int = DEFAULT_SLOT_MIN, lead_id: str = "") -> dict | None:
    """Создаёт запись, если слот свободен. None — если конфликт (проверяй is_free
    заранее для дружелюбного ответа пользователю)."""
    if not is_free(date_iso, time_iso, duration_min):
        return None
    items = _all()
    booking = {
        "id": uuid.uuid4().hex[:10], "date": date_iso, "time": time_iso,
        "duration_min": duration_min, "name": (name or "").strip()[:120],
        "contact": (contact or "").strip()[:160], "service": (service or "").strip()[:120],
        "status": "booked", "created_ts": time.time(), "lead_id": lead_id,
    }
    items.append(booking)
    _save(items)
    return booking


def attach_lead(booking_id: str, lead_id: str) -> None:
    """Проставляет lead_id после того, как заявка (leads.py) создана — бронь и
    лид рождаются в двух разных модулях в один вызов _finalize, id лида известен
    только постфактум."""
    items = _all()
    for b in items:
        if b["id"] == booking_id:
            b["lead_id"] = lead_id
            _save(items)
            return


def cancel(booking_id: str) -> dict | None:
    items = _all()
    for b in items:
        if b["id"] == booking_id and b["status"] == "booked":
            b["status"] = "cancelled"
            _save(items)
            return b
    return None


def list_for_date(date_iso: str) -> list[dict]:
    return sorted(_booked_for_date(date_iso), key=lambda b: b["time"])


def upcoming(limit: int = 50) -> list[dict]:
    now = datetime.now()
    items = [b for b in _all() if b.get("status") == "booked"]
    def _dt(b):
        try:
            return datetime.strptime(f"{b['date']} {b['time']}", "%Y-%m-%d %H:%M")
        except ValueError:
            return now
    items = [b for b in items if _dt(b) >= now]
    items.sort(key=_dt)
    return items[:limit]


def reset() -> None:
    ctx.delete_file(_FILE)
