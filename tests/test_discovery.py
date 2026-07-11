"""
Тесты discovery.py — классификация внешнего ресурса по URL. Сетевой пробинг
проверяется против РЕАЛЬНОГО локального HTTP-сервера (не моки httpx) — тот же
подход, что test_mcp_bridge.py для живого MCP-процесса: маршруты подкладываются
заранее, но сам HTTP-запрос/парсинг ответа реальные.

    python tests/test_discovery.py
"""

import asyncio
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.office import discovery


def _run(coro):
    return asyncio.run(coro)


class _Routes:
    """Конфигурируемый обработчик: path -> (status, content_type, body)."""
    routes: dict = {}

    def __class_getitem__(cls, routes):
        return type("_ConfiguredHandler", (_BaseHandler,), {"ROUTES": routes})


class _BaseHandler(BaseHTTPRequestHandler):
    ROUTES: dict = {}

    def do_GET(self):
        entry = self.ROUTES.get(self.path)
        if entry is None:
            self.send_response(404)
            self.end_headers()
            return
        status, ctype, body = entry
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, fmt, *args):
        pass  # тихо — не засорять вывод тестов


def _serve(routes: dict):
    handler_cls = _Routes[routes]
    server = HTTPServer(("127.0.0.1", 0), handler_cls)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


def _stop(server: HTTPServer):
    server.shutdown()
    server.server_close()


# ── classify_by_shape (без сети) ────────────────────────────────────────────

def test_github_url_classified_by_shape_alone():
    c = discovery.classify_by_shape("https://github.com/anthropics/claude-code")
    assert c is not None
    assert c["kind"] == "github_repo"
    assert c["detail"]["owner"] == "anthropics"
    assert c["detail"]["repo"] == "claude-code"


def test_non_github_url_not_classified_by_shape():
    assert discovery.classify_by_shape("https://example.com/anything") is None


# ── probe() — форма без сети ────────────────────────────────────────────────

def test_probe_invalid_url_returns_invalid_kind():
    c = _run(discovery.probe("не url вообще"))
    assert c["kind"] == "invalid_url"


def test_probe_empty_url_returns_invalid_kind():
    assert _run(discovery.probe(""))["kind"] == "invalid_url"


def test_probe_github_url_shortcuts_network():
    c = _run(discovery.probe("https://github.com/openai/whatever"))
    assert c["kind"] == "github_repo"


# ── probe() — сетевой пробинг против реального локального сервера ──────────

def test_probe_detects_odata_metadata():
    server, port = _serve({
        "/$metadata": (200, "application/xml", "<edmx/>"),
    })
    try:
        c = _run(discovery.probe(f"http://127.0.0.1:{port}"))
        assert c["kind"] == "odata"
    finally:
        _stop(server)


def test_probe_detects_openapi_spec():
    spec = json.dumps({"openapi": "3.0.0", "info": {"title": "Test API"},
                       "paths": {"/foo": {"get": {"summary": "Get foo"}}}})
    server, port = _serve({
        "/openapi.json": (200, "application/json", spec),
    })
    try:
        c = _run(discovery.probe(f"http://127.0.0.1:{port}"))
        assert c["kind"] == "rest_api_openapi"
        assert c["detail"]["title"] == "Test API"
    finally:
        _stop(server)


def test_probe_falls_back_to_website_when_no_api_markers():
    server, port = _serve({
        "/": (200, "text/html", "<html><body>hi</body></html>"),
    })
    try:
        c = _run(discovery.probe(f"http://127.0.0.1:{port}"))
        assert c["kind"] == "website"
    finally:
        _stop(server)


def test_probe_unreachable_host_returns_unreachable():
    # Порт заведомо закрыт (никто не слушает) — реальная сетевая ошибка, не мок.
    c = _run(discovery.probe("http://127.0.0.1:1"))
    assert c["kind"] == "unreachable"


def test_probe_odata_checked_before_openapi_when_both_present():
    """Порядок проверки детерминирован: $metadata раньше openapi.json —
    сервис, отвечающий на оба, классифицируется как odata (см. docstring probe)."""
    spec = json.dumps({"openapi": "3.0.0", "paths": {}})
    server, port = _serve({
        "/$metadata": (200, "application/xml", "<edmx/>"),
        "/openapi.json": (200, "application/json", spec),
    })
    try:
        c = _run(discovery.probe(f"http://127.0.0.1:{port}"))
        assert c["kind"] == "odata"
    finally:
        _stop(server)


# ── recommend() ──────────────────────────────────────────────────────────────

def test_recommend_matches_every_kind():
    for kind in ("github_repo", "odata", "rest_api_openapi", "website", "unreachable", "invalid_url"):
        text = discovery.recommend({"kind": kind})
        assert text and len(text) > 10


def _run_all():
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
    _run_all()
