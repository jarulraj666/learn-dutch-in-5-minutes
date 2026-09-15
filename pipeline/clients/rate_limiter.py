"""Per-key sliding-window rate limiter.

Each Gemini API key here belongs to its own separate Google Cloud project, so
RPM quota is independent per key — rotating keys is enough to multiply total
throughput, but each individual key must still stay under its own project's
RPM cap (retries on a single key, or several rotator "waves" landing on the
same key within a minute, can otherwise exceed it).
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections import deque

LOGGER = logging.getLogger(__name__)


class RpmLimiter:
    """Blocks callers so that no more than ``max_requests`` calls start within
    any trailing ``window_seconds`` window."""

    def __init__(self, max_requests: int, window_seconds: float = 60.0) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._lock = threading.Lock()
        self._timestamps: deque[float] = deque()

    def acquire(self) -> None:
        """Block until a request slot is free, then reserve it."""
        if self._max_requests <= 0:
            return  # 0/negative disables the limiter entirely
        while True:
            with self._lock:
                now = time.monotonic()
                while self._timestamps and now - self._timestamps[0] >= self._window_seconds:
                    self._timestamps.popleft()
                if len(self._timestamps) < self._max_requests:
                    self._timestamps.append(now)
                    return
                wait_seconds = self._window_seconds - (now - self._timestamps[0])
            LOGGER.info(
                "rpm_limiter: %d/%d requests used in the last %.0fs; waiting %.1fs",
                self._max_requests, self._max_requests, self._window_seconds, wait_seconds,
            )
            time.sleep(max(wait_seconds, 0.05))


_registry_lock = threading.Lock()
_registry: dict[str, RpmLimiter] = {}


def get_rpm_limiter(pool_name: str, key: str, max_requests: int, window_seconds: float = 60.0) -> RpmLimiter:
    """Return the (lazily created) limiter scoped to one specific pool+key pair."""
    cache_key = f"{pool_name}:{hashlib.sha256(key.encode()).hexdigest()[:16]}"
    with _registry_lock:
        limiter = _registry.get(cache_key)
        if limiter is None:
            limiter = RpmLimiter(max_requests, window_seconds)
            _registry[cache_key] = limiter
        else:
            limiter._max_requests = max_requests
        return limiter
