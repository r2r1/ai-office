"""
Хранилище пользователей и рабочих пространств (тенантов).

Workspace = тенант: единица изоляции данных офиса. На старте 1 пользователь = 1
workspace (создаётся автоматически при регистрации/входе).
"""

import os
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
    """Тенант пользователя для входа.

    ⚠️ Приоритет ЧЛЕНСТВА над ВЛАДЕНИЕМ, не наоборот — сделано намеренно после
    находки при живой проверке HTTP-эндпоинтов: `_ensure_workspace` заводит
    СВОЙ воркспейс АВТОМАТИЧЕСКИ при любом входе (github/dev-login), поэтому
    у человека, которого только что пригласили участником (портрет §12), уже
    есть собственный (пустой, никогда не использованный) воркспейс раньше,
    чем он вообще узнал про приглашение — приоритет владения сделал бы фичу
    физически недостижимой обычным логином: человек всегда попадал бы в свой
    пустой офис, а не в тот, куда его позвали. Портретный сценарий — «сотрудника
    добавили в офис работодателя» — встречается чаще, чем «у человека уже
    активный СВОЙ офис, и его ЕЩЁ отдельно пригласили в чужой» (тот случай пока
    не решён — нужен явный переключатель активного воркспейса, которого сегодня
    в продукте нет; это осознанный, задокументированный остаток, не забытый).
    """
    m = db.query_one(
        "SELECT w.* FROM workspaces w "
        "JOIN workspace_members m ON m.workspace_id = w.id "
        "WHERE m.user_id = ? ORDER BY m.created_at LIMIT 1",
        (user_id,),
    )
    if m:
        return m
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
    # Бонусный баланс новому клиенту (BONUS_BALANCE_USD, по умолчанию $5) —
    # до подключения реальной платёжной системы это единственный способ дать
    # попробовать офис без ручной настройки лимита; хранится как обычный
    # бюджетный лимит (costs.py), офис на нём же и остановится, когда бонус
    # закончится (тот же баннер/индикатор в TopBar, что и у платного лимита).
    try:
        from src.saas import context as ctx
        from src.office import costs
        prev = ctx.get_tenant()
        ctx.set_tenant(wid)
        try:
            bonus = float(os.getenv("BONUS_BALANCE_USD", "5"))
            if bonus > 0:
                costs.set_limits(total_usd=bonus, daily_usd=0)
        finally:
            ctx.set_tenant(prev)
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


def delete_workspace(tid: str) -> bool:
    """Полное удаление тенанта — оператор (админка), не сам клиент: строка
    workspaces, все её users (обычно один владелец), и все данные на диске
    (context.wipe(), тот же путь, что у клиентского «сбросить и начать
    заново», просто без необходимости быть залогиненным ИМЕННО этим
    тенантом — вызывающий явно передаёт tid, а не берёт из ContextVar)."""
    ws = db.query_one("SELECT * FROM workspaces WHERE id = ?", (tid,))
    if not ws:
        return False
    db.execute("DELETE FROM workspaces WHERE id = ?", (tid,))
    db.execute("DELETE FROM users WHERE id = ?", (ws["owner_user_id"],))
    from src.saas import context as ctx
    prev = ctx.get_tenant()
    ctx.set_tenant(tid)
    try:
        ctx.wipe()
    finally:
        ctx.set_tenant(prev)
    _invalidate_workspaces_cache()
    return True


def public_user(user: dict) -> dict:
    """Безопасная проекция пользователя для фронта."""
    return {
        "id": user["id"],
        "email": user.get("email"),
        "name": user.get("name"),
        "github_login": user.get("github_login"),
        "avatar": user.get("avatar"),
    }
