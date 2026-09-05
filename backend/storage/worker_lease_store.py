"""Durable SQLite worker leases for crash-safe task execution ownership."""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


class WorkerLeaseStore:
    """Coordinate one active execution owner per task using expiring SQLite leases."""

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
        with self._lock:
            connection = self._connect()
            try:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS worker_leases (
                        task_id TEXT PRIMARY KEY,
                        worker_id TEXT NOT NULL,
                        execution_id TEXT NOT NULL,
                        acquired_at REAL NOT NULL,
                        heartbeat_at REAL NOT NULL,
                        lease_until REAL NOT NULL,
                        status TEXT NOT NULL
                    )
                    """
                )
                connection.execute("CREATE INDEX IF NOT EXISTS idx_worker_leases_until ON worker_leases(lease_until)")
                connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_worker_execution_id ON worker_leases(execution_id)")
                connection.commit()
            finally:
                connection.close()

    @staticmethod
    def _decode(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return {
            "task_id": row["task_id"],
            "worker_id": row["worker_id"],
            "execution_id": row["execution_id"],
            "acquired_at": float(row["acquired_at"]),
            "heartbeat_at": float(row["heartbeat_at"]),
            "lease_until": float(row["lease_until"]),
            "status": row["status"],
        }

    def get(self, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            connection = self._connect()
            try:
                return self._decode(connection.execute("SELECT * FROM worker_leases WHERE task_id=?", (task_id,)).fetchone())
            finally:
                connection.close()

    def acquire(self, task_id: str, worker_id: str, execution_id: str, *, ttl_seconds: float = 30.0, now: float | None = None) -> bool:
        ttl = max(1.0, float(ttl_seconds))
        current = time.time() if now is None else float(now)
        with self._lock:
            connection = self._connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute("SELECT * FROM worker_leases WHERE task_id=?", (task_id,)).fetchone()
                if existing is not None and float(existing["lease_until"]) > current and existing["status"] == "active":
                    connection.rollback()
                    return False
                connection.execute("DELETE FROM worker_leases WHERE task_id=?", (task_id,))
                connection.execute(
                    "INSERT INTO worker_leases(task_id,worker_id,execution_id,acquired_at,heartbeat_at,lease_until,status) VALUES(?,?,?,?,?,?,?)",
                    (task_id, worker_id, execution_id, current, current, current + ttl, "active"),
                )
                connection.commit()
                return True
            finally:
                connection.close()

    def renew(self, task_id: str, worker_id: str, execution_id: str, *, ttl_seconds: float = 30.0, now: float | None = None) -> bool:
        ttl = max(1.0, float(ttl_seconds))
        current = time.time() if now is None else float(now)
        with self._lock:
            connection = self._connect()
            try:
                cursor = connection.execute(
                    "UPDATE worker_leases SET heartbeat_at=?, lease_until=? WHERE task_id=? AND worker_id=? AND execution_id=? AND status='active' AND lease_until>=?",
                    (current, current + ttl, task_id, worker_id, execution_id, current),
                )
                connection.commit()
                return cursor.rowcount == 1
            finally:
                connection.close()

    def owns(self, task_id: str, worker_id: str, execution_id: str, *, now: float | None = None) -> bool:
        current = time.time() if now is None else float(now)
        lease = self.get(task_id)
        return bool(
            lease
            and lease["worker_id"] == worker_id
            and lease["execution_id"] == execution_id
            and lease["status"] == "active"
            and lease["lease_until"] >= current
        )

    def release(self, task_id: str, worker_id: str, execution_id: str) -> bool:
        with self._lock:
            connection = self._connect()
            try:
                cursor = connection.execute(
                    "DELETE FROM worker_leases WHERE task_id=? AND worker_id=? AND execution_id=?",
                    (task_id, worker_id, execution_id),
                )
                connection.commit()
                return cursor.rowcount == 1
            finally:
                connection.close()

    def stale(self, *, now: float | None = None, limit: int = 100) -> list[dict[str, Any]]:
        current = time.time() if now is None else float(now)
        limit = max(1, min(int(limit), 500))
        with self._lock:
            connection = self._connect()
            try:
                rows = connection.execute(
                    "SELECT * FROM worker_leases WHERE status='active' AND lease_until<? ORDER BY lease_until ASC LIMIT ?",
                    (current, limit),
                ).fetchall()
                return [self._decode(row) for row in rows if row is not None]
            finally:
                connection.close()

    def purge_stale(self, *, now: float | None = None, limit: int = 100) -> list[dict[str, Any]]:
        stale = self.stale(now=now, limit=limit)
        if not stale:
            return []
        with self._lock:
            connection = self._connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                for lease in stale:
                    connection.execute(
                        "DELETE FROM worker_leases WHERE task_id=? AND execution_id=? AND lease_until<?",
                        (lease["task_id"], lease["execution_id"], time.time() if now is None else float(now)),
                    )
                connection.commit()
            finally:
                connection.close()
        return stale
