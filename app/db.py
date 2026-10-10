from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from app.config import PROJECT_ROOT

_configured_db_path = Path(__import__('os').environ.get('ARC_DB_PATH', str(PROJECT_ROOT / 'arc.sqlite3'))).expanduser()
DB_PATH = (_configured_db_path if _configured_db_path.is_absolute() else PROJECT_ROOT / _configured_db_path).resolve()


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS app_settings (
            setting_key TEXT PRIMARY KEY,
            setting_value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            display_name TEXT NOT NULL DEFAULT '',
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS analyses (
            analysis_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            payload TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS discovery_runs (
            run_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            payload TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_analyses_created_at ON analyses(created_at DESC);
        ''')


def save_analysis(payload: dict[str, Any]) -> None:
    import datetime as dt
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            '''INSERT INTO analyses(analysis_id, created_at, updated_at, payload)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(analysis_id) DO UPDATE SET updated_at=excluded.updated_at, payload=excluded.payload''',
            (payload['analysis_id'], payload.get('created_at', now), now, json.dumps(payload, ensure_ascii=False)),
        )


def load_analysis(analysis_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute('SELECT payload FROM analyses WHERE analysis_id=?', (analysis_id,)).fetchone()
    return json.loads(row['payload']) if row else None


def load_analyses() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute('SELECT payload FROM analyses ORDER BY created_at DESC').fetchall()
    return [json.loads(row['payload']) for row in rows]


def save_discovery(run_id: str, payload: dict[str, Any]) -> None:
    import datetime as dt
    with _connect() as conn:
        conn.execute('INSERT OR REPLACE INTO discovery_runs(run_id, created_at, payload) VALUES (?, ?, ?)',
                     (run_id, dt.datetime.now(dt.timezone.utc).isoformat(), json.dumps(payload, ensure_ascii=False)))


def create_user_record(user_id: str, email: str, display_name: str, password_hash: str) -> None:
    import datetime as dt
    with _connect() as conn:
        conn.execute(
            "INSERT INTO users(user_id, email, display_name, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, email.strip().lower(), display_name.strip(), password_hash, dt.datetime.now(dt.timezone.utc).isoformat()),
        )

def get_user_by_email(email: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT user_id, email, display_name, password_hash, created_at FROM users WHERE email = ? COLLATE NOCASE",
            (email.strip().lower(),),
        ).fetchone()
    return dict(row) if row else None

def get_user_by_id(user_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT user_id, email, display_name, created_at FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
    return dict(row) if row else None


def get_or_create_setting(key: str, generated_value: str) -> str:
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO app_settings(setting_key, setting_value) VALUES (?, ?)",
            (key, generated_value),
        )
        row = conn.execute(
            "SELECT setting_value FROM app_settings WHERE setting_key = ?", (key,)
        ).fetchone()
    if not row:
        raise RuntimeError(f"Could not initialize application setting: {key}")
    return str(row["setting_value"])


def claim_legacy_analyses_for_first_user(user_id: str) -> None:
    """Assign pre-authentication analyses to the first created account on an upgraded MVP database."""
    with _connect() as conn:
        users = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        if users != 1:
            return
        rows = conn.execute("SELECT analysis_id, payload FROM analyses").fetchall()
        for row in rows:
            payload = json.loads(row["payload"])
            if not payload.get("owner_id"):
                payload["owner_id"] = user_id
                conn.execute("UPDATE analyses SET payload = ? WHERE analysis_id = ?",
                             (json.dumps(payload, ensure_ascii=False), row["analysis_id"]))
