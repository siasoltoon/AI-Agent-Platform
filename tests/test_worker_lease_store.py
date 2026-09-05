from backend.storage.worker_lease_store import WorkerLeaseStore


def test_active_lease_blocks_duplicate_execution(tmp_path):
    store = WorkerLeaseStore(tmp_path / "tasks.db")

    assert store.acquire("task-1", "worker-a", "exec-a", ttl_seconds=30, now=100.0) is True
    assert store.acquire("task-1", "worker-b", "exec-b", ttl_seconds=30, now=110.0) is False
    assert store.owns("task-1", "worker-a", "exec-a", now=120.0) is True


def test_expired_lease_can_be_reacquired_with_new_execution_identity(tmp_path):
    store = WorkerLeaseStore(tmp_path / "tasks.db")

    assert store.acquire("task-1", "worker-a", "exec-a", ttl_seconds=5, now=100.0) is True
    assert store.acquire("task-1", "worker-b", "exec-b", ttl_seconds=5, now=106.0) is True
    assert store.owns("task-1", "worker-a", "exec-a", now=106.0) is False
    assert store.owns("task-1", "worker-b", "exec-b", now=106.0) is True


def test_heartbeat_renews_only_exact_owner(tmp_path):
    store = WorkerLeaseStore(tmp_path / "tasks.db")
    store.acquire("task-1", "worker-a", "exec-a", ttl_seconds=10, now=100.0)

    assert store.renew("task-1", "worker-b", "exec-a", ttl_seconds=10, now=105.0) is False
    assert store.renew("task-1", "worker-a", "exec-b", ttl_seconds=10, now=105.0) is False
    assert store.renew("task-1", "worker-a", "exec-a", ttl_seconds=10, now=105.0) is True
    assert store.owns("task-1", "worker-a", "exec-a", now=114.0) is True


def test_stale_scan_and_purge_are_bounded_and_identity_safe(tmp_path):
    store = WorkerLeaseStore(tmp_path / "tasks.db")
    store.acquire("old", "worker-a", "exec-old", ttl_seconds=5, now=100.0)
    store.acquire("live", "worker-b", "exec-live", ttl_seconds=30, now=100.0)

    stale = store.stale(now=110.0, limit=10)
    assert [lease["task_id"] for lease in stale] == ["old"]

    purged = store.purge_stale(now=110.0, limit=10)
    assert [lease["execution_id"] for lease in purged] == ["exec-old"]
    assert store.get("old") is None
    assert store.get("live") is not None


def test_release_requires_exact_worker_and_execution_identity(tmp_path):
    store = WorkerLeaseStore(tmp_path / "tasks.db")
    store.acquire("task-1", "worker-a", "exec-a", ttl_seconds=30, now=100.0)

    assert store.release("task-1", "worker-b", "exec-a") is False
    assert store.release("task-1", "worker-a", "exec-b") is False
    assert store.release("task-1", "worker-a", "exec-a") is True
    assert store.get("task-1") is None
