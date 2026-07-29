from __future__ import annotations

from dataclasses import dataclass

from pipeline import settings
from pipeline.db import get_connection
from pipeline.utils import jaccard_similarity


@dataclass
class TopicChoice:
    topic_id: str
    track: str
    title_hint: str


def _recent_topics(limit: int) -> list[str]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT topic_id
            FROM canonical_scripts
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [r["topic_id"] for r in rows]


def _historical_titles() -> list[str]:
    with get_connection() as conn:
        rows = conn.execute("SELECT title FROM canonical_scripts").fetchall()
    return [r["title"] for r in rows]


def choose_next_topic() -> TopicChoice:
    cooldown = int(settings.TOPIC_BACKLOG_CONFIG.get("cooldown_last_topics", 4))
    max_similarity = float(settings.TOPIC_BACKLOG_CONFIG.get("max_similarity_threshold", 0.75))

    backlog = settings.TOPIC_BACKLOG_CONFIG.get("topics", [])
    recent = set(_recent_topics(cooldown))
    historical = _historical_titles()

    filtered = [t for t in backlog if t["id"] not in recent]
    if not filtered:
        filtered = backlog

    best = None
    best_score = -1.0

    for topic in filtered:
        title_hint = topic["title_hint"]
        max_seen_similarity = max((jaccard_similarity(title_hint, h) for h in historical), default=0.0)
        novelty = 1.0 - max_seen_similarity

        if max_seen_similarity >= max_similarity:
            continue

        if novelty > best_score:
            best_score = novelty
            best = topic

    if best is None:
        best = filtered[0]

    return TopicChoice(
        topic_id=best["id"],
        track=best["track"],
        title_hint=best["title_hint"],
    )
