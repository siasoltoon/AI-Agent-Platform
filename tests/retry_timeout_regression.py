"""Regression coverage for ambiguous Worker outcomes."""

from backend.safe_task_runner import SafeTaskRunner


def test_all_known_ambiguous_worker_outcomes_suppress_retry():
    errors = [
        "Worker request timed out after 300 seconds.",
        "Worker request failed: connection reset",
        "Worker request cancelled: execution cancelled",
        "Worker HTTP 408: Request Timeout",
        "Worker HTTP 429: Too Many Requests",
        "Worker HTTP 500: upstream failure",
        "Worker HTTP 503: service unavailable",
        "Worker returned a non-JSON response.",
        "Worker returned an invalid JSON response object.",
        "RuntimeError: Execution for task_id=x is already in progress; duplicate execution rejected.",
    ]

    assert all(SafeTaskRunner._is_ambiguous_worker_error(error) for error in errors)


def test_definitive_worker_outcomes_are_not_marked_ambiguous():
    errors = [
        "Worker HTTP 400: invalid task",
        "Worker HTTP 401: unauthorized",
        "Worker HTTP 403: forbidden",
        "Worker HTTP 404: not found",
        "Worker HTTP 422: validation failed",
    ]

    assert not any(SafeTaskRunner._is_ambiguous_worker_error(error) for error in errors)
