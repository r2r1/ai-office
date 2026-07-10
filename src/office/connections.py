"""
Подключения к внешним платформам (API-ключи и т.п.) — по тенанту.

ВНИМАНИЕ: значения пока хранятся как есть. Шифрование кредов at-rest — отдельный
пункт SaaS-плана (см. docs/SAAS_ARCHITECTURE.md §4).
"""

import uuid

from src.saas import context as ctx
from src.saas import crypto

_FILE = "connections.json"


def _all() -> list[dict]:
    return ctx.read_json(_FILE, [])


def _decrypted(c: dict) -> dict:
    return {**c, "fields": {k: crypto.decrypt(v) for k, v in (c.get("fields") or {}).items()}}


def _masked(c: dict) -> dict:
    return {**c, "fields": {k: crypto.mask(crypto.decrypt(v)) for k, v in (c.get("fields") or {}).items()}}


def list_all() -> list[dict]:
    """Для UI — значения замаскированы."""
    return [_masked(c) for c in _all()]


def save(conn: dict) -> dict:
    conns = _all()
    cid = conn.get("id")
    raw_fields = conn.get("fields") or {}
    name = (conn.get("name") or "").strip()
    ctype = (conn.get("type") or "api").strip()
    note = (conn.get("note") or "").strip()

    # Обновление по id: значения с маской «•» оставляем как были (не перезаписываем)
    for i, c in enumerate(conns):
        if cid and c["id"] == cid:
            enc_fields = dict(c.get("fields", {}))
            for k, v in raw_fields.items():
                if "•" in str(v):
                    continue  # пользователь не менял это поле
                enc_fields[k] = crypto.encrypt(v)
            conns[i] = {"id": cid, "name": name, "type": ctype, "fields": enc_fields, "note": note}
            ctx.write_json(_FILE, conns)
            return _decrypted(conns[i])

    # Дедуп по имени + значениям (сравниваем в открытом виде)
    new_vals = sorted(str(v) for v in raw_fields.values())
    for c in conns:
        if c["name"].lower() == name.lower():
            existing_plain = sorted(crypto.decrypt(v) for v in c.get("fields", {}).values())
            if existing_plain == new_vals:
                return _decrypted(c)

    item = {"id": uuid.uuid4().hex[:8], "name": name, "type": ctype,
            "fields": {k: crypto.encrypt(v) for k, v in raw_fields.items()}, "note": note}
    conns.append(item)
    ctx.write_json(_FILE, conns)
    return _decrypted(item)


def delete(cid: str) -> bool:
    conns = _all()
    new = [c for c in conns if c["id"] != cid]
    ctx.write_json(_FILE, new)
    return len(new) < len(conns)


def get_by_name(name: str) -> dict | None:
    """Возвращает подключение с РАСШИФРОВАННЫМИ полями (для агентов/интеграций).
    Нечёткий фолбэк (подстрока) — для агента, который называет сервис приблизительно
    (get_connection). Для идентификации КОНКРЕТНОЙ интеграции (registry.credentials_for/
    is_connected) используй get_exact_by_name — нечёткий матч здесь способен задеть
    чужую интеграцию с похожим префиксом имени (реальный риск: "crm" — подстрока
    "crm_bitrix24", "telegram" — подстрока "telegram_personal")."""
    name = (name or "").lower().strip()
    conns = _all()
    for c in conns:
        if c["name"].lower() == name:
            return _decrypted(c)
    for c in conns:
        if name and name in c["name"].lower():
            return _decrypted(c)
    return None


def get_exact_by_name(name: str) -> dict | None:
    """Первый профиль с ТОЧНЫМ совпадением имени — без нечёткого фолбэка."""
    name = (name or "").lower().strip()
    for c in _all():
        if c["name"].lower() == name:
            return _decrypted(c)
    return None


def get_all_by_name(name: str) -> list[dict]:
    """Все подключения (профили) с данным именем, расшифрованные. Один провайдер
    способности может иметь НЕСКОЛЬКО одновременных профилей у тенанта (два
    портала Bitrix24 разных отделов и т.п.) — save() уже допускает несколько
    записей с одинаковым name и разными значениями (дедуп только по name+values),
    просто раньше не было способа прочитать больше первой."""
    name = (name or "").lower().strip()
    return [_decrypted(c) for c in _all() if c["name"].lower() == name]


def list_profiles(name: str) -> list[dict]:
    """Профили провайдера для UI — значения замаскированы."""
    name = (name or "").lower().strip()
    return [_masked(c) for c in _all() if c["name"].lower() == name]


def get_profile(cid: str) -> dict | None:
    """Конкретный профиль по id подключения — когда нужен НЕ первый попавшийся
    (роутер/агент выбирает между несколькими профилями одной способности)."""
    for c in _all():
        if c["id"] == cid:
            return _decrypted(c)
    return None


def names() -> list[str]:
    return [c["name"] for c in _all() if c["name"]]


def load() -> None:
    pass


def reset() -> None:
    ctx.delete_file(_FILE)
