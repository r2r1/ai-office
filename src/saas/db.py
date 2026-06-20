"""
Слой БД для SaaS — на stdlib sqlite3 (без сторонних ORM).

Postgres появится в проде (Phase 6); для dev и старта достаточно SQLite в
`data/app.db`. Все таблицы тенант-ориентированы (кроме `users`/`workspaces`,
которые и задают тенанта).
"""

import sqlite3
import threading
from pathlib import Path

DB_PATH = Path("data/app.db")
_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = _connect()
    return _conn


def execute(sql: str, params: tuple = ()) -> sqlite3.Cursor:
    """Безопасное выполнение с блокировкой (sqlite не любит многопоточную запись)."""
    with _lock:
        cur = conn().execute(sql, params)
        conn().commit()
        return cur


def query_one(sql: str, params: tuple = ()) -> dict | None:
    with _lock:
        row = conn().execute(sql, params).fetchone()
    return dict(row) if row else None


def query_all(sql: str, params: tuple = ()) -> list[dict]:
    with _lock:
        rows = conn().execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def init_db() -> None:
    """Создаёт таблицы, если их нет."""
    execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id          TEXT PRIMARY KEY,
            email       TEXT UNIQUE,
            github_id   INTEGER UNIQUE,
            github_login TEXT,
            name        TEXT,
            avatar      TEXT,
            created_at  REAL
        )
        """
    )
    execute(
        """
        CREATE TABLE IF NOT EXISTS workspaces (
            id            TEXT PRIMARY KEY,
            owner_user_id TEXT NOT NULL,
            name          TEXT,
            plan          TEXT DEFAULT 'free',
            created_at    REAL,
            FOREIGN KEY (owner_user_id) REFERENCES users(id)
        )
        """
    )
