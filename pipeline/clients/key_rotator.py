"""API key rotation with per-key rate-limit cooldown.

Keys that receive a 429 are excluded from rotation for a configurable duration
(default: 12 hours, or the retry delay returned in the API response if available).
Cooldown state is persisted to a JSON file so it survives process restarts.

Usage::

    from pipeline.clients.key_rotator import KeyRotator

    rotator = KeyRotator(["key1", "key2"], pool_name="gemini")

    for key in rotator.available_keys():
        try:
            result = call_api(key)
            break
        except SomeRateLimitError as exc:
            rotator.mark_rate_limited(key, exc=exc)
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

LOGGER = logging.getLogger(__name__)

_DEFAULT_STATE_FILE = Path(__file__).resolve().parent.parent.parent / "output" / ".key_cooldowns.json"

# Keys whose API-provided retry delay is below this threshold are still
# rate-limited for this minimum instead (to avoid sub-minute micro-bans).
_MIN_COOLDOWN_SECONDS = 60.0


class AllKeysRateLimitedError(RuntimeError):
    """Raised when every key in the pool has actually received a 429 (not merely
    reserved via ``mark_used``). Callers should treat this as fatal and stop,
    rather than waiting for a reservation cooldown to expire."""


def _hash_key(key: str) -> str:
    """Return a short, non-reversible identifier for a raw API key."""
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _parse_retry_delay(exc: Exception | None) -> float | None:
    """Try to extract the retry delay (seconds) from a Gemini rate-limit exception.

    Checks, in order:
    1. ``google.api_core.exceptions.ResourceExhausted`` error details
       (``RetryInfo.retryDelay``).
    2. Regex patterns in the exception message string.

    Returns the delay in seconds, or ``None`` if it cannot be determined.
    """
    if exc is None:
        return None

    # --- Attempt 1: google.api_core structured error details ---
    try:
        from google.api_core.exceptions import ResourceExhausted  # type: ignore[import]

        if isinstance(exc, ResourceExhausted):
            for detail in getattr(exc, "errors", []) or []:
                retry_delay = detail.get("retryDelay") or detail.get("retry_delay")
                if retry_delay:
                    return _parse_duration_str(str(retry_delay))
    except ImportError:
        pass

    # --- Attempt 2: regex the exception message ---
    msg = str(exc)

    # Pattern: "retryDelay":"30s"  or  "retry_delay":"30s"
    m = re.search(r'"retry[_-]?[Dd]elay"\s*:\s*"([^"]+)"', msg, re.IGNORECASE)
    if m:
        parsed = _parse_duration_str(m.group(1))
        if parsed is not None:
            return parsed

    # Pattern: retry_delay { seconds: 60 }  (proto text format)
    m = re.search(r'retry[_\s]?delay\s*\{[^}]*seconds\s*:\s*(\d+)', msg, re.IGNORECASE)
    if m:
        return float(m.group(1))

    # Pattern: bare number of seconds at the end, e.g. "Retry after 60 seconds"
    m = re.search(r'retry\s+after\s+(\d+)\s*s', msg, re.IGNORECASE)
    if m:
        return float(m.group(1))

    return None


def _parse_duration_str(value: str) -> float | None:
    """Parse a duration string like ``'30s'`` or ``'1m30s'`` into seconds."""
    value = value.strip()
    # Simple "Ns" format
    m = re.fullmatch(r'(\d+(?:\.\d+)?)s', value)
    if m:
        return float(m.group(1))
    # "Nm" or "NmMs" format
    m = re.fullmatch(r'(?:(\d+)m)?(?:(\d+(?:\.\d+)?)s)?', value)
    if m and (m.group(1) or m.group(2)):
        minutes = int(m.group(1) or 0)
        secs = float(m.group(2) or 0)
        return minutes * 60 + secs
    return None


class KeyRotator:
    """Round-robin API key rotator with 429-triggered per-key cooldown.

    Args:
        keys: List of raw API key strings.
        pool_name: Identifier for this key pool (used as JSON dict key in state file).
        fallback_cooldown_hours: Cooldown applied when the API response does not
            specify a retry delay. Defaults to 12 hours.
        min_cooldown_seconds: Minimum cooldown applied even when the API response
            provides a shorter retry delay. Prevents sub-minute micro-bans.
        state_file: Path to the JSON file used to persist cooldown state.
    """

    def __init__(
        self,
        keys: list[str],
        pool_name: str,
        fallback_cooldown_hours: float = 12.0,
        min_cooldown_seconds: float = _MIN_COOLDOWN_SECONDS,
        state_file: Path = _DEFAULT_STATE_FILE,
    ) -> None:
        self._keys = list(keys)
        self._pool_name = pool_name
        self._fallback_cooldown_seconds = fallback_cooldown_hours * 3600
        self._min_cooldown_seconds = min_cooldown_seconds
        self._state_file = state_file
        # hash -> expiry datetime (UTC)
        self._cooldowns: dict[str, datetime] = {}
        # hash -> expiry datetime (UTC), populated only by mark_rate_limited (actual 429s),
        # kept separate from _cooldowns so we can tell a real rate-limit apart from a
        # normal-use reservation (mark_used) when deciding whether to give up entirely.
        self._rate_limited: dict[str, datetime] = {}
        self._next_key_index = 0
        # Guards _cooldowns/_next_key_index/state-file I/O for concurrent (threaded) callers.
        self._lock = threading.Lock()
        self._load_state()

    def __len__(self) -> int:
        return len(self._keys)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def available_keys(self) -> Iterator[str]:
        """Yield each key that is not currently rate-limited.

        Raises:
            RuntimeError: If every key in the pool is currently rate-limited.
        """
        with self._lock:
            now = datetime.now(tz=timezone.utc)
            available = [k for k in self._keys if not self._is_rate_limited(k, now)]

            if not available:
                earliest = self._earliest_expiry()
                msg = (
                    f"All {len(self._keys)} key(s) in pool '{self._pool_name}' are rate-limited."
                )
                if earliest:
                    msg += f" Earliest retry at {earliest.isoformat()}."
                raise RuntimeError(msg)

            LOGGER.debug(
                "key_rotator pool=%s available=%d/%d",
                self._pool_name,
                len(available),
                len(self._keys),
            )
        yield from available

    def next_key_cycle(self) -> Iterator[str]:
        """Yield available keys starting with the next key in round-robin order."""
        available = list(self.available_keys())
        with self._lock:
            start = self._next_key_index % len(available)
            self._next_key_index = (start + 1) % len(available)
        yield from available[start:] + available[:start]

    def mark_used(self, key: str, cooldown_seconds: float) -> None:
        """Reserve a key after a successful request for the requested duration."""
        from datetime import timedelta

        expiry = datetime.now(tz=timezone.utc) + timedelta(seconds=cooldown_seconds)
        key_hash = _hash_key(key)
        with self._lock:
            current = self._cooldowns.get(key_hash)
            if current is None or expiry > current:
                self._cooldowns[key_hash] = expiry
                self._save_state()

    def seconds_until_available(self) -> float:
        """Return seconds until at least one key is available, or zero."""
        with self._lock:
            expiry = self._earliest_expiry()
        if expiry is None:
            return 0.0
        return max(0.0, (expiry - datetime.now(tz=timezone.utc)).total_seconds())

    def all_rate_limited(self) -> bool:
        """Return True if every key in the pool currently has an active 429 cooldown.

        Unlike ``available_keys()`` raising, this ignores plain in-use reservations
        (``mark_used``) and only counts keys that actually received a 429.
        """
        now = datetime.now(tz=timezone.utc)
        with self._lock:
            return all(
                (expiry := self._rate_limited.get(_hash_key(k))) is not None and expiry > now
                for k in self._keys
            )

    def mark_rate_limited(self, key: str, exc: Exception | None = None) -> None:
        """Mark *key* as rate-limited.

        The cooldown duration is taken from the API response (via *exc*) when
        available, capped to at least ``min_cooldown_seconds``.  Falls back to
        ``fallback_cooldown_hours`` when the response contains no retry delay.
        """
        api_delay = _parse_retry_delay(exc)

        if api_delay is not None:
            cooldown_seconds = max(api_delay, self._min_cooldown_seconds)
            source = "api_response"
        else:
            cooldown_seconds = self._fallback_cooldown_seconds
            source = "fallback_12h"

        now = datetime.now(tz=timezone.utc)
        from datetime import timedelta
        expiry = now + timedelta(seconds=cooldown_seconds)
        key_hash = _hash_key(key)
        with self._lock:
            self._cooldowns[key_hash] = expiry
            self._rate_limited[key_hash] = expiry
            self._save_state()

        LOGGER.warning(
            "key_rotator pool=%s key_hash=%s rate_limited cooldown=%.0fs source=%s expiry=%s",
            self._pool_name,
            key_hash,
            cooldown_seconds,
            source,
            expiry.isoformat(),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_rate_limited(self, key: str, now: datetime) -> bool:
        expiry = self._cooldowns.get(_hash_key(key))
        return expiry is not None and expiry > now

    def _earliest_expiry(self) -> datetime | None:
        now = datetime.now(tz=timezone.utc)
        active = [exp for exp in self._cooldowns.values() if exp > now]
        return min(active) if active else None

    def _load_state(self) -> None:
        """Load cooldown state from the JSON state file, ignoring expired entries."""
        if not self._state_file.exists():
            return
        try:
            data: dict = json.loads(self._state_file.read_text(encoding="utf-8"))
            pool_data: dict = data.get(self._pool_name, {})
            now = datetime.now(tz=timezone.utc)
            for key_hash, expiry_str in pool_data.items():
                expiry = datetime.fromisoformat(expiry_str)
                if expiry > now:
                    self._cooldowns[key_hash] = expiry
        except Exception as exc:
            LOGGER.warning(
                "key_rotator failed to load state from %s: %s", self._state_file, exc
            )

    def _save_state(self) -> None:
        """Persist current cooldown state to the JSON state file."""
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            # Read existing file so other pools' data is preserved
            existing: dict = {}
            if self._state_file.exists():
                try:
                    existing = json.loads(self._state_file.read_text(encoding="utf-8"))
                except Exception:
                    pass

            now = datetime.now(tz=timezone.utc)
            # Only persist non-expired entries
            existing[self._pool_name] = {
                key_hash: expiry.isoformat()
                for key_hash, expiry in self._cooldowns.items()
                if expiry > now
            }
            self._state_file.write_text(
                json.dumps(existing, indent=2), encoding="utf-8"
            )
        except Exception as exc:
            LOGGER.warning(
                "key_rotator failed to save state to %s: %s", self._state_file, exc
            )
