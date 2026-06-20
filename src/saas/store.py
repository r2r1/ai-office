"""
Хранилище пользователей и рабочих пространств (тенантов).

Workspace = тенант: единица изоляции данных офиса. На старте 1 пользователь = 1
workspace (создаётся автоматически при регистрации/входе).
"""

import time
import uuid

from src.saas import db


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
    return db.query_all("SELECT * FROM workspaces ORDER BY created_at")


def public_user(user: dict) -> dict:
    """Безопасная проекция пользователя для фронта."""
    return {
        "id": user["id"],
        "email": user.get("email"),
        "name": user.get("name"),
        "github_login": user.get("github_login"),
        "avatar": user.get("avatar"),
    }
