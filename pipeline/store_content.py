from __future__ import annotations

import json
from datetime import datetime, timezone

from pipeline.db import get_connection
from pipeline.utils import content_fingerprint, now_utc_iso


def store_canonical_script(
    topic_id: str,
    language: str,
    title: str,
    script: dict,
) -> int:
    key_phrases = script.get("key_phrases", [])
    fingerprint = content_fingerprint(topic_id, title, key_phrases)

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO canonical_scripts (topic_id, language, title, script_json, fingerprint, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                topic_id,
                language,
                title,
                json.dumps(script, ensure_ascii=False),
                fingerprint,
                now_utc_iso(),
            ),
        )

        conn.execute(
            """
            UPDATE topics
            SET last_used_at = ?, use_count = use_count + 1
            WHERE id = ?
            """,
            (now_utc_iso(), topic_id),
        )

    return int(cursor.lastrowid)


def store_publish_job(
    canonical_script_id: int,
    playlist_track: str,
    scheduled_at_iso: str,
    playlist_name: str | None = None,
) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO publish_jobs (
                canonical_script_id,
                playlist_track,
                playlist_name,
                scheduled_at,
                status,
                created_at
            )
            VALUES (?, ?, ?, ?, 'scheduled', ?)
            """,
            (
                canonical_script_id,
                playlist_track,
                playlist_name,
                scheduled_at_iso,
                datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            ),
        )
    return int(cursor.lastrowid)


def update_publish_job_artifacts(
    publish_job_id: int,
    artifact_path: str,
    video_file_path: str,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE publish_jobs
            SET artifact_path = ?, video_file_path = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                artifact_path,
                video_file_path,
                datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                publish_job_id,
            ),
        )


def update_publish_job_status(
    publish_job_id: int,
    status: str,
    status_detail: str = "",
    youtube_video_id: str | None = None,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE publish_jobs
            SET status = ?, status_detail = ?, youtube_video_id = COALESCE(?, youtube_video_id), updated_at = ?
            WHERE id = ?
            """,
            (
                status,
                status_detail,
                youtube_video_id,
                datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                publish_job_id,
            ),
        )
