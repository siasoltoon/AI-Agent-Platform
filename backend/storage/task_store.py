"""Small durable SQLite task store for the controller API."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any


class TaskStore:
    """Persist task lifecycle state without requiring an external database."""

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
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    prompt TEXT NOT NULL,
                    model TEXT,
                    status TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    started_at REAL,
                    completed_at REAL,
                    result_json TEXT,
                    error TEXT,
                    metadata_json TEXT NOT NULL
                )
                """
            )
            connection.commit()

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "prompt": row["prompt"],
            "model": row["model"],
            "status": row["status"],
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
            "result": json.loads(row["result_json"]) if row["result_json"] else None,
            "error": row["error"],
            "metadata": json.loads(row["metadata_json"]),
        }

    def create(self, task: dict[str, Any]) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO tasks
                (id, prompt, model, status, created_at, started_at, completed_at,
                 result_json, error, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task["id"],
                    task["prompt"],
                    task.get("model"),
                    str(task["status"]),
                    task["created_at"],
                    task.get("started_at"),
                    task.get("completed_at"),
                    json.dumps(task.get("result"), ensure_ascii=False, default=str),
                    task.get("error"),
                    json.dumps(task.get("metadata", {}), ensure_ascii=False, default=str),
                ),
            )
            connection.commit()

    def get(self, task_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as connection:
            row = connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            return self._decode(row) if row else None

    def list(self) -> list[dict[str, Any]]:
        with self._lock, self._connect() as connection:
            rows = connection.execute("SELECT * FROM tasks ORDER BY created_at DESC").fetchall()
            return [self._decode(row) for row in rows]

    def update(self, task_id: str, **changes: Any) -> dict[str, Any]:
        allowed = {
            "status",
            "started_at",
            "completed_at",
            "result",
            "error",
            "metadata",
        }
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError(f"Unsupported task fields: {sorted(unknown)}")
        if not changes:
            current = self.get(task_id)
            if current is None:
                raise KeyError(task_id)
            return current

        assignments: list[str] = []
        values: list[Any] = []
        for key, value in changes.items():
            column = {"result": "result_json", "metadata": "metadata_json"}.get(key, key)
            assignments.append(f"{column} = ?")
            if key in {"result", "metadata"}:
                value = json.dumps(value, ensure_ascii=False, default=str)
            values.append(str(value) if key == "status" else value)
        values.append(task_id)

        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                f"UPDATE tasks SET {', '.join(assignments)} WHERE id = ?",
                values,
            )
            if cursor.rowcount != 1:
                raise KeyError(task_id)
            connection.commit()
            row = connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            return self._decode(row)

    def ping(self) -> bool:
        with self._lock, self._connect() as connection:
            connection.execute("SELECT 1").fetchone()
        return True
