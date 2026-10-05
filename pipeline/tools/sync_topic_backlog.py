"""Sync config/topic_backlog.yaml into the local topic database."""

from __future__ import annotations

import argparse

from pipeline import settings
from pipeline.core.db import get_connection, init_db, seed_topics_from_config


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync configured topics into the local pipeline SQLite database."
    )
    parser.parse_args()

    init_db()
    seed_topics_from_config()

    db_path = settings.DB_PATH
    if not db_path.is_absolute():
        db_path = settings.ROOT / db_path
    with get_connection() as conn:
        topic_count = conn.execute("SELECT count(*) FROM topics").fetchone()[0]

    configured_count = len(settings.TOPIC_BACKLOG_CONFIG.get("topics", []))
    print(f"Synced {configured_count} backlog topics to {db_path} ({topic_count} topics in database).")


if __name__ == "__main__":
    main()
