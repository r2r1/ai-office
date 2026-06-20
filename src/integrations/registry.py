"""
Каталог доступных интеграций + связка с хранилищем учётных данных.

Здесь регистрируются все поддерживаемые сервисы. Статус «подключено»
определяется наличием сохранённого подключения (connections.py) с нужным
ключом. Чтобы добавить сервис — импортируй его INTEGRATION и добавь в _ALL.
"""

from src.integrations.base import Integration
from src.integrations.telegram import INTEGRATION as _telegram
from src.office import connections

# Все зарегистрированные интеграции (name -> Integration)
_ALL: dict[str, Integration] = {
    _telegram.name: _telegram,
}


def all_integrations() -> list[Integration]:
    return list(_ALL.values())


def get(name: str) -> Integration | None:
    if not name:
        return None
    key = name.lower().strip()
    if key in _ALL:
        return _ALL[key]
    # поиск по title и по частичному совпадению
    for integ in _ALL.values():
        if integ.title.lower() == key or key in integ.name:
            return integ
    return None


def credentials_for(integ: Integration) -> dict:
    """Возвращает поля учётных данных из сохранённого подключения (или {})."""
    conn = connections.get_by_name(integ.name) or connections.get_by_name(integ.title)
    if not conn:
        return {}
    return conn.get("fields", {}) or {}


def is_connected(integ: Integration) -> bool:
    """Подключено, если есть учётка с непустым основным секретом."""
    creds = credentials_for(integ)
    if not creds:
        return False
    primary = integ.cred_fields[0].key if integ.cred_fields else None
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
