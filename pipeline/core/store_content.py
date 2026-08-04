from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from pipeline import settings
from pipeline.core.db import get_connection
from pipeline.utils import content_fingerprint, now_utc_iso


def create_title_slug(title: str, max_length: int = 50) -> str:
    """Create URL-safe slug from title for use in filenames.
    
    Args:
        title: Topic title or name
        max_length: Maximum length of slug
    
    Returns:
        Lowercase slug with spaces replaced by underscores, truncated to max_length
    """
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    slug = slug.strip("_")
    return slug[:max_length]


def ensure_output_dir(level: str, category: str, file_type: str | None = None) -> Path:
    """Ensure output directory structure exists for level/category/type.
    
    Args:
        level: Level (A1, A2, B1, B2)
        category: Category (common_words, dialogue, grammar, etc.)
        file_type: Optional file type subdirectory (visuals, audio, videos, subtitles)
    
    Returns:
        Path to the created directory
    """
    output_path = settings.OUTPUT_DIR / level / category
    if file_type:
        output_path = output_path / file_type
    
    output_path.mkdir(parents=True, exist_ok=True)
    return output_path


def get_artifact_path(topic_id: str, title: str, level: str, category: str) -> Path:
    """Get the full path for an episode artifact file.
    
    Args:
        topic_id: Topic ID (for fallback if title is empty)
        title: Topic/episode title
        level: Level (A1, A2, B1, B2)
        category: Category (common_words, dialogue, etc.)
    
    Returns:
        Path to artifact file (e.g., output/A1/common_words/episode_123_common_words.json)
    """
    slug = create_title_slug(title) if title else f"topic_{topic_id}"
    artifact_dir = ensure_output_dir(level, category)
    return artifact_dir / f"episode_{topic_id}_{slug}.json"


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


def save_episode_artifact(
    publish_job_id: int,
    artifact_json: dict | str,
    artifact_file_path: str,
) -> None:
    """Save episode artifact JSON to publish_jobs table for later video generation/publishing.
    
    Args:
        publish_job_id: ID of the publish job record
        artifact_json: Full episode artifact dict or JSON string
        artifact_file_path: Local path to artifact file (e.g., output/A1/common_words/episode_123_common_words.json)
    """
    artifact_json_str = artifact_json if isinstance(artifact_json, str) else json.dumps(artifact_json, ensure_ascii=False)
    
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE publish_jobs
            SET artifact_json = ?, artifact_file_path = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                artifact_json_str,
                artifact_file_path,
                datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                publish_job_id,
            ),
        )


def update_publish_job_status(
    publish_job_id: int,
    status: str,
    status_detail: str = "",
    youtube_video_id: str | None = None,
    published_at: str | None = None,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE publish_jobs
            SET status = ?, status_detail = ?, youtube_video_id = COALESCE(?, youtube_video_id), 
                published_at = COALESCE(?, published_at), updated_at = ?
            WHERE id = ?
            """,
            (
                status,
                status_detail,
                youtube_video_id,
                published_at,
                datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                publish_job_id,
            ),
        )
