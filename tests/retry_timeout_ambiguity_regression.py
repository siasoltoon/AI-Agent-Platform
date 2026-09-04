from backend.safe_task_runner import SafeTaskRunner


def test_known_ambiguous_worker_errors_suppress_retry():
    errors = [
        "Worker request timed out after 10 seconds",
        "Worker request failed: connection reset",
        "Worker request cancelled: client cancellation",
        "Worker HTTP 408: Request Timeout",
        "Worker HTTP 429: Too Many Requests",
        "Worker HTTP 500: Internal Server Error",
        "Worker HTTP 503: Service Unavailable",
        "Worker returned a non-JSON response.",
        "Worker returned an invalid JSON response object.",
        "Execution for task_id=x is already in progress; duplicate execution rejected.",
    ]
    assert all(SafeTaskRunner._is_ambiguous_worker_error(error) for error in errors)


def test_definitive_worker_errors_remain_retryable_by_default_policy():
    errors = [
        "Worker HTTP 400: Bad Request",
        "Worker HTTP 401: Unauthorized",
        "Worker HTTP 403: Forbidden",
        "Worker HTTP 404: Not Found",
        "Worker HTTP 422: Unprocessable Content",
    ]
    assert all(not SafeTaskRunner._is_ambiguous_worker_error(error) for error in errors)
