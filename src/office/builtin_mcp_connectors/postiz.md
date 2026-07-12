---
id: postiz
title: Postiz (кроспостинг в соцсети)
keywords: постинг, кроспостинг, соцсети, публикация, карусель, контент-план, instagram, telegram, vk, автопостинг
command: npx
args: -y, mcp-remote, {POSTIZ_URL}/mcp/{POSTIZ_API_KEY}
needs: POSTIZ_URL=адрес self-hosted Postiz БЕЗ слэша на конце, например http://host:4007; POSTIZ_API_KEY=ключ из Settings → Developers → Public API в интерфейсе Postiz
allow_network: true
---
Postiz — открытый (AGPL-3.0), self-hosted кроспостинг в 30+ соцсетей (Instagram,
Telegram, X, Bluesky, Mastodon, Reddit, Discord и др.). Бесплатен навсегда при
self-host (в отличие от большинства SaaS-кроспостеров с триалом 7-14 дней).

Собственный MCP-сервер Postiz — это УДАЛЁННЫЙ HTTP/SSE-эндпоинт на инстансе
клиента (`/mcp/<api-key>`), не локальный npx-пакет. Наша обвязка тенантских
MCP-серверов (mcp_bridge.py) говорит только stdio — поэтому command/args здесь
поднимают `mcp-remote` (реальный npm-пакет, мост stdio↔SSE), который проксирует
локальный stdio-процесс на удалённый эндпоинт клиента.

Как получить значения needs:
1. Клиент разворачивает Postiz self-host (docker-compose из
   github.com/gitroomhq/postiz-docker-compose), порт по умолчанию 4007.
2. В интерфейсе Postiz: Settings → Developers → Public API → сгенерировать ключ.
3. POSTIZ_URL — адрес, на котором клиент реально поднял Postiz (спроси через
   ask_user, не выдумывай localhost, если сервер не у нас).

После подключения инструменты появятся с префиксом mcp__tenant_<id>__ — 9
инструментов Postiz (посты, площадки, расписание и т.п.), без необходимости
самому собирать HTTP-запросы к REST API Postiz.
