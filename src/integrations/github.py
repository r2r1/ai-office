"""
Интеграция с GitHub — создание репозитория и пуш кода из рабочей папки тенанта.

Токен берётся из подключения 'GitHub' (сохраняется автоматически при «Войти через
GitHub» с scope repo, либо вводится вручную как PAT). Пуш — через Contents API
(создание/обновление файлов), чего достаточно для проектов офиса.
"""

import base64

import httpx

from src.integrations.base import Action, CredField, Integration
from src.office import workspace

API = "https://api.github.com"


def _token(creds: dict) -> str:
    t = (creds.get("token") or creds.get("key") or creds.get("value") or "").strip()
    if not t:
        raise RuntimeError("Нет токена GitHub. Подключи GitHub в «Доступах».")
    return t


async def _owner(client: httpx.AsyncClient) -> str:
    r = await client.get(f"{API}/user")
    if r.status_code != 200:
        raise RuntimeError(f"GitHub: не удалось получить профиль (HTTP {r.status_code})")
    return r.json()["login"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}


async def _create_repo(creds: dict, params: dict) -> str:
    token = _token(creds)
    name = (params.get("name") or "").strip()
    if not name:
        return "Укажи name репозитория."
    private = params.get("private", True)
    async with httpx.AsyncClient(timeout=25, headers=_headers(token)) as client:
        r = await client.post(f"{API}/user/repos",
                              json={"name": name, "private": bool(private), "auto_init": True})
        if r.status_code == 201:
            return f"Репозиторий создан: {r.json().get('html_url')}"
        if r.status_code == 422:
            owner = await _owner(client)
            return f"Репозиторий уже существует: https://github.com/{owner}/{name}"
        return f"GitHub: ошибка создания репозитория (HTTP {r.status_code}): {r.text[:150]}"


async def _push(creds: dict, params: dict) -> str:
    token = _token(creds)
    repo = (params.get("repo") or "").strip()
    if not repo:
        return "Укажи repo (имя репозитория)."
    message = (params.get("message") or "AI-Office: обновление кода").strip()
    files = workspace.list_files()
    if not files:
        return "Рабочая папка пуста — нечего пушить. Сначала напиши код через write_file."

    pushed, errors = 0, []
    async with httpx.AsyncClient(timeout=30, headers=_headers(token)) as client:
        owner = await _owner(client)
        for f in files:
            path = f["path"]
            content_b64 = base64.b64encode(
                workspace.read_file(path).encode("utf-8")).decode("ascii")
            url = f"{API}/repos/{owner}/{repo}/contents/{path}"
            sha = None
            g = await client.get(url)
            if g.status_code == 200:
                sha = g.json().get("sha")
            body = {"message": message, "content": content_b64}
            if sha:
                body["sha"] = sha
            p = await client.put(url, json=body)
            if p.status_code in (200, 201):
                pushed += 1
            else:
                errors.append(f"{path}: HTTP {p.status_code}")
    res = f"Запушено файлов: {pushed}/{len(files)} → https://github.com/{owner}/{repo}"
    if errors:
        res += "\nОшибки: " + "; ".join(errors[:5])
    return res


INTEGRATION = Integration(
    name="github",
    title="GitHub",
    category="dev",
    icon="🐙",
    description="Создание репозитория и пуш кода проекта из рабочей папки офиса.",
    how_to=(
        "Нажми «Подключить через GitHub» — авторизация по аккаунту (OAuth), "
        "ключ вводить не нужно."
    ),
    oauth_url="/auth/github/login",
    cred_fields=[CredField(key="token", label="GitHub token (scope repo)", secret=True)],
    actions={
        "create_repo": Action(
            name="create_repo",
            description="Создать репозиторий у пользователя (auto-init).",
            handler=_create_repo,
            params={"name": {"type": "string", "description": "Имя репозитория"},
                    "private": {"type": "boolean", "description": "Приватный (по умолчанию да)"}},
            required=["name"],
            synonyms=["репозитор", "github", "гитхаб"],
        ),
        "push": Action(
            name="push",
            description="Запушить все файлы рабочей папки в репозиторий.",
            handler=_push,
            params={"repo": {"type": "string", "description": "Имя репозитория"},
                    "message": {"type": "string", "description": "Сообщение коммита"}},
            required=["repo"],
            synonyms=["github", "гитхаб", "запушить"],
        ),
    },
)
