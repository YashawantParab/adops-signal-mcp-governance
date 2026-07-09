from __future__ import annotations

import time
from collections import defaultdict, deque

_hits: dict[str, deque[float]] = defaultdict(deque)


def check_rate_limit(key: str, limit: int, window_seconds: float = 60.0) -> bool:
    """Best-effort in-process rate limit.

    Not a distributed limiter (resets on restart, per-instance only). It exists
    solely to bound OpenAI cost and database noise from the public,
    unauthenticated demo-session endpoint and the diagnoses it can trigger -
    not as a general-purpose abuse defense for authenticated traffic.
    """
    now = time.monotonic()
    bucket = _hits[key]
    while bucket and now - bucket[0] > window_seconds:
        bucket.popleft()
    if len(bucket) >= limit:
        return False
    bucket.append(now)
    return True
