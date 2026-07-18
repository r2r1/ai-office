"""
Интеграция «Внешние данные (HTTP)» — единственный официальный способ агента
получить данные с публичного URL (курс валюты, погода, любой открытый API),
когда для сервиса нет отдельной готовой интеграции.

Реальная причина существования: execute_code/run_command выполняются в
песочнице БЕЗ сети (--network none, src/office/exec_sandbox.py) — осознанное
решение безопасности, агент не может дёргать интернет ИЗНУТРИ исполняемого
кода. Но агенту (не коду, который он пишет) сеть иногда честно нужна — эта
интеграция даёт её на ГЛАВНОМ процессе (как website.py/discovery.py), не
трогая изоляцию песочницы. Найденный живой баг (2026-07-18, инициатива
«Автообновление курса USD/RUB»): без такого пути агент 40+ циклов подряд
переписывал скрипт (requests → urllib), каждый раз падая на одной и той же
сетевой ошибке — задача была структурно нерешаема написанием кода.

Без кредов (как website.py) — публичный GET, ключи не нужны. Базовая защита
от SSRF: только http/https, резолвим хост и отклоняем приватные/loopback/
link-local адреса (иначе агент мог бы дёрнуть 127.0.0.1:8001/supervisor/...
или облачный metadata-эндпоинт с правами процесса сервера).
"""

import ipaddress
import socket
from urllib.parse import urlparse

import httpx

from src.integrations.base import Action, Integration

_TIMEOUT = 10.0
_MAX_BODY = 200_000  # символов — не раздувать контекст агента одним ответом


def _is_safe_host(hostname: str) -> bool:
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            return False
    return True


async def _get(creds: dict, params: dict) -> str:
    url = (params.get("url") or "").strip()
    if not url:
        return "Нужен url."
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return "Некорректный url — нужен полный http(s)-адрес."
    if not _is_safe_host(parsed.hostname):
        return ("Этот адрес недоступен для запроса (внутренний/приватный хост). "
                "Разрешены только обычные публичные интернет-адреса.")
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "ai-office-agent/1.0"})
    except httpx.TimeoutException:
        return f"Таймаут запроса к {url} ({_TIMEOUT:g}с) — источник не ответил."
    except httpx.RequestError as e:
        return f"Ошибка сети при запросе {url}: {e}"

    body = resp.text[:_MAX_BODY]
    truncated = " (обрезано)" if len(resp.text) > _MAX_BODY else ""
    return f"HTTP {resp.status_code} от {url}{truncated}:\n{body}"


INTEGRATION = Integration(
    name="http_fetch",
    title="Внешние данные (HTTP)",
    category="dev",
    icon="🌐",
    description="GET-запрос к публичному URL (курс валюты, погода, открытый API) — когда "
                "для сервиса нет отдельной интеграции. Ключи не нужны.",
    how_to="Учётные данные не нужны — просто передай url. Работает только для публичных адресов.",
    cred_fields=[],  # без кредов — всегда доступна
    actions={
        "get": Action(
            name="get",
            description="Сделать GET-запрос к публичному URL и вернуть тело ответа (обрезано до "
                        f"{_MAX_BODY} символов). Единственный способ получить внешние данные по "
                        "сети — execute_code/run_command в песочнице сети не имеют.",
            handler=_get,
            params={"url": {"type": "string", "description": "Полный http(s)-адрес"}},
            required=["url"],
            synonyms=["курс валют", "внешний api", "скачать данные", "получить данные по url",
                      "http-запрос", "веб-запрос", "публичный api", "погода"],
        ),
    },
)
