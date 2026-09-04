from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from pipeline import settings


def get_connection() -> sqlite3.Connection:
    db_path = settings.DB_PATH
    if not db_path.is_absolute():
        db_path = settings.ROOT / db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _latest_publish_job_artifact(conn: sqlite3.Connection, topic_id: str) -> tuple[int, dict] | None:
    row = conn.execute(
        """
        SELECT pj.id, pj.artifact_json
        FROM canonical_scripts cs
        JOIN publish_jobs pj ON pj.canonical_script_id = cs.id
        WHERE cs.topic_id = ? AND pj.artifact_json IS NOT NULL
        ORDER BY pj.id DESC
        LIMIT 1
        """,
        [topic_id],
    ).fetchone()
    if not row:
        return None
    try:
        return row["id"], json.loads(row["artifact_json"])
    except (TypeError, json.JSONDecodeError):
        return None


def claim_facebook_reel_upload(topic_id: str, scene: int) -> tuple[str, dict, dict] | None:
    """Atomically reserve a Facebook reel upload, returning its claim and media data.

    Claims expire after two hours so a crashed worker does not block a future retry.
    """
    now = datetime.now(timezone.utc)
    expires_before = (now - timedelta(hours=2)).isoformat()
    claim_id = uuid4().hex
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        job = _latest_publish_job_artifact(conn, topic_id)
        if not job:
            return None
        job_id, artifact = job
        shorts = artifact.get("shorts") or []
        short = next((item for item in shorts if str(item.get("scene")) == str(scene)), None)
        if short is None or short.get("facebook", {}).get("post_id"):
            return None
        existing_claim = short.get("facebook_upload_claim") or {}
        if existing_claim.get("claimed_at", "") > expires_before:
            return None
        short["facebook_upload_claim"] = {"id": claim_id, "claimed_at": now.isoformat()}
        conn.execute(
            "UPDATE publish_jobs SET artifact_json = ? WHERE id = ?",
            [json.dumps(artifact, ensure_ascii=False), job_id],
        )
        return claim_id, artifact, short


def complete_facebook_reel_upload(topic_id: str, scene: int, claim_id: str, result: dict) -> bool:
    """Record a Facebook upload result only when it still owns the given claim."""
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        job = _latest_publish_job_artifact(conn, topic_id)
        if not job:
            return False
        job_id, artifact = job
        short = next((item for item in artifact.get("shorts") or [] if str(item.get("scene")) == str(scene)), None)
        if not short or short.get("facebook_upload_claim", {}).get("id") != claim_id:
            return False
        short["facebook"] = result
        short.pop("facebook_upload_claim", None)
        short["facebook_scheduled_at"] = None
        conn.execute(
            "UPDATE publish_jobs SET artifact_json = ? WHERE id = ?",
            [json.dumps(artifact, ensure_ascii=False), job_id],
        )
        return True


def release_facebook_reel_upload_claim(topic_id: str, scene: int, claim_id: str) -> bool:
    """Release a failed upload's claim without disturbing a newer worker's claim."""
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        job = _latest_publish_job_artifact(conn, topic_id)
        if not job:
            return False
        job_id, artifact = job
        short = next((item for item in artifact.get("shorts") or [] if str(item.get("scene")) == str(scene)), None)
        if not short or short.get("facebook_upload_claim", {}).get("id") != claim_id:
            return False
        short.pop("facebook_upload_claim", None)
        conn.execute(
            "UPDATE publish_jobs SET artifact_json = ? WHERE id = ?",
            [json.dumps(artifact, ensure_ascii=False), job_id],
        )
        return True


def claim_instagram_reel_upload(topic_id: str, scene: int) -> tuple[str, dict, dict] | None:
    """Atomically reserve an Instagram reel upload, returning its claim and media data."""
    now = datetime.now(timezone.utc)
    expires_before = (now - timedelta(hours=2)).isoformat()
    claim_id = uuid4().hex
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        job = _latest_publish_job_artifact(conn, topic_id)
        if not job:
            return None
        job_id, artifact = job
        short = next((item for item in artifact.get("shorts") or [] if str(item.get("scene")) == str(scene)), None)
        if short is None or short.get("instagram", {}).get("reel_id"):
            return None
        existing_claim = short.get("instagram_upload_claim") or {}
        if existing_claim.get("claimed_at", "") > expires_before:
            return None
        short["instagram_upload_claim"] = {"id": claim_id, "claimed_at": now.isoformat()}
        conn.execute(
            "UPDATE publish_jobs SET artifact_json = ? WHERE id = ?",
            [json.dumps(artifact, ensure_ascii=False), job_id],
        )
        return claim_id, artifact, short


