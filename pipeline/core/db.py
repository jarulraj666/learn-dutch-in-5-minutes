from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from pipeline import settings


def get_connection() -> sqlite3.Connection:
    db_path = settings.DB_PATH
    if not db_path.is_absolute():
        db_path = settings.ROOT / db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


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
