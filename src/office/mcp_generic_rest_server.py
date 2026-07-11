"""
Обобщённый REST/OpenAPI MCP-мост — платформенный ШАБЛОН, который discovery.py
предлагает для ресурсов kind="rest_api_openapi" (произвольный REST API со
спецификацией OpenAPI/Swagger), под которые нет заранее написанного провайдера
(в отличие от github/erp_1c — там уже есть свои Integration-модули).

Не «магия»: сервер честно ЧИТАЕТ OpenAPI-спецификацию по указанному URL и
предоставляет ровно два инструмента — обзор эндпоинтов и вызов конкретного.
Никакого написания нового кода на лету — тот же принцип, что у остальных MCP-
серверов: обобщённый механизм, параметризованный конфигурацией, не код агента.

Параметры через переменные окружения (сервер стартует через
mcp_tenant_servers → mcp_bridge._docker_wrap → StdioServerParameters.env,
как и любой другой тенантский MCP-сервер — ОБЯЗАТЕЛЬНО в Docker-песочнице):
  BASE_URL    — базовый URL API (обязателен)
  SPEC_URL    — URL OpenAPI-спеки (по умолчанию BASE_URL/openapi.json)
  AUTH_HEADER — имя заголовка авторизации (напр. "Authorization"), опционально
  AUTH_VALUE  — значение заголовка (напр. "Bearer xxx"), опционально
"""

import os

import httpx
from mcp.server.fastmcp import FastMCP

BASE_URL = (os.environ.get("BASE_URL") or "").rstrip("/")
SPEC_URL = os.environ.get("SPEC_URL") or f"{BASE_URL}/openapi.json"
AUTH_HEADER = os.environ.get("AUTH_HEADER") or ""
AUTH_VALUE = os.environ.get("AUTH_VALUE") or ""

mcp = FastMCP("ai-office-generic-rest")


def parse_openapi_paths(spec: dict) -> list[dict]:
    """Чистая функция (без сети/FastMCP) — извлекает [{method, path, summary,
    operationId}] из тела OpenAPI/Swagger-спецификации. Тестируется отдельно
    от реального HTTP-вызова и от обёртки FastMCP."""
    out = []
    for path, methods in (spec.get("paths") or {}).items():
        if not isinstance(methods, dict):
            continue
        for method, op in methods.items():
            if method.lower() not in ("get", "post", "put", "patch", "delete"):
                continue
            if not isinstance(op, dict):
                continue
            out.append({
                "method": method.upper(),
                "path": path,
                "summary": op.get("summary") or op.get("description") or "",
                "operationId": op.get("operationId") or "",
            })
    return out


def _auth_headers() -> dict:
    return {AUTH_HEADER: AUTH_VALUE} if AUTH_HEADER and AUTH_VALUE else {}


@mcp.tool()
async def list_endpoints() -> str:
    """Читает OpenAPI-спецификацию API и возвращает список доступных
    эндпоинтов (метод, путь, описание) — вызови ПЕРЕД call_endpoint, чтобы
    узнать, что вообще можно вызвать у этого сервиса."""
    if not BASE_URL:
        return "BASE_URL не настроен — сервер сконфигурирован некорректно."
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(SPEC_URL, headers=_auth_headers())
        resp.raise_for_status()
        spec = resp.json()
    except Exception as e:
        return f"Не удалось прочитать спецификацию {SPEC_URL}: {e}"
    endpoints = parse_openapi_paths(spec)
    if not endpoints:
        return f"Спецификация прочитана, но в ней нет ни одного эндпоинта ({SPEC_URL})."
    lines = "\n".join(f"• {e['method']} {e['path']} — {e['summary']}" for e in endpoints)
    return f"Эндпоинты {BASE_URL} ({len(endpoints)}):\n{lines}"


@mcp.tool()
async def call_endpoint(method: str, path: str, params_json: str = "{}") -> str:
    """Вызывает конкретный эндпоинт API. `path` — как в списке list_endpoints
    (например "/orders/{id}" — подставь реальный id сама). `params_json` —
    JSON-строка: для GET/DELETE уходит как query-параметры, для POST/PUT/PATCH
    — как тело запроса."""
    if not BASE_URL:
        return "BASE_URL не настроен — сервер сконфигурирован некорректно."
    import json as _json
    try:
        params = _json.loads(params_json) if params_json else {}
    except ValueError:
        return f"params_json — не валидный JSON: {params_json!r}"
    m = (method or "GET").upper()
    url = f"{BASE_URL}{path if path.startswith('/') else '/' + path}"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            if m in ("GET", "DELETE"):
                resp = await client.request(m, url, params=params, headers=_auth_headers())
            else:
                resp = await client.request(m, url, json=params, headers=_auth_headers())
    except Exception as e:
        return f"Ошибка вызова {m} {url}: {e}"
    body = resp.text[:2000]
    return f"{m} {url} → HTTP {resp.status_code}\n{body}"


if __name__ == "__main__":
    mcp.run()
