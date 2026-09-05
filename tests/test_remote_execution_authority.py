from __future__ import annotations

from backend.services.remote_execution_authority import RemoteExecutionAuthority


class FakeResponse:
    ok = True
    reason = "OK"
    status_code = 200

    def __init__(self, payload):
        self.payload = payload
        self.text = ""

    def json(self):
        return self.payload


def test_remote_authority_fence_check_and_side_effect_flow(monkeypatch):
    calls = []
    records = {}

    def fake_post(url, *, json, headers, timeout):
        calls.append((url, json, headers, timeout))
        if url.endswith("/fence"):
            return FakeResponse({"current": True})
        if url.endswith("/side-effects/begin"):
            record = {
                "idempotency_key": json["idempotency_key"],
                "task_id": json["task_id"],
                "execution_id": json["execution_id"],
                "fencing_token": json["fencing_token"],
                "request_hash": json["request_hash"],
                "state": "running",
            }
            records[record["idempotency_key"]] = record
            return FakeResponse({"record": record})
        if url.endswith("/side-effects/get"):
            return FakeResponse({"record": records.get(json["idempotency_key"])})
        if url.endswith("/side-effects/commit"):
            return FakeResponse({"committed": True})
        if url.endswith("/side-effects/transition"):
            return FakeResponse({"transitioned": True})
        raise AssertionError(url)

    monkeypatch.setattr("backend.services.remote_execution_authority.requests.post", fake_post)
    authority = RemoteExecutionAuthority("http://controller:8000", token="secret", timeout=7)

    assert authority.fence_check("task-1", "exec-1", 3) is True
    request_hash = authority.request_hash("write_file", {"path": "a.txt", "content": "hello"})
    record = authority.begin(idempotency_key="key-1", task_id="task-1", execution_id="exec-1", fencing_token=3, tool_name="write_file", request_hash=request_hash)
    assert record["state"] == "running"
    assert authority.commit("key-1", result={"ok": True}, execution_id="exec-1", fencing_token=3) is True
    assert authority.transition("key-1", "ambiguous", error="worker lost", execution_id="exec-1", fencing_token=3) is True
    assert all(call[2] == {"Authorization": "Bearer secret"} for call in calls)
