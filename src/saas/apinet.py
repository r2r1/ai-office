"""
Клиент управления аккаунтом apinet.cloud (new-api) через Access Token.

Назначение: на КАЖДЫЙ профиль (тенант) выдавать СВОЙ API-ключ с лимитом квоты.
Это даёт изоляцию расхода и страхует от пережога баланса одним тенантом.

Включается ОПЦИОНАЛЬНО через .env:
    APINET_ACCESS_TOKEN=<Access Token из Настройки ЛК>
    APINET_USER_ID=<User ID из Настройки ЛК>
    APINET_BASE=https://apinet.cloud            # по умолчанию
    APINET_TENANT_QUOTA=500000                  # лимит на ключ тенанта (квота, 500000 = $1)

Если токен/ID не заданы — провижининг пропускается, тенант использует общий
ключ оператора из LLM_API_KEY (текущее поведение, ничего не ломается).

Единицы: new-api считает в «квоте», где 500000 квоты = $1.
"""

import json
import os
import urllib.request
import urllib.error

_BASE = os.getenv("APINET_BASE", "https://apinet.cloud").rstrip("/")
_ACCESS_TOKEN = os.getenv("APINET_ACCESS_TOKEN", "").strip()
_USER_ID = os.getenv("APINET_USER_ID", "").strip()
_TENANT_QUOTA = int(os.getenv("APINET_TENANT_QUOTA", "500000"))  # $1 по умолчанию

QUOTA_PER_USD = 500000


def is_configured() -> bool:
    """Заданы ли креды управления аккаунтом (иначе провижининг пропускается)."""
    return bool(_ACCESS_TOKEN and _USER_ID)


def _request(method: str, path: str, body: dict | None = None) -> dict:
    """Запрос к API управления аккаунтом (авторизация Access Token + User ID)."""
    url = f"{_BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": _ACCESS_TOKEN,
        "New-Api-User": _USER_ID,
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"success": False, "message": f"HTTP {e.code}: {e.read().decode()[:200]}"}
    except Exception as e:
        return {"success": False, "message": str(e)[:200]}


def balance() -> dict:
    """Профиль и баланс аккаунта оператора: {quota, used_quota, usd, ...}."""
    r = _request("GET", "/api/user/self")
    d = r.get("data") or {}
    return {
        "username": d.get("username"),
        "quota": d.get("quota", 0),
        "used_quota": d.get("used_quota", 0),
        "usd": round((d.get("quota", 0) or 0) / QUOTA_PER_USD, 4),
        "used_usd": round((d.get("used_quota", 0) or 0) / QUOTA_PER_USD, 4),
        "group": d.get("group"),
    }


def list_tokens(size: int = 50) -> list[dict]:
    r = _request("GET", f"/api/token/?p=0&size={size}")
    data = r.get("data")
    if isinstance(data, dict):
        data = data.get("records") or data.get("data") or []
    return data or []


def find_token(name: str) -> dict | None:
    for t in list_tokens(size=100):
        if t.get("name") == name:
            return t
    return None


def create_token(name: str, quota: int | None = None, unlimited: bool = False) -> dict:
    """
    Создаёт API-ключ с лимитом квоты. Возвращает {ok, key, id, message}.
    key — готовый к использованию ключ вида 'sk-...'.
    """
    if not is_configured():
        return {"ok": False, "message": "APINET_ACCESS_TOKEN/USER_ID не заданы"}
    # Не плодим дубли: если ключ с таким именем уже есть — переиспользуем
    existing = find_token(name)
    if existing:
        return {"ok": True, "key": _full_key(existing.get("key", "")),
                "id": existing.get("id"), "message": "уже существует", "reused": True}

    body = {
        "name": name,
        "remain_quota": _TENANT_QUOTA if quota is None else quota,
        "expired_time": -1,            # бессрочно
        "unlimited_quota": bool(unlimited),
    }
    r = _request("POST", "/api/token/", body)
    if not r.get("success", False):
        return {"ok": False, "message": r.get("message", "ошибка создания")}
    # new-api обычно не возвращает сам ключ в ответе на создание — дочитываем из списка
    created = find_token(name)
    if not created:
        return {"ok": False, "message": "ключ создан, но не найден в списке"}
    return {"ok": True, "key": _full_key(created.get("key", "")),
            "id": created.get("id"), "message": "создан"}


def disable_token(token_id: int) -> dict:
    return _request("PUT", "/api/token/", {"id": token_id, "status": 2})


def delete_token(token_id: int) -> dict:
    return _request("DELETE", f"/api/token/{token_id}")


def _full_key(raw: str) -> str:
    """new-api хранит ключ без префикса — для вызовов нужен 'sk-<key>'."""
    raw = (raw or "").strip()
    if not raw:
        return ""
    return raw if raw.startswith("sk-") else f"sk-{raw}"
