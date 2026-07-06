# Образ песочницы для исполнения кода агентов (execute_code/run_command).
#
# Собрать:  docker build -f docker/sandbox.Dockerfile -t ai-office-sandbox .
# Использует src/office/sandbox.py (SANDBOX_MODE=docker), см. docs/audit-dd-2026-07-06.md §11/§19 п.2.
#
# Непривилегированный пользователь + минимальный набор интерпретаторов
# (python3, node, bash) — ровно то, что execute_code/run_command реально
# запускают (workspace.py: .py/.js/.mjs/.ts/.sh). Никаких сетевых утилит,
# компиляторов или SSH — агенту не нужно ничего, кроме интерпретации
# написанного им же кода в своей рабочей папке.

FROM node:20-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip bash \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --no-create-home --uid 10001 --shell /usr/sbin/nologin sandbox

WORKDIR /workspace
USER sandbox

# Никакого ENTRYPOINT/CMD — sandbox.py передаёт полную команду через
# `docker run ... <image> <cmd...>`.
