import threading
import time
from collections import defaultdict, deque


class FailureRateLimiter:
    """In-memory sliding-window limiter that only counts failed attempts.

    Successful attempts don't consume the budget, so legitimate concurrent
    logins (e.g. everyone signing in at 8am) never get throttled - only
    repeated failures from the same key do.

    Per-process and in-memory: resets on restart, and isn't shared across
    multiple worker processes. That's an acceptable tradeoff for blunting
    naive brute-force/credential-stuffing attempts against a single-instance
    on-prem deployment; it is not a substitute for a distributed limiter at
    real scale.
    """

    def __init__(self, max_failures: int, window_seconds: float):
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self._failures: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque:
        hits = self._failures[key]
        while hits and now - hits[0] > self.window_seconds:
            hits.popleft()
        return hits

    def is_blocked(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            return len(self._prune(key, now)) >= self.max_failures

    def record_failure(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            self._prune(key, now).append(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)

    def retry_after_seconds(self, key: str) -> int:
        now = time.monotonic()
        with self._lock:
            hits = self._prune(key, now)
            if not hits:
                return 0
            return max(0, int(self.window_seconds - (now - hits[0])))


# 10 failed attempts per 15 minutes per client IP.
login_rate_limiter = FailureRateLimiter(max_failures=10, window_seconds=900)
