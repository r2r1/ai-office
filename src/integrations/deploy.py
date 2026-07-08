"""
Интеграция «Деплой» — TEST-режим без реального хостинг-провайдера.

Раньше код после `github.py::push` был тупиком для нетехнического клиента:
GitHub умеет создать репозиторий и запушить файлы, а дальше — ничего, поднять
сайт/бота должен был сам клиент (docs/product-capability-gaps.md п.3). Vercel/
Netlify/Render ключа сегодня нет, но форма ответа реального провайдера
известна заранее (id деплоя, публичный URL, статус) — здесь она воспроизведена
в виде рабочей песочницы, которая ведёт свой реестр (`deployments.json`) и
возвращает агенту и пользователю осязаемый результат («вот ссылка») уже
сейчас. Когда появится реальный ключ Vercel/Netlify — меняется только тело
`_create_deployment` (реальный HTTP-вызов вместо генерации mock-записи),
контракт действия (что видит агент) остаётся прежним.
"""

import time
import uuid

from src.integrations.base import Action, Integration
from src.office import workspace
from src.saas import context as ctx

_FILE = "deployments.json"


def _all() -> list[dict]:
    return ctx.read_json(_FILE, [])


def _save(items: list[dict]) -> None:
    ctx.write_json(_FILE, items)


def get(deployment_id: str) -> dict | None:
    for d in _all():
        if d["id"] == deployment_id:
            return d
    return None


def list_deployments() -> list[dict]:
    return sorted(_all(), key=lambda d: d.get("created_ts", 0), reverse=True)


def _find_index(directory: str) -> str | None:
    """Тот же приём авто-детекта, что в website.py::_publish_site — агент
    часто не помнит точную папку, index.html ищем в типичных местах."""
    directory = (directory or "").strip().strip("/")
    idx_rel = f"{directory}/index.html" if directory else "index.html"
    idx = workspace.resolve(idx_rel)
    if idx is not None and idx.is_file():
        return idx_rel
    for cand in ("site", "", "public", "dist", "www", "build"):
        cand_rel = f"{cand}/index.html" if cand else "index.html"
        ci = workspace.resolve(cand_rel)
        if ci is not None and ci.is_file():
            return cand_rel
    for f in workspace.list_files():
        if f["path"].endswith("index.html"):
            return f["path"]
    return None


async def _create_deployment(creds: dict, params: dict) -> str:
    directory = (params.get("directory") or "").strip().strip("/")
    title = (params.get("title") or "проект").strip()
    idx_rel = _find_index(directory)
    if idx_rel is None:
        return ("Не найден index.html — сначала напиши сайт/бота через write_file. "
                "Деплой возможен только для готовых статических файлов (html/css/js); "
                "серверный код (Python-бот и т.п.) деплою так не подлежит — его "
                "нужно запускать отдельно (см. workspace/run_command).")

    tid = ctx.get_tenant()
    did = f"dpl_{uuid.uuid4().hex[:10]}"
    slug = "".join(c if c.isalnum() else "-" for c in title.lower())[:40].strip("-") or "site"
    url = f"https://{slug}-{did[-6:]}.mock-preview.dev"
    items = _all()
    items.append({
        "id": did, "directory": directory, "title": title, "url": url,
        "status": "ready", "provider": "test", "created_ts": time.time(),
        "index_path": idx_rel,
    })
    _save(items)
    return (f"Тестовый деплой создан: {url} (id: {did}, файл входа: {idx_rel}). "
            f"⚠️ Реальный хостинг-провайдер (Vercel/Netlify/Render) не подключён — "
            f"это песочница: ссылка не резолвится в интернете по-настоящему. "
            f"Публичный рабочий адрес для клиента прямо сейчас — публикация через "
            f"скилл сайта (use_capability('опубликовать сайт')), она хостится реально. "
            f"Эту ссылку используй только чтобы показать, куда встанет деплой после "
            f"подключения настоящего провайдера в «Доступы».")


async def _get_deployment_status(creds: dict, params: dict) -> str:
    did = (params.get("deployment_id") or "").strip()
    d = get(did)
    if d is None:
        return f"Деплой {did} не найден."
    return f"Деплой {did}: {d['status']}, {d['url']} (провайдер: {d['provider']})."


INTEGRATION = Integration(
    name="deploy",
    title="Деплой",
    category="dev",
    icon="🚀",
    description="TEST-режим деплоя статических файлов: заводит запись с публичным "
                "адресом до подключения реального хостинг-провайдера.",
    how_to="Сейчас работает в тестовом режиме без ключей — ссылка не резолвится "
           "по-настоящему. Чтобы деплоить реально, подключи Vercel/Netlify/Render здесь, "
           "когда появится ключ (раздел будет обновлён под конкретного провайдера).",
    cred_fields=[],  # test-режим доступен всегда; реальный провайдер добавится сюда позже
    actions={
        "create_deployment": Action(
            name="create_deployment",
            description="Задеплоить статические файлы из папки workspace (тестовый режим, "
                        "пока нет реального хостинг-провайдера).",
            handler=_create_deployment,
            params={
                "directory": {"type": "string", "description": "Папка с index.html в рабочей директории"},
                "title": {"type": "string", "description": "Название проекта (влияет на адрес)"},
            },
            required=[],
            synonyms=["деплой", "задеплой", "vercel", "netlify", "render", "хостинг", "поднять сайт"],
        ),
        "get_deployment_status": Action(
            name="get_deployment_status",
            description="Проверить статус созданного деплоя по id.",
            handler=_get_deployment_status,
            params={"deployment_id": {"type": "string", "description": "id деплоя"}},
            required=["deployment_id"],
        ),
    },
)
