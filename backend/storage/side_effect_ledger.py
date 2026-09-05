"""Durable side-effect ledger for idempotent agent tool mutations."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


class SideEffectLedger:
    """Persist mutation intents so ambiguous executions are never blindly replayed."""
    STATES = {"running", "committed", "ambiguous", "failed"}

    def __init__(self, path: str | Path = "data/tasks.db") -> None:
        self.path = Path(path); self._lock = threading.RLock(); self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        if self.path.parent != Path("."): self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10); connection.row_factory = sqlite3.Row
        try: yield connection
        finally: connection.close()

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS side_effects (idempotency_key TEXT PRIMARY KEY, task_id TEXT NOT NULL, execution_id TEXT NOT NULL, fencing_token INTEGER NOT NULL, tool_name TEXT NOT NULL, request_hash TEXT NOT NULL, state TEXT NOT NULL, result_json TEXT, error TEXT, started_at REAL NOT NULL, finished_at REAL)""")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_side_effect_task ON side_effects(task_id, started_at)"); connection.execute("CREATE INDEX IF NOT EXISTS idx_side_effect_execution ON side_effects(execution_id)"); connection.commit()

    @staticmethod
    def request_hash(tool_name: str, arguments: Any) -> str:
        payload = json.dumps({"tool": str(tool_name), "arguments": arguments}, ensure_ascii=False, sort_keys=True, default=str); return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get(self, idempotency_key: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as connection:
            row = connection.execute("SELECT * FROM side_effects WHERE idempotency_key=?", (idempotency_key,)).fetchone(); return dict(row) if row else None

    def begin(self, *, idempotency_key: str, task_id: str, execution_id: str, fencing_token: int, tool_name: str, request_hash: str, now: float | None = None) -> dict[str, Any]:
        timestamp = time.time() if now is None else float(now)
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE"); existing = connection.execute("SELECT * FROM side_effects WHERE idempotency_key=?", (idempotency_key,)).fetchone()
            if existing: connection.commit(); return dict(existing)
            connection.execute("INSERT INTO side_effects (idempotency_key,task_id,execution_id,fencing_token,tool_name,request_hash,state,started_at) VALUES (?,?,?,?,?,?,?,?)", (idempotency_key, task_id, execution_id, int(fencing_token), tool_name, request_hash, "running", timestamp)); connection.commit(); return self.get(idempotency_key) or {}

    def commit(self, idempotency_key: str, *, result: Any = None, now: float | None = None) -> bool:
        timestamp = time.time() if now is None else float(now); result_json = json.dumps(result, ensure_ascii=False, default=str) if result is not None else None
        with self._lock, self._connect() as connection:
            cursor = connection.execute("UPDATE side_effects SET state='committed', result_json=?, finished_at=? WHERE idempotency_key=? AND state='running'", (result_json, timestamp, idempotency_key)); connection.commit(); return cursor.rowcount == 1

    def transition(self, idempotency_key: str, state: str, *, error: str | None = None, now: float | None = None) -> bool:
        state = str(state).lower().strip()
        if state not in self.STATES: raise ValueError(f"Unsupported side-effect state: {state}")
        timestamp = time.time() if now is None else float(now)
        with self._lock, self._connect() as connection:
            cursor = connection.execute("UPDATE side_effects SET state=?, error=COALESCE(?,error), finished_at=? WHERE idempotency_key=? AND state='running'", (state, error, timestamp, idempotency_key)); connection.commit(); return cursor.rowcount == 1

    def summary(self, *, limit: int = 500) -> dict[str, Any]:
        """Return bounded authoritative side-effect state for diagnostics/dashboard use."""
        limit = max(1, min(int(limit), 500))
        with self._lock, self._connect() as connection:
            rows = connection.execute("SELECT state, COUNT(*) AS count FROM side_effects GROUP BY state").fetchall()
            recent = connection.execute("SELECT idempotency_key, task_id, execution_id, tool_name, state, started_at, finished_at, error FROM side_effects ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()
        counts = {state: 0 for state in self.STATES}; counts.update({str(row["state"]): int(row["count"]) for row in rows})
        return {"counts": counts, "total": sum(counts.values()), "ambiguous": counts["ambiguous"], "running": counts["running"], "recent": [dict(row) for row in recent]}
