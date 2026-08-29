"""Durable SQLite task store with lifecycle enforcement and audit events."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from task_engine.lifecycle import validate_transition


class TaskStore:
    """Persist task lifecycle state and an append-only execution audit trail."""

    def __init__(self, path: str | Path = "data/tasks.db") -> None:
        self.path = Path(path)
        self._lock = threading.RLock()
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Open one SQLite connection and always release its OS file handle."""
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
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, prompt TEXT NOT NULL, model TEXT, status TEXT NOT NULL,
                    created_at REAL NOT NULL, started_at REAL, completed_at REAL,
                    result_json TEXT, error TEXT, metadata_json TEXT NOT NULL
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS task_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
                    created_at REAL NOT NULL, event_type TEXT NOT NULL, status TEXT,
                    detail_json TEXT, FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
                )
            """)
            connection.execute("CREATE INDEX IF NOT EXISTS idx_task_events_task_id ON task_events(task_id, id)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status_created ON tasks(status, created_at)")
            connection.commit()

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"], "prompt": row["prompt"], "model": row["model"], "status": row["status"],
            "created_at": row["created_at"], "started_at": row["started_at"], "completed_at": row["completed_at"],
            "result": json.loads(row["result_json"]) if row["result_json"] else None,
            "error": row["error"], "metadata": json.loads(row["metadata_json"]),
        }

    @staticmethod
    def _decode_event(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"], "task_id": row["task_id"], "created_at": row["created_at"],
            "event_type": row["event_type"], "status": row["status"],
            "detail": json.loads(row["detail_json"]) if row["detail_json"] else None,
        }

    @staticmethod
    def _record_event(connection: sqlite3.Connection, task_id: str, event_type: str, *, status: str | None = None, detail: Any = None) -> None:
        connection.execute(
            "INSERT INTO task_events (task_id, created_at, event_type, status, detail_json) VALUES (?, ?, ?, ?, ?)",
            (task_id, time.time(), event_type, status, json.dumps(detail, ensure_ascii=False, default=str) if detail is not None else None),
        )

    def create(self, task: dict[str, Any]) -> None:
        status = str(task["status"])
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO tasks (id,prompt,model,status,created_at,started_at,completed_at,result_json,error,metadata_json) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (task["id"], task["prompt"], task.get("model"), status, task["created_at"], task.get("started_at"), task.get("completed_at"), json.dumps(task.get("result"), ensure_ascii=False, default=str), task.get("error"), json.dumps(task.get("metadata", {}), ensure_ascii=False, default=str)),
            )
            self._record_event(connection, task["id"], "created", status=status, detail={"prompt_length": len(task["prompt"])})
            connection.commit()

    def get(self, task_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as connection:
            row = connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            return self._decode(row) if row else None

    def list(self, *, limit: int = 100, status: str | None = None) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        with self._lock, self._connect() as connection:
            base = """
                SELECT tasks.* FROM tasks
                LEFT JOIN (SELECT task_id, MAX(id) AS last_event_id FROM task_events GROUP BY task_id)
                events ON events.task_id = tasks.id
            """
            query = base + (" WHERE tasks.status = ?" if status else "") + " ORDER BY COALESCE(events.last_event_id, 0) DESC, tasks.created_at DESC LIMIT ?"
            params = (str(status).strip().lower(), limit) if status else (limit,)
            return [self._decode(row) for row in connection.execute(query, params).fetchall()]

    def events(self, task_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 1000))
        with self._lock, self._connect() as connection:
            rows = connection.execute("SELECT * FROM task_events WHERE task_id = ? ORDER BY id ASC LIMIT ?", (task_id, limit)).fetchall()
            return [self._decode_event(row) for row in rows]

    def update(self, task_id: str, **changes: Any) -> dict[str, Any]:
        allowed = {"status", "started_at", "completed_at", "result", "error", "metadata"}
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError(f"Unsupported task fields: {sorted(unknown)}")
        if not changes:
            current = self.get(task_id)
            if current is None: raise KeyError(task_id)
            return current
        with self._lock, self._connect() as connection:
            row = connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if row is None: raise KeyError(task_id)
            current_status = str(row["status"])
            target_status = str(changes.get("status", current_status)).strip().lower()
            if "status" in changes:
                if current_status == "running" and target_status == "queued":
                    raise ValueError(f"Invalid task lifecycle transition: {current_status} -> {target_status}")
                validate_transition(current_status, target_status)
            assignments, values, detail = [], [], {}
            for key, value in changes.items():
                column = {"result": "result_json", "metadata": "metadata_json"}.get(key, key)
                assignments.append(f"{column} = ?")
                if key in {"result", "metadata"}: value = json.dumps(value, ensure_ascii=False, default=str)
                values.append(str(value) if key == "status" else value)
                if key not in {"result", "metadata"}: detail[key] = value
            values.append(task_id)
            connection.execute(f"UPDATE tasks SET {', '.join(assignments)} WHERE id = ?", values)
            event_type = "status_changed" if "status" in changes and target_status != current_status else "updated"
            self._record_event(connection, task_id, event_type, status=target_status, detail=detail)
            connection.commit()
            return self._decode(connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone())

    def requeue_for_retry(self, task_id: str, *, metadata: dict[str, Any], error: str) -> dict[str, Any]:
        """Atomically return a running task to the queue for a bounded retry."""
        with self._lock, self._connect() as connection:
            row = connection.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if row is None: raise KeyError(task_id)
            if row["status"] != "running":
                return self._decode(connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone())
            connection.execute(
                "UPDATE tasks SET status='queued', started_at=NULL, completed_at=NULL, error=?, metadata_json=? WHERE id=?",
                (error, json.dumps(metadata, ensure_ascii=False, default=str), task_id),
            )
            self._record_event(connection, task_id, "retry_queued", status="queued", detail={"error": error, "retry_count": metadata.get("retry_count", 0)})
            connection.commit()
            return self._decode(connection.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone())

    def retry_failed(self, task_id: str) -> dict[str, Any]:
        """Explicitly requeue a failed task without weakening generic lifecycle updates."""
        with self._lock, self._connect() as connection:
            row = connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if row is None:
                raise KeyError(task_id)
            if str(row["status"]) != "failed":
                raise ValueError(f"Task is not retryable: {row['status']}")

            metadata = json.loads(row["metadata_json"])
            previous_error = row["error"]
            metadata["manual_retry_count"] = int(metadata.get("manual_retry_count", 0)) + 1
            metadata["retry_count"] = 0
            metadata["last_retry_at"] = time.time()
            connection.execute(
                "UPDATE tasks SET status='queued', started_at=NULL, completed_at=NULL, result_json=NULL, error=NULL, metadata_json=? WHERE id=? AND status='failed'",
                (json.dumps(metadata, ensure_ascii=False, default=str), task_id),
            )
            self._record_event(
                connection,
                task_id,
                "manual_retry_queued",
                status="queued",
                detail={"previous_error": previous_error, "manual_retry_count": metadata["manual_retry_count"]},
            )
            connection.commit()
            return self._decode(connection.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone())

    def cancel(self, task_id: str, *, reason: str = "Cancelled by user.") -> dict[str, Any]:
        with self._lock, self._connect() as connection:
            row = connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if row is None: raise KeyError(task_id)
            status = str(row["status"])
            if status in {"completed", "failed", "cancelled"}: return self._decode(row)
            validate_transition(status, "cancelled")
            completed_at = time.time()
            connection.execute("UPDATE tasks SET status='cancelled', completed_at=?, error=? WHERE id=?", (completed_at, reason, task_id))
            self._record_event(connection, task_id, "cancelled", status="cancelled", detail={"reason": reason})
            connection.commit()
            return self._decode(connection.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone())

    def recover_running_tasks(self) -> int:
        with self._lock, self._connect() as connection:
            rows = connection.execute("SELECT id FROM tasks WHERE status='running'").fetchall()
            for row in rows:
                connection.execute("UPDATE tasks SET status='queued', started_at=NULL WHERE id=?", (row["id"],))
                self._record_event(connection, row["id"], "recovered", status="queued", detail={"reason": "controller_restart"})
            connection.commit()
            return len(rows)

    def claim_next_queued(self) -> dict[str, Any] | None:
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM tasks WHERE status='queued' ORDER BY created_at ASC LIMIT 1").fetchone()
            if row is None:
                connection.commit(); return None
            started_at = time.time()
            cursor = connection.execute("UPDATE tasks SET status='running', started_at=? WHERE id=? AND status='queued'", (started_at, row["id"]))
            if cursor.rowcount != 1:
                connection.rollback(); return None
            self._record_event(connection, row["id"], "claimed", status="running", detail={"started_at": started_at})
            connection.commit()
            return self._decode(connection.execute("SELECT * FROM tasks WHERE id=?", (row["id"],)).fetchone())

    def is_cancelled(self, task_id: str) -> bool:
        with self._lock, self._connect() as connection:
            row = connection.execute("SELECT status FROM tasks WHERE id=?", (task_id,)).fetchone()
            return bool(row and row["status"] == "cancelled")

    def ping(self) -> bool:
        with self._lock, self._connect() as connection:
            connection.execute("SELECT 1").fetchone()
        return True
