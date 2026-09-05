"""SQLite persistence adapter for durable autonomous mission memory."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


class SQLiteMissionStore:
    """Persist complete mission-memory snapshots in the controller's SQLite database."""

    def __init__(self, path: str | Path = "data/tasks.db") -> None:
        self.path = Path(path)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        if self.path.parent != Path("."):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS missions (
                    mission_id TEXT PRIMARY KEY,
                    objective TEXT NOT NULL,
                    status TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    snapshot_json TEXT NOT NULL
                )
                """
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_missions_status_updated ON missions(status, updated_at)")
            connection.commit()

    def save_mission(self, mission_id: str, payload: dict[str, Any]) -> None:
        """Atomically replace the latest complete mission snapshot."""
        if not mission_id or payload.get("mission_id") != mission_id:
            raise ValueError("Mission store identity does not match the snapshot")
        objective = str(payload.get("objective", "")).strip()
        status = str(payload.get("status", "pending")).strip().lower()
        if not objective:
            raise ValueError("Mission objective is required")
        if not status:
            raise ValueError("Mission status is required")
        serialized = json.dumps(payload, ensure_ascii=False, default=str)
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO missions (mission_id, objective, status, updated_at, snapshot_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(mission_id) DO UPDATE SET
                    objective=excluded.objective,
                    status=excluded.status,
                    updated_at=excluded.updated_at,
                    snapshot_json=excluded.snapshot_json
                """,
                (mission_id, objective, status, time.time(), serialized),
            )
            connection.commit()

    def load_mission(self, mission_id: str) -> dict[str, Any] | None:
        """Load the newest durable snapshot for a mission."""
        with self._lock, self._connect() as connection:
            row = connection.execute("SELECT snapshot_json FROM missions WHERE mission_id = ?", (mission_id,)).fetchone()
            if row is None:
                return None
            payload = json.loads(row["snapshot_json"])
            if not isinstance(payload, dict):
                raise ValueError("Persisted mission snapshot must be an object")
            return payload

    def list_missions(self, *, limit: int = 100, status: str | None = None) -> list[dict[str, Any]]:
        """Return bounded mission snapshots for operational inspection."""
        limit = max(1, min(int(limit), 500))
        with self._lock, self._connect() as connection:
            if status is None:
                rows = connection.execute("SELECT snapshot_json FROM missions ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
            else:
                rows = connection.execute(
                    "SELECT snapshot_json FROM missions WHERE status = ? ORDER BY updated_at DESC LIMIT ?",
                    (str(status).strip().lower(), limit),
                ).fetchall()
            return [json.loads(row["snapshot_json"]) for row in rows]
