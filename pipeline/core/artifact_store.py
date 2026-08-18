"""Single source of truth for artifact persistence.

Design contract
---------------
- The DB (publish_jobs.artifact_json) is the ONLY store.
- No disk artifact files are written or read.
- ``load(topic_id)`` reads the DB blob and returns the artifact dict.
- ``save(topic_id, artifact)`` writes the artifact dict to the DB.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from pipeline.core.db import get_connection

LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _db_row(topic_id: str) -> dict | None:
    sql = """
        SELECT pj.id AS job_id, pj.artifact_json
        FROM publish_jobs pj
        JOIN canonical_scripts cs ON cs.id = pj.canonical_script_id
        WHERE cs.topic_id = ?
        ORDER BY pj.id DESC
        LIMIT 1
    """
    with get_connection() as conn:
        row = conn.execute(sql, [topic_id]).fetchone()
    return dict(row) if row else None


def _write_db(job_id: int, artifact: dict) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE publish_jobs SET artifact_json = ? WHERE id = ?",
            [json.dumps(artifact, ensure_ascii=False), job_id],
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load(topic_id: str) -> dict[str, Any]:
    """Load artifact from DB. Raises KeyError if not found."""
    row = _db_row(topic_id)
    if row is None:
        raise KeyError(f"No publish_job found for topic_id={topic_id!r}")
    if not row["artifact_json"]:
        raise KeyError(f"No artifact_json in publish_job for topic_id={topic_id!r}")
    artifact: dict = json.loads(row["artifact_json"])
    LOGGER.debug("artifact_store.loaded topic=%s", topic_id)
    return artifact


def save(topic_id: str, artifact: dict[str, Any]) -> None:
    """Save artifact to DB. Raises KeyError if no publish_job exists."""
    row = _db_row(topic_id)
    if row is None:
        raise KeyError(f"No publish_job found for topic_id={topic_id!r}")
    _write_db(row["job_id"], artifact)
    LOGGER.debug("artifact_store.saved topic=%s", topic_id)
