from __future__ import annotations

from dataclasses import dataclass

from pipeline import settings
from pipeline.db import get_connection

# Category pick order: lower number = higher priority
_CATEGORY_ORDER = {
    "common_words": 1,
    "vocabulary": 2,
    "grammar": 3,
    "dialogue": 4,
}


@dataclass
class TopicChoice:
    topic_id: str
    track: str
    title_hint: str
    level: str = "A1"
    category: str = "dialogue"


def choose_next_topic(level: str = "A1") -> TopicChoice:
    """Pick the next topic from the DB.

    Priority:
    1. Any topic with status='selected' (manual override), ordered by category then order_index.
    2. Otherwise the next status='pending' topic, ordered by category priority then order_index.
    """
    with get_connection() as conn:
        # Manual override: 'selected' topics first
        row = conn.execute(
            """
            SELECT id, track, title_hint, level, category
            FROM topics
            WHERE level = ? AND status = 'selected'
            ORDER BY
              CASE category
                WHEN 'common_words' THEN 1
                WHEN 'vocabulary'   THEN 2
                WHEN 'grammar'      THEN 3
                WHEN 'dialogue'     THEN 4
                ELSE 5
              END,
              order_index
            LIMIT 1
            """,
            (level,),
        ).fetchone()

        if row is None:
            # Auto-pick: next pending topic in category + index order
            row = conn.execute(
                """
                SELECT id, track, title_hint, level, category
                FROM topics
                WHERE level = ? AND status = 'pending'
                ORDER BY
                  CASE category
                    WHEN 'common_words' THEN 1
                    WHEN 'vocabulary'   THEN 2
                    WHEN 'grammar'      THEN 3
                    WHEN 'dialogue'     THEN 4
                    ELSE 5
                  END,
                  order_index
                LIMIT 1
                """,
                (level,),
            ).fetchone()

    if row is None:
        raise RuntimeError(
            f"No pending or selected topics found for level={level!r}. "
            "All topics are done or skipped."
        )

    return TopicChoice(
        topic_id=row["id"],
        track=row["track"],
        title_hint=row["title_hint"],
        level=row["level"],
        category=row["category"],
    )
