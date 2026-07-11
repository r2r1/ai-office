"""
Discovery — распознавание внешнего ресурса по голой ссылке (BOS: «дать системе
URL — пусть сама поймёт, что это и как с этим работать»).

Стоит на слой НИЖЕ Layer 2 (Integration/Capability): у агента есть ссылка на
GitHub-репозиторий / сайт / API, но нет заранее объявленной интеграции под
именно этот ресурс. Discovery отвечает на вопрос «что это?», не «как этим
пользоваться» — решение, что делать с результатом (использовать существующую
интеграцию, попросить креды, зарегистрировать обобщённый MCP-мост), принимает
вызывающий код (integration_tool_handlers.py), не этот модуль.

Два прохода классификации:
  1. По ФОРМЕ URL (без сети, мгновенно) — GitHub-репозиторий узнаётся по
     домену/пути, дальше сеть не нужна.
  2. Сетевой пробинг (короткий timeout, best-effort) — ищем стандартные
     маркеры: OData $metadata (та же проверка, что erp_1c.check_connection),
     openapi.json/swagger.json, иначе — обычная страница (Content-Type).
     Ошибка сети/таймаут — kind="unreachable", не исключение: агент должен
     получить понятный результат, а не упасть.
"""

import re
from urllib.parse import urlparse

import httpx

_GITHUB_RE = re.compile(r"^https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?(?:$|[?#])")

_PROBE_TIMEOUT = 8.0
_ODATA_PATHS = ("$metadata", "odata/standard.odata/$metadata")
_OPENAPI_PATHS = ("openapi.json", "swagger.json", "v3/api-docs")


def classify_by_shape(url: str) -> dict | None:
    """Классификация по одной ТОЛЬКО форме URL, без сети. None — нечего сказать
    заранее, нужен сетевой пробинг (probe)."""
    m = _GITHUB_RE.match((url or "").strip())
    if m:
        return {"kind": "github_repo", "url": url, "detail": {"owner": m.group(1), "repo": m.group(2)}}
    return None


async def _try_get(client: httpx.AsyncClient, url: str) -> httpx.Response | None:
    try:
        resp = await client.get(url)
        return resp
    except Exception:
        return None


async def probe(url: str) -> dict:
    """Полная классификация: форма URL, затем (если не решилось) сетевые
    маркеры. Всегда возвращает dict с "kind" — деградация, не исключение.

    kind: github_repo | odata | rest_api_openapi | website | unreachable | invalid_url
    """
    url = (url or "").strip()
    if not url:
        return {"kind": "invalid_url", "url": url, "detail": {}}
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return {"kind": "invalid_url", "url": url, "detail": {}}

    by_shape = classify_by_shape(url)
    if by_shape:
        return by_shape

    base = url.rstrip("/")
    async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT, follow_redirects=True) as client:
        for suffix in _ODATA_PATHS:
            resp = await _try_get(client, f"{base}/{suffix}")
            if resp is not None and resp.status_code < 400:
                return {"kind": "odata", "url": url, "detail": {"metadata_path": suffix}}

        for suffix in _OPENAPI_PATHS:
            resp = await _try_get(client, f"{base}/{suffix}")
            if resp is not None and resp.status_code < 400:
                try:
                    spec = resp.json()
                except ValueError:
                    continue
                if isinstance(spec, dict) and ("openapi" in spec or "swagger" in spec or "paths" in spec):
                    title = (spec.get("info") or {}).get("title", "")
                    return {"kind": "rest_api_openapi", "url": url,
                            "detail": {"spec_url": f"{base}/{suffix}", "title": title}}

        resp = await _try_get(client, base)
        if resp is None:
            return {"kind": "unreachable", "url": url, "detail": {}}
        ctype = resp.headers.get("content-type", "")
        if resp.status_code >= 400:
            return {"kind": "unreachable", "url": url, "detail": {"status": resp.status_code}}
        if "html" in ctype or not ctype:
            return {"kind": "website", "url": url, "detail": {"content_type": ctype}}
        return {"kind": "website", "url": url, "detail": {"content_type": ctype}}


# ── Рекомендация по типу ресурса (текст для агента, не выполнение) ──────────
_RECOMMENDATIONS: dict[str, str] = {
    "github_repo": (
        "Это GitHub-репозиторий. Используй существующую интеграцию github "
        "(use_integration с name=\"github\") — если не подключена, запроси у "
        "пользователя через ask_user (OAuth или личный токен в «Доступы»)."
    ),
    "odata": (
        "Это OData-сервис (похоже на 1С). Подключи через существующего провайдера "
        "erp_1c: нужны base_url (эта ссылка), login, password, entity, field_map — "
        "запроси недостающее у пользователя через ask_user."
    ),
    "rest_api_openapi": (
        "Это REST API с OpenAPI/Swagger-спецификацией. Готового провайдера под "
        "именно этот сервис нет — вызови register_external_api с этой ссылкой: "
        "система поднимет обобщённый MCP-мост, который прочитает спецификацию "
        "и сам предложит доступные вызовы."
    ),
    "website": (
        "Обычная веб-страница, не API. Если нужно её содержимое — читай напрямую "
        "(web_search/фактический текст), интеграция тут не нужна."
    ),
    "unreachable": (
        "Ресурс недоступен по сети (таймаут/ошибка/HTTP 4xx-5xx). Если это "
        "локальная система клиента (например 1С без публикации) — спроси "
        "пользователя, опубликована ли она наружу; без этого подключение "
        "невозможно в принципе."
    ),
    "invalid_url": "Это не похоже на валидную ссылку (http/https). Уточни у пользователя.",
}


def recommend(classification: dict) -> str:
    kind = classification.get("kind", "invalid_url")
    return _RECOMMENDATIONS.get(kind, _RECOMMENDATIONS["invalid_url"])
