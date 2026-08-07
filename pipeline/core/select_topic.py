from __future__ import annotations

from dataclasses import dataclass

from pipeline import settings
from pipeline.core.db import get_connection

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
    level: str = "A1A2"
    category: str = "dialogue"
    # Multi-speaker dialogue fields (optional, only for dialogue category)
    scenario: str | None = None
    speaker1_role: str | None = None
    speaker2_role: str | None = None
    speaker1_gender: str | None = None
    speaker2_gender: str | None = None


def choose_next_topic(level: str = "A1A2", category: str | None = None) -> TopicChoice:
    """Pick the next topic from the DB.

    Priority:
    1. Any topic with status='selected' (manual override), ordered by category then order_index.
    2. Otherwise the next status='pending' topic, ordered by category priority then order_index.

    Args:
        level: CEFR level to filter by (e.g. 'A1').
        category: Optional category to restrict to (e.g. 'common_words', 'grammar').
    """
    category_filter = "AND category = ?" if category else ""
    params_base = (level, category) if category else (level,)

    with get_connection() as conn:
        # Manual override: 'selected' topics first
        row = conn.execute(
            f"""
            SELECT id, track, title_hint, level, category
            FROM topics
            WHERE level = ? AND status = 'selected' {category_filter}
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
            params_base,
        ).fetchone()

        if row is None:
            # Auto-pick: next pending topic in category + index order
            row = conn.execute(
                f"""
                SELECT id, track, title_hint, level, category
                FROM topics
                WHERE level = ? AND status = 'pending' {category_filter}
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
                params_base,
            ).fetchone()

    category_hint = f" category={category!r}" if category else ""
    if row is None:
        raise RuntimeError(
            f"No pending or selected topics found for level={level!r}{category_hint}. "
            "All topics are done or skipped."
        )

    # Load dialogue-specific metadata from config
    dialogue_metadata = _load_dialogue_metadata(row["id"])

    return TopicChoice(
        topic_id=row["id"],
        track=row["track"],
        title_hint=row["title_hint"],
        level=row["level"],
        category=row["category"],
        scenario=dialogue_metadata.get("scenario"),
        speaker1_role=dialogue_metadata.get("speaker1_role"),
        speaker2_role=dialogue_metadata.get("speaker2_role"),
        speaker1_gender=dialogue_metadata.get("speaker1_gender"),
        speaker2_gender=dialogue_metadata.get("speaker2_gender"),
    )


def _load_dialogue_metadata(topic_id: str) -> dict:
    """Load dialogue-specific metadata (scenario, speaker roles) from topic_backlog.yaml.
    
    Returns empty dict for non-dialogue topics or if metadata not found.
    """
    topics = settings.TOPIC_BACKLOG_CONFIG.get("topics", [])
    for topic in topics:
        if topic.get("id") == topic_id:
            return {
                "scenario": topic.get("scenario"),
                "speaker1_role": topic.get("speaker1_role"),
                "speaker2_role": topic.get("speaker2_role"),
                "speaker1_gender": topic.get("speaker1_gender"),
                "speaker2_gender": topic.get("speaker2_gender"),
            }
    return {}
