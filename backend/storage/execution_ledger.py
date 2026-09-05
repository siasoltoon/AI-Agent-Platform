"""Durable execution-attempt ledger for crash-safe retries and fencing."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


class ExecutionLedger:
    """Persist execution attempts and monotonically increasing fencing tokens."""

    STATES = {"created", "running", "interrupted", "ambiguous", "committed", "superseded", "failed", "cancelled"}

    def __init__(self, path: str | Path = "data/tasks.db") -> None:
        self.path = Path(path)
        self._lock = threading.RLock()
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        if self.path.parent != Path("."):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS execution_attempts (
                    execution_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    attempt_no INTEGER NOT NULL,
                    worker_id TEXT,
                    state TEXT NOT NULL,
                    fencing_token INTEGER NOT NULL,
                    parent_execution_id TEXT,
                    idempotency_key TEXT,
                    started_at REAL,
                    finished_at REAL,
                    result_hash TEXT,
                    result_json TEXT,
                    error TEXT
                )
            """)
            connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_execution_task_attempt ON execution_attempts(task_id, attempt_no)")
            connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_execution_task_idempotency ON execution_attempts(task_id, idempotency_key) WHERE idempotency_key IS NOT NULL")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_execution_task_state ON execution_attempts(task_id, state)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_execution_task_fence ON execution_attempts(task_id, fencing_token)")
            # Existing installations created before result persistence receive the column without destructive migration.
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(execution_attempts)").fetchall()}
            if "result_json" not in columns:
                connection.execute("ALTER TABLE execution_attempts ADD COLUMN result_json TEXT")
            connection.commit()

    @staticmethod
    def _decode(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return {key: row[key] for key in row.keys()}

    def get(self, execution_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as connection:
            return self._decode(connection.execute("SELECT * FROM execution_attempts WHERE execution_id=?", (execution_id,)).fetchone())

    def current(self, task_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as connection:
            return self._decode(connection.execute(
                "SELECT * FROM execution_attempts WHERE task_id=? ORDER BY fencing_token DESC LIMIT 1", (task_id,)
            ).fetchone())

    def begin(
        self,
        task_id: str,
        worker_id: str,
        *,
        execution_id: str | None = None,
        parent_execution_id: str | None = None,
        idempotency_key: str | None = None,
        now: float | None = None,
    ) -> dict[str, Any]:
        """Create exactly one new attempt, superseding any previous live attempt."""
        timestamp = time.time() if now is None else float(now)
        execution_id = str(execution_id or uuid.uuid4())
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if idempotency_key:
                existing = connection.execute(
                    "SELECT * FROM execution_attempts WHERE task_id=? AND idempotency_key=?",
                    (task_id, idempotency_key),
                ).fetchone()
                if existing is not None:
                    connection.commit()
                    return self._decode(existing) or {}
            current = connection.execute(
                "SELECT * FROM execution_attempts WHERE task_id=? ORDER BY fencing_token DESC LIMIT 1", (task_id,)
            ).fetchone()
            next_attempt = int(current["attempt_no"]) + 1 if current else 1
            next_token = int(current["fencing_token"]) + 1 if current else 1
            if current and current["state"] in {"created", "running"}:
                connection.execute(
                    "UPDATE execution_attempts SET state='superseded', finished_at=?, error=? WHERE execution_id=?",
                    (timestamp, "Superseded by a newer execution attempt.", current["execution_id"]),
                )
            try:
                connection.execute(
                    "INSERT INTO execution_attempts (execution_id,task_id,attempt_no,worker_id,state,fencing_token,parent_execution_id,idempotency_key,started_at) VALUES (?,?,?,?,?,?,?,?,?)",
                    (execution_id, task_id, next_attempt, str(worker_id), "running", next_token, parent_execution_id, idempotency_key, timestamp),
                )
            except sqlite3.IntegrityError:
                if idempotency_key:
                    existing = connection.execute(
                        "SELECT * FROM execution_attempts WHERE task_id=? AND idempotency_key=?",
                        (task_id, idempotency_key),
                    ).fetchone()
                    if existing is not None:
                        connection.commit()
                        return self._decode(existing) or {}
                raise
            connection.commit()
            return self.get(execution_id) or {}

    def transition(self, execution_id: str, state: str, *, error: str | None = None, result_hash: str | None = None, now: float | None = None) -> bool:
        state = str(state).strip().lower()
        if state not in self.STATES:
            raise ValueError(f"Unsupported execution state: {state}")
        timestamp = time.time() if now is None else float(now)
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "UPDATE execution_attempts SET state=?, finished_at=?, error=COALESCE(?, error), result_hash=COALESCE(?, result_hash) WHERE execution_id=? AND state NOT IN ('committed','superseded','cancelled')",
                (state, timestamp if state in {"interrupted", "ambiguous", "committed", "superseded", "failed", "cancelled"} else None, error, result_hash, execution_id),
            )
            connection.commit()
            return cursor.rowcount == 1

    def fence_check(self, task_id: str, execution_id: str, fencing_token: int) -> bool:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT state, fencing_token FROM execution_attempts WHERE task_id=? AND execution_id=?",
                (task_id, execution_id),
            ).fetchone()
            return bool(row and int(row["fencing_token"]) == int(fencing_token) and row["state"] == "running")

    def commit_if_current(self, task_id: str, execution_id: str, fencing_token: int, *, result_hash: str | None = None, result: Any = None, now: float | None = None) -> bool:
        """Commit only the current fenced attempt; stale workers cannot commit."""
        timestamp = time.time() if now is None else float(now)
        result_json = json.dumps(result, ensure_ascii=False, default=str) if result is not None else None
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "UPDATE execution_attempts SET state='committed', finished_at=?, result_hash=?, result_json=? WHERE task_id=? AND execution_id=? AND fencing_token=? AND state='running' AND fencing_token=(SELECT MAX(fencing_token) FROM execution_attempts WHERE task_id=?)",
                (timestamp, result_hash, result_json, task_id, execution_id, int(fencing_token), task_id),
            )
            connection.commit()
            return cursor.rowcount == 1

    def commit_task_if_current(
        self,
        task_id: str,
        execution_id: str,
        fencing_token: int,
        *,
        result: Any,
        metadata: dict[str, Any],
        now: float | None = None,
    ) -> bool:
        """Atomically commit the ledger attempt and TaskStore completion under its fence."""
        timestamp = time.time() if now is None else float(now)
        result_json = json.dumps(result, ensure_ascii=False, default=str)
        metadata_json = json.dumps(metadata, ensure_ascii=False, default=str)
        result_hash = hashlib.sha256(result_json.encode("utf-8")).hexdigest()
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            task = connection.execute("SELECT status FROM tasks WHERE id=?", (task_id,)).fetchone()
            if task is None or task["status"] != "running":
                connection.rollback()
                return False
            ledger_cursor = connection.execute(
                "UPDATE execution_attempts SET state='committed', finished_at=?, result_hash=?, result_json=? WHERE task_id=? AND execution_id=? AND fencing_token=? AND state='running' AND fencing_token=(SELECT MAX(fencing_token) FROM execution_attempts WHERE task_id=?)",
                (timestamp, result_hash, result_json, task_id, execution_id, int(fencing_token), task_id),
            )
            if ledger_cursor.rowcount != 1:
                connection.rollback()
                return False
            task_cursor = connection.execute(
                "UPDATE tasks SET status='completed', completed_at=?, result_json=?, error=NULL, metadata_json=? WHERE id=? AND status='running'",
                (timestamp, result_json, metadata_json, task_id),
            )
            if task_cursor.rowcount != 1:
                connection.rollback()
                return False
            connection.execute(
                "INSERT INTO task_events (task_id, created_at, event_type, status, detail_json) VALUES (?, ?, ?, ?, ?)",
                (task_id, timestamp, "status_changed", "completed", json.dumps({"execution_id": execution_id, "fencing_token": int(fencing_token)}, ensure_ascii=False)),
            )
            connection.commit()
            return True

    def list_attempts(self, task_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM execution_attempts WHERE task_id=? ORDER BY attempt_no DESC LIMIT ?", (task_id, limit)
            ).fetchall()
            return [self._decode(row) or {} for row in rows]
