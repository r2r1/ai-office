# Образ ПРИЛОЖЕНИЯ (сервер + фронт) — не путать с docker/sandbox.Dockerfile
# (та песочница исполняет КОД АГЕНТОВ, эта — сам AI-Office). Закрывает issue #8
# (docs/architecture-improvements.md) — до этого в репозитории не было ни
# строчки деплой-инфраструктуры для самого приложения.
#
# Собрать:  docker build -t ai-office .
# Запустить (проще — через docker-compose.yml, который добавляет reverse-proxy
# с автоматическим TLS и volume для data/):
#   docker compose up -d
#
# Два стейджа: сначала Node собирает фронт (webapp/ → static/webapp/, тот же
# `vite build`, что и в CLAUDE.md §2), затем Python-рантайм копирует только
# результат сборки — в финальном образе нет ни node, ни исходников webapp/,
# ни node_modules (~300MB экономии, и не нужен Node в проде).

# ---- Стейдж 1: сборка фронта ----
FROM node:20-slim AS webapp-build
WORKDIR /webapp
COPY webapp/package.json webapp/package-lock.json* ./
RUN npm ci
COPY webapp/ ./
RUN npm run build
# vite.config.ts: outDir "../static/webapp" (относительно webapp/) → /static/webapp

# ---- Стейдж 2: рантайм приложения ----
FROM python:3.13-slim

# Непривилегированный пользователь — то же решение, что уже принято для
# sandbox.Dockerfile (не root в контейнере, даже без сетевой экспозиции наружу).
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin office

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# Заменяем static/webapp исходников (если случайно закоммичен устаревший) на
# СВЕЖУЮ сборку из стейджа 1 — источник правды один, не два рассинхронизирующихся.
COPY --from=webapp-build /static/webapp ./static/webapp

# data/ — per-tenant состояние (sqlite, workspace агентов) — ВСЕГДА volume в
# docker-compose.yml, никогда не должно жить только в слое образа (потеря при
# пересборке). Здесь просто гарантируем, что каталог существует и им владеет
# непривилегированный пользователь ДО первого монтирования volume.
RUN mkdir -p data && chown -R office:office /app

USER office

ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# ⚠️ БЕЗ --reload: reload-логика в scripts/run.py существует ТОЛЬКО для
# локальной разработки (следит за исходниками, игнорирует data/) — в проде
# автоперезагрузка на изменение файлов не нужна и не должна быть включена.
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
