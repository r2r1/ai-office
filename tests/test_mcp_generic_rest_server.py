"""
Тесты mcp_generic_rest_server.py::parse_openapi_paths — чистая функция
(без сети/FastMCP), извлекающая эндпоинты из тела OpenAPI-спецификации.

    python tests/test_mcp_generic_rest_server.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.office import mcp_generic_rest_server as grs


def test_parses_get_and_post_endpoints():
    spec = {
        "paths": {
            "/orders": {
                "get": {"summary": "List orders", "operationId": "listOrders"},
                "post": {"summary": "Create order"},
            },
            "/orders/{id}": {
                "delete": {"summary": "Delete order"},
            },
        }
    }
    eps = grs.parse_openapi_paths(spec)
    assert len(eps) == 3
    methods = {(e["method"], e["path"]) for e in eps}
    assert ("GET", "/orders") in methods
    assert ("POST", "/orders") in methods
    assert ("DELETE", "/orders/{id}") in methods
    get_order = next(e for e in eps if e["method"] == "GET")
    assert get_order["summary"] == "List orders"
    assert get_order["operationId"] == "listOrders"


def test_ignores_non_http_method_keys():
    """OpenAPI позволяет служебные ключи вроде "parameters" на уровне path —
    не должны попасть в список эндпоинтов как "метод"."""
    spec = {"paths": {"/x": {"parameters": [{"name": "id"}], "get": {"summary": "ok"}}}}
    eps = grs.parse_openapi_paths(spec)
    assert len(eps) == 1
    assert eps[0]["method"] == "GET"


def test_empty_spec_returns_empty_list():
    assert grs.parse_openapi_paths({}) == []
    assert grs.parse_openapi_paths({"paths": {}}) == []


def test_summary_falls_back_to_description():
    spec = {"paths": {"/x": {"get": {"description": "fallback text"}}}}
    eps = grs.parse_openapi_paths(spec)
    assert eps[0]["summary"] == "fallback text"


def _run():
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ✓ {name}")
            passed += 1
    print(f"ВСЕ {passed} ТЕСТОВ ПРОШЛИ")


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    _run()
