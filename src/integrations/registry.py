"""
Каталог доступных интеграций + связка с хранилищем учётных данных.

Чтобы добавить сервис — импортируй его INTEGRATION и добавь в _ALL.
OAuth-интеграции (oauth_url != "") считаются подключёнными, если существует
соответствующее подключение в connections (name == integration.name или "google").
"""

from src.integrations.base import Integration
from src.integrations.telegram        import INTEGRATION as _telegram
from src.integrations.website         import INTEGRATION as _website
from src.integrations.github          import INTEGRATION as _github
from src.integrations.google_sheets   import INTEGRATION as _gsheets
from src.integrations.gmail           import INTEGRATION as _gmail
from src.integrations.google_calendar import INTEGRATION as _gcal
from src.office import connections

_ALL: dict[str, Integration] = {
    _website.name:  _website,
    _telegram.name: _telegram,
    _github.name:   _github,
    _gsheets.name:  _gsheets,
    _gmail.name:    _gmail,
    _gcal.name:     _gcal,
}

# Все Google-интеграции держат токен под одним именем "google"
_GOOGLE_SERVICES = {"google_sheets", "gmail", "google_calendar"}


def all_integrations() -> list[Integration]:
    return list(_ALL.values())


def get(name: str) -> Integration | None:
    if not name:
        return None
    key = name.lower().strip()
    if key in _ALL:
        return _ALL[key]
    for integ in _ALL.values():
        if integ.title.lower() == key or key in integ.name:
            return integ
    return None


def credentials_for(integ: Integration) -> dict:
    """Возвращает поля учётных данных из сохранённого подключения (или {})."""
    # Google-интеграции используют общее подключение "google"
    if integ.name in _GOOGLE_SERVICES:
        conn = connections.get_by_name("google")
        return conn.get("fields", {}) if conn else {}
    conn = connections.get_by_name(integ.name) or connections.get_by_name(integ.title)
    return conn.get("fields", {}) if conn else {}


def is_connected(integ: Integration) -> bool:
    """
    Подключено ли? Логика:
    - Интеграции без cred_fields и без oauth_url: всегда True (сайт и т.п.)
    - OAuth-интеграции: True если существует нужное подключение в connections
    - Остальные: True если есть сохранённая учётка с непустым секретом
    """
    # OAuth-интеграции
    if integ.oauth_url:
        if integ.name in _GOOGLE_SERVICES:
            return connections.get_by_name("google") is not None
        return connections.get_by_name(integ.name) is not None

    # Интеграции без кредов (website и т.п.)
    if not integ.cred_fields:
        return True

    # Обычные ключ/токен
    creds = credentials_for(integ)
    if not creds:
        return False
    primary    = integ.cred_fields[0].key if integ.cred_fields else None
    candidates = [primary, "token", "key", "value"]
    return any((creds.get(k) or "").strip() for k in candidates if k)


def catalog_payload() -> list[dict]:
    """Каталог для фронта: описание + статус подключения."""
    out = []
    for integ in _ALL.values():
        item = integ.to_public()
        item["connected"] = is_connected(integ)
        out.append(item)
    return out
