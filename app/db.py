from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from app.config import PROJECT_ROOT

DB_PATH = Path(__import__('os').environ.get('ARC_DB_PATH', str(PROJECT_ROOT / 'arc.sqlite3')))


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript('''
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