def record_instagram_pending_container(topic_id: str, scene: int, claim_id: str, container_id: str) -> bool:
    """Persist a created media container so a retry republishes it instead of duplicating."""
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        job = _latest_publish_job_artifact(conn, topic_id)
        if not job:
            return False
        job_id, artifact = job
        short = next((item for item in artifact.get("shorts") or [] if str(item.get("scene")) == str(scene)), None)
        if not short or short.get("instagram_upload_claim", {}).get("id") != claim_id:
            return False
        short["instagram_pending_container"] = {
            "id": container_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        conn.execute(
            "UPDATE publish_jobs SET artifact_json = ? WHERE id = ?",
            [json.dumps(artifact, ensure_ascii=False), job_id],
        )
        return True


def complete_instagram_reel_upload(topic_id: str, scene: int, claim_id: str, result: dict) -> bool:
    """Record an Instagram upload result only when it still owns the given claim."""
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        job = _latest_publish_job_artifact(conn, topic_id)
        if not job:
            return False
        job_id, artifact = job
        short = next((item for item in artifact.get("shorts") or [] if str(item.get("scene")) == str(scene)), None)
        if not short or short.get("instagram_upload_claim", {}).get("id") != claim_id:
            return False
        short["instagram"] = result
        short["reel_id"] = result.get("reel_id")
        short["permalink"] = result.get("permalink")
        short.pop("instagram_upload_claim", None)
        short.pop("instagram_pending_container", None)
        short["instagram_scheduled_at"] = None
        conn.execute(
            "UPDATE publish_jobs SET artifact_json = ? WHERE id = ?",
            [json.dumps(artifact, ensure_ascii=False), job_id],
        )
        return True


def release_instagram_reel_upload_claim(topic_id: str, scene: int, claim_id: str) -> bool:
    """Release a failed Instagram upload's claim without disturbing another worker."""
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        job = _latest_publish_job_artifact(conn, topic_id)
        if not job:
            return False
        job_id, artifact = job
        short = next((item for item in artifact.get("shorts") or [] if str(item.get("scene")) == str(scene)), None)
        if not short or short.get("instagram_upload_claim", {}).get("id") != claim_id:
            return False
        short.pop("instagram_upload_claim", None)
        conn.execute(
            "UPDATE publish_jobs SET artifact_json = ? WHERE id = ?",
            [json.dumps(artifact, ensure_ascii=False), job_id],
        )
        return True


def init_db() -> None:
    schema_path = settings.ROOT / "db/schema.sql"
    sql = schema_path.read_text(encoding="utf-8")

    with get_connection() as conn:
        conn.executescript(sql)
        _ensure_runtime_migrations(conn)


def _ensure_runtime_migrations(conn: sqlite3.Connection) -> None:
    # topics table — new columns for level/category/status/order
    topic_cols = {row["name"] for row in conn.execute("PRAGMA table_info(topics)").fetchall()}
    topic_required = {
        "level": "TEXT NOT NULL DEFAULT 'A1A2'",
        "category": "TEXT NOT NULL DEFAULT 'dialogue'",
        "status": "TEXT NOT NULL DEFAULT 'pending'",
        "order_index": "INTEGER NOT NULL DEFAULT 0",
    }
    for col, col_def in topic_required.items():
        if col not in topic_cols:
            conn.execute(f"ALTER TABLE topics ADD COLUMN {col} {col_def}")

    # Create pick index if missing
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_topics_pick "
        "ON topics(level, category, status, order_index)"
    )

    # publish_jobs table — existing migrations
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(publish_jobs)").fetchall()}
    required_columns = {
        "playlist_name": "TEXT",
        "artifact_path": "TEXT",
        "video_file_path": "TEXT",
        "status_detail": "TEXT",
        "updated_at": "TEXT",
    }
    for col, col_type in required_columns.items():
        if col not in columns:
            conn.execute(f"ALTER TABLE publish_jobs ADD COLUMN {col} {col_type}")


def seed_topics_from_config() -> None:
    topics = settings.TOPIC_BACKLOG_CONFIG.get("topics", [])
    with get_connection() as conn:
        for topic in topics:
            # Insert new topics; update title_hint and track if YAML changed
            conn.execute(
                """
                INSERT INTO topics
                  (id, track, title_hint, level, category, status, order_index)
                VALUES (?, ?, ?, ?, ?, 'pending', ?)
                ON CONFLICT(id) DO UPDATE SET
                  title_hint  = excluded.title_hint,
                  track       = excluded.track,
                  order_index = excluded.order_index
                """,
                (
                    topic["id"],
                    topic.get("track", "daily_life"),
                    topic["title_hint"],
                    topic.get("level", "A1A2"),
                    topic.get("category", "dialogue"),
                    int(topic.get("order_index", 0)),
                ),
            )


def get_topic_by_id(topic_id: str) -> dict | None:
    """Fetch a single topic row by ID. Returns None if not found."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, track, title_hint, level, category, status, order_index FROM topics WHERE id = ?",
            (topic_id,),
        ).fetchone()
    return dict(row) if row else None


def mark_topic_generated(topic_id: str) -> None:
    """Mark a topic as generated (video rendered) but not yet uploaded to YouTube."""
    from pipeline.utils import now_utc_iso
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE topics
            SET status = 'generated', last_used_at = ?
            WHERE id = ?
            """,
            (now_utc_iso(), topic_id),
        )


def mark_topic_ready_to_publish(topic_id: str) -> None:
    """Mark a topic as ready_to_publish (main video + shorts rendered)."""
    from pipeline.utils import now_utc_iso
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE topics
            SET status = 'ready_to_publish', last_used_at = ?
            WHERE id = ?
            """,
            (now_utc_iso(), topic_id),
        )


def mark_topic_done(topic_id: str) -> None:
    """Mark a topic as done after successful YouTube upload."""
    from pipeline.utils import now_utc_iso
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE topics
            SET status = 'done', last_used_at = ?, use_count = use_count + 1
            WHERE id = ?
            """,
            (now_utc_iso(), topic_id),
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--init", action="store_true", help="Initialize DB schema")
    args = parser.parse_args()

    if args.init:
        init_db()
        seed_topics_from_config()
        print("Database initialized and topics seeded.")


if __name__ == "__main__":
    main()
