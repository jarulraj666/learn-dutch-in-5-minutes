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
    # Keep migration logic lightweight for local-first development.
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(publish_jobs)").fetchall()
    }

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
            conn.execute(
                """
                INSERT OR IGNORE INTO topics (id, track, title_hint)
                VALUES (?, ?, ?)
                """,
                (topic["id"], topic["track"], topic["title_hint"]),
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
