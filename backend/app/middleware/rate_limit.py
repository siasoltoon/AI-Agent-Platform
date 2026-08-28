"""Rate limiting foundation for backend requests."""

from collections import defaultdict
from time import time

_requests = defaultdict(list)


def check_rate_limit(key: str, limit: int = 60, window: int = 60) -> bool:
    now = time()
    _requests[key] = [t for t in _requests[key] if now - t < window]
    if len(_requests[key]) >= limit:
        return False
    _requests[key].append(now)
    return True
