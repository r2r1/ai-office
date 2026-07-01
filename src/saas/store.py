"""
Хранилище пользователей и рабочих пространств (тенантов).

Workspace = тенант: единица изоляции данных офиса. На старте 1 пользователь = 1
workspace (создаётся автоматически при регистрации/входе).
"""

import time
import uuid

from src.saas import db

# Короткий TTL-кеш списка воркспейсов: office/loop.py's менеджер опрашивает
# all_workspaces() каждые MANAGER_POLL=5с для КАЖДОГО тенанта — полный скан
# таблицы на каждый тик не нужен, список меняется редко (только при регистрации).
# Инвалидируется явно в _ensure_workspace при создании нового воркспейса —
# TTL здесь просто подстраховка (например прямые вставки в БД в обход store.py).
_WORKSPACES_CACHE_TTL = 5.0
_workspaces_cache: tuple[float, list[dict]] | None = None


def _invalidate_workspaces_cache() -> None:
    global _workspaces_cache
    _workspaces_cache = None


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def get_user(user_id: str) -> dict | None:
    return db.query_one("SELECT * FROM users WHERE id = ?", (user_id,))


def workspace_for_user(user_id: str) -> dict | None:
    return db.query_one(
        "SELECT * FROM workspaces WHERE owner_user_id = ? ORDER BY created_at LIMIT 1",
        (user_id,),
    )


def _ensure_workspace(user: dict) -> dict:
    ws = workspace_for_user(user["id"])
    if ws:
        return ws
    wid = _new_id("ws")
    name = (user.get("name") or user.get("github_login") or user.get("email") or "Мой офис")
    db.execute(
        "INSERT INTO workspaces (id, owner_user_id, name, plan, created_at) VALUES (?,?,?,?,?)",
        (wid, user["id"], f"{name}", "free", time.time()),
    )
    # Свой apinet-ключ на профиль (если заданы APINET_ACCESS_TOKEN/USER_ID).
    # Не валим создание workspace, если apinet недоступен.
    try:
        from src.office import llm_settings
        llm_settings.provision_tenant_key(wid, name=f"office-{wid}")
    except Exception:
        pass
    _invalidate_workspaces_cache()
    return workspace_for_user(user["id"])


def get_or_create_by_github(profile: dict) -> dict:
    """profile: {id, login, name, email, avatar_url} из GitHub API."""
    gh_id = profile.get("id")
    existing = db.query_one("SELECT * FROM users WHERE github_id = ?", (gh_id,))
    if not existing and profile.get("email"):
        existing = db.query_one("SELECT * FROM users WHERE email = ?", (profile["email"],))
    if existing:
        # обновим профиль (логин/имя/аватар могли поменяться)
        db.execute(
            "UPDATE users SET github_id=?, github_login=?, name=?, avatar=? WHERE id=?",
            (gh_id, profile.get("login"), profile.get("name"), profile.get("avatar_url"), existing["id"]),
        )
        user = get_user(existing["id"])
    else:
        uid = _new_id("u")
        db.execute(
            "INSERT INTO users (id, email, github_id, github_login, name, avatar, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (uid, profile.get("email"), gh_id, profile.get("login"),
             profile.get("name"), profile.get("avatar_url"), time.time()),
        )
        user = get_user(uid)
    _ensure_workspace(user)
    return user


def get_or_create_dev_user(email: str) -> dict:
    """Локальный вход без GitHub (для разработки/демо)."""
    email = (email or "dev@local").strip().lower()
    existing = db.query_one("SELECT * FROM users WHERE email = ?", (email,))
    if existing:
        _ensure_workspace(existing)
        return existing
    uid = _new_id("u")
    db.execute(
        "INSERT INTO users (id, email, name, created_at) VALUES (?,?,?,?)",
        (uid, email, email.split("@")[0], time.time()),
    )
    user = get_user(uid)
    _ensure_workspace(user)
    return user


def all_workspaces() -> list[dict]:
    global _workspaces_cache
    now = time.time()
    if _workspaces_cache is not None and now - _workspaces_cache[0] < _WORKSPACES_CACHE_TTL:
        return _workspaces_cache[1]
    rows = db.query_all("SELECT * FROM workspaces ORDER BY created_at")
    _workspaces_cache = (now, rows)
    return rows


def public_user(user: dict) -> dict:
    """Безопасная проекция пользователя для фронта."""
    return {
        "id": user["id"],
        "email": user.get("email"),
        "name": user.get("name"),
        "github_login": user.get("github_login"),
        "avatar": user.get("avatar"),
    }
