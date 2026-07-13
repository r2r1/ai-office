"""
Провайдер способности «дизайн-референс» — чтение файлов/макетов Figma (REST
API v1, OAuth-токен из figma_oauth.py). Только чтение (scope file_content:read) —
никаких правок макета из агента, только получение структуры/картинок для
дизайнера/разработчика, которые собирают лендинг (см. builtin_skills/
vite_react_site.md — designer читает референс, а не тянет его руками).
"""

import httpx

from src.integrations.base import Action, CredField, Integration
from src.integrations import figma_oauth


def _file_key(params: dict) -> str:
    key = (params.get("file_key") or "").strip()
    if not key:
        raise RuntimeError("Нужен file_key — id файла из ссылки Figma "
                            "(figma.com/file/<file_key>/...).")
    return key


async def _get_file(creds: dict, params: dict) -> str:
    token = await figma_oauth.get_valid_token()
    key = _file_key(params)
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"https://api.figma.com/v1/files/{key}",
                              headers={"Authorization": f"Bearer {token}"})
    if r.status_code != 200:
        raise RuntimeError(f"Figma API: HTTP {r.status_code} — {r.text[:200]}")
    data = r.json()
    name = data.get("name", key)
    pages = [c.get("name", "") for c in (data.get("document") or {}).get("children", [])]
    return f"Файл «{name}»: страницы — {', '.join(pages) or 'нет'}."


async def _export_images(creds: dict, params: dict) -> str:
    token = await figma_oauth.get_valid_token()
    key = _file_key(params)
    node_ids = (params.get("node_ids") or "").strip()
    if not node_ids:
        raise RuntimeError("Нужен node_ids — id узла(ов) макета через запятую "
                            "(видно в ссылке Figma после ?node-id=).")
    fmt = (params.get("format") or "png").strip()
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"https://api.figma.com/v1/images/{key}",
                              params={"ids": node_ids, "format": fmt},
                              headers={"Authorization": f"Bearer {token}"})
    if r.status_code != 200:
        raise RuntimeError(f"Figma API: HTTP {r.status_code} — {r.text[:200]}")
    urls = (r.json().get("images") or {})
    if not urls:
        raise RuntimeError("Figma не вернула изображения для этих node_ids.")
    lines = [f"{nid}: {url}" for nid, url in urls.items() if url]
    return "Ссылки на экспортированные изображения:\n" + "\n".join(lines)


INTEGRATION = Integration(
    name="figma",
    title="Figma",
    category="productivity",
    icon="🎨",
    description="Чтение дизайн-макетов Figma (структура файла, экспорт картинок узлов) — референс для вёрстки.",
    how_to="Нажми «Войти через Figma» и разреши доступ на чтение файлов.",
    oauth_url="/auth/figma/login",
    cred_fields=[CredField(key="access_token", label="Figma access token")],
    department="tech",
    actions={
        "get_file": Action(
            name="get_file",
            description="Получить структуру файла Figma (страницы/фреймы) по file_key.",
            handler=_get_file,
            params={"file_key": {"type": "string", "description": "id файла из ссылки Figma"}},
            required=["file_key"],
            synonyms=["figma", "фигма", "макет", "дизайн-файл"],
        ),
        "export_images": Action(
            name="export_images",
            description="Экспортировать узлы макета Figma как изображения (для референса вёрстки).",
            handler=_export_images,
            params={
                "file_key": {"type": "string", "description": "id файла из ссылки Figma"},
                "node_ids": {"type": "string", "description": "id узла(ов) через запятую"},
                "format": {"type": "string", "description": "png/svg/jpg/pdf (по умолчанию png)"},
            },
            required=["file_key", "node_ids"],
            synonyms=["экспортировать макет", "скачать дизайн", "figma image"],
        ),
    },
)
