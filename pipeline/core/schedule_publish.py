from __future__ import annotations

from datetime import datetime, timezone

# Sentinel value stored in publish_jobs.scheduled_at when an episode has not
# yet been manually scheduled.  publish_pending.py filters on scheduled_at <= now,
# so this date is never picked up automatically.
UNSCHEDULED_SENTINEL = "9999-12-31T00:00:00+00:00"


def next_publish_slot() -> datetime:
    """Return the 'unscheduled' sentinel datetime.

    Automatic cadence scheduling has been disabled.  Episodes are scheduled
    manually via the webapp (Episodes → Schedule button).
    """
    return datetime.fromisoformat(UNSCHEDULED_SENTINEL)
