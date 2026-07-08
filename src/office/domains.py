"""
Кастомные домены для опубликованных сайтов (docs/product-capability-gaps.md п.5).

Раньше сайт клиента жил ТОЛЬКО на `/site/{tenant}/{slug}` под доменом
платформы — малый бизнес не мог показать `моякомпания.рф`. DNS-провайдера
(регистрация домена, автоматический CNAME) у нас нет и не нужен: указать
DNS на платформу — ответственность владельца домена, ЗДЕСЬ нужна только
серверная часть — сопоставление входящего Host-заголовка с тенантом/сайтом,
что не требует ни одного внешнего ключа и работает уже сегодня.

Хранилище — ГЛОБАЛЬНЫЙ файл `data/domains.json` (не per-tenant, в отличие от
остальной платформы): домен → (tenant, slug) должен резолвиться ДО того, как
мы знаем тенанта (см. server.py::custom_domain_middleware, читает Host первым
делом, раньше tenant_middleware). Один домен закреплён ровно за одним тенантом
(register() отказывает, если домен уже занят другим тенантом) — иначе тенант A
мог бы угнать трафик тенанта B, один раз узнав его домен.
"""

import json
import re
import time
from pathlib import Path

_FILE = Path("data/domains.json")
_DOMAIN_RE = re.compile(r"^[a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?)+$")


def _normalize(domain: str) -> str:
    return (domain or "").strip().lower().rstrip(".")


def _load() -> list[dict]:
    if not _FILE.is_file():
        return []
    try:
        return json.loads(_FILE.read_text(encoding="utf-8")).get("items", [])
    except (json.JSONDecodeError, OSError):
        return []


def _save(items: list[dict]) -> None:
    _FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"items": items}, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_FILE)


def is_valid_domain(domain: str) -> bool:
    d = _normalize(domain)
    return bool(d) and bool(_DOMAIN_RE.match(d)) and "." in d


def register(domain: str, tenant: str, slug: str) -> dict:
    """Привязывает домен к сайту тенанта. Бросает ValueError, если формат домена
    невалиден или домен уже занят ДРУГИМ тенантом (защита от угона трафика)."""
    d = _normalize(domain)
    if not is_valid_domain(d):
        return {"error": f"«{domain}» не похож на домен (пример: mycompany.ru)"}
    items = _load()
    for item in items:
        if item["domain"] == d and item["tenant"] != tenant:
            return {"error": f"Домен {d} уже привязан к другому рабочему пространству"}
    items = [i for i in items if not (i["domain"] == d and i["tenant"] == tenant)]
    entry = {"domain": d, "tenant": tenant, "slug": slug, "created_ts": time.time(), "verified": False}
    items.append(entry)
    _save(items)
    return entry


def resolve(host: str) -> dict | None:
    """host → {"tenant", "slug"} если это зарегистрированный кастомный домен."""
    d = _normalize(host)
    if not d:
        return None
    for item in _load():
        if item["domain"] == d:
            return item
    return None


def for_tenant(tenant: str) -> list[dict]:
    return [i for i in _load() if i["tenant"] == tenant]


def unregister(domain: str, tenant: str) -> bool:
    """Отвязывает домен — только если он принадлежит ЭТОМУ тенанту."""
    d = _normalize(domain)
    items = _load()
    kept = [i for i in items if not (i["domain"] == d and i["tenant"] == tenant)]
    if len(kept) == len(items):
        return False
    _save(kept)
    return True


def mark_verified(domain: str) -> None:
    """Отмечает, что DNS реально указывает на платформу (сегодня выставляется
    вручную/по факту первого успешного запроса с этим Host — полноценная
    DNS-проверка (dig/резолв A-записи) не входит в объём без внешнего DNS-API)."""
    d = _normalize(domain)
    items = _load()
    for item in items:
        if item["domain"] == d:
            item["verified"] = True
    _save(items)
