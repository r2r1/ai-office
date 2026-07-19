"""
Multi-user доступ к тенанту (docs/product-portrait-2026-07-19.md §12, §16).

Три раздельно выдаваемых права, не единый пакет «роль» — основатель настраивает
каждое отдельно, кому в каком домене доверять:
  1. Видимость домена (visibility_domains)  — какие Facts/метрики видны.
  2. Финальное решение в домене (decide_domains) — тот же ритуал «офис
     аргументирует → человек решает финально» (§3/§5a), что у основателя, но
     ограниченно своим доменом; без этого права участник может только
     обсуждать/советовать — риск-гейт всё равно эскалирует основателю.
  3. Прямое поручение агентам (can_direct_agents) — право давать директивы
     через intent.capture, не только смотреть.

Выдаёт права ТОЛЬКО основатель (owner_user_id воркспейса) — enforced здесь, не
только на роутере (defense in depth: чужой вызов из кода тоже не пройдёт).
Конфликт между двумя людьми с доступом — эскалация основателю (см. intent.py,
тот же паттерн, что конфликт отделов внутри офиса, портрет §11).

Хранилище: таблица `workspace_members` (src/saas/db.py) — SaaS-уровень
(кто есть кто), не office/*-уровень (что каждый видит по CWM решает сам office
через rights, читая эту таблицу).
"""

import json
import time

from src.saas import db


class NotFounder(Exception):
    """Попытка выдать/отозвать права не от имени основателя воркспейса."""


def _workspace(workspace_id: str) -> dict | None:
    return db.query_one("SELECT * FROM workspaces WHERE id = ?", (workspace_id,))


def is_founder(workspace_id: str, user_id: str) -> bool:
    ws = _workspace(workspace_id)
    return bool(ws) and ws["owner_user_id"] == user_id


def grant(workspace_id: str, target_user_id: str, granted_by: str,
          visibility_domains: list[str] | None = None,
          decide_domains: list[str] | None = None,
          can_direct_agents: bool = False) -> dict:
    """Выдать/обновить права участнику. Только основатель может звать это —
    NotFounder, если `granted_by` не владелец воркспейса (портрет §12: «только
    основатель», без исключений, даже для повторной правки существующих прав)."""
    if not is_founder(workspace_id, granted_by):
        raise NotFounder(f"{granted_by} не основатель воркспейса {workspace_id}")
    if target_user_id == granted_by:
        raise ValueError("Основатель не может выдать права самому себе — он и так видит всё")
    now = time.time()
    existing = db.query_one(
        "SELECT 1 FROM workspace_members WHERE workspace_id=? AND user_id=?",
        (workspace_id, target_user_id))
    payload = (workspace_id, target_user_id, granted_by,
               json.dumps(visibility_domains or [], ensure_ascii=False),
               json.dumps(decide_domains or [], ensure_ascii=False),
               1 if can_direct_agents else 0, now)
    if existing:
        db.execute(
            "UPDATE workspace_members SET granted_by=?, visibility_domains=?, "
            "decide_domains=?, can_direct_agents=?, created_at=? "
            "WHERE workspace_id=? AND user_id=?",
            (granted_by, payload[3], payload[4], payload[5], now, workspace_id, target_user_id))
    else:
        db.execute(
            "INSERT INTO workspace_members (workspace_id, user_id, granted_by, "
            "visibility_domains, decide_domains, can_direct_agents, created_at) "
            "VALUES (?,?,?,?,?,?,?)", payload)
    return rights_for(workspace_id, target_user_id) or {}


def revoke(workspace_id: str, target_user_id: str, revoked_by: str) -> bool:
    if not is_founder(workspace_id, revoked_by):
        raise NotFounder(f"{revoked_by} не основатель воркспейса {workspace_id}")
    cur = db.execute("DELETE FROM workspace_members WHERE workspace_id=? AND user_id=?",
                     (workspace_id, target_user_id))
    return cur.rowcount > 0


def rights_for(workspace_id: str, user_id: str) -> dict | None:
    """Права участника (не основателя — у основателя всегда всё, см. `is_founder`
    в вызывающем коде) или None, если он вообще не участник этого тенанта."""
    row = db.query_one(
        "SELECT * FROM workspace_members WHERE workspace_id=? AND user_id=?",
        (workspace_id, user_id))
    if not row:
        return None
    return {
        "user_id": user_id,
        "granted_by": row["granted_by"],
        "visibility_domains": json.loads(row["visibility_domains"] or "[]"),
        "decide_domains": json.loads(row["decide_domains"] or "[]"),
        "can_direct_agents": bool(row["can_direct_agents"]),
    }


def members_of(workspace_id: str) -> list[dict]:
    rows = db.query_all("SELECT user_id FROM workspace_members WHERE workspace_id=?",
                        (workspace_id,))
    return [rights_for(workspace_id, r["user_id"]) for r in rows]


def can_view(workspace_id: str, user_id: str, domain: str) -> bool:
    """Основатель видит всё всегда. Участник — если домен в его visibility_domains
    ИЛИ ему выдан "*" (весь CWM целиком, портрет §12)."""
    if is_founder(workspace_id, user_id):
        return True
    r = rights_for(workspace_id, user_id)
    if not r:
        return False
    doms = r["visibility_domains"]
    return "*" in doms or domain in doms


def can_decide(workspace_id: str, user_id: str, domain: str) -> bool:
    """Финальное слово в домене — без этого права участник может только
    обсуждать/советовать, риск-гейт эскалирует основателю (§3/§5a)."""
    if is_founder(workspace_id, user_id):
        return True
    r = rights_for(workspace_id, user_id)
    if not r:
        return False
    doms = r["decide_domains"]
    return "*" in doms or domain in doms


def can_direct(workspace_id: str, user_id: str) -> bool:
    if is_founder(workspace_id, user_id):
        return True
    r = rights_for(workspace_id, user_id)
    return bool(r and r["can_direct_agents"])
