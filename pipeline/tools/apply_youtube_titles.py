"""Apply numbered YouTube titles to uploaded videos.

The canonical titles live in ``topics.youtube_title`` in the database.
To assign or change a title for a topic, update that column — no code change needed.

Usage:
    # Dry-run all categories (show what would change, don't write):
    python -m pipeline.tools.apply_youtube_titles --dry-run

    # Apply all categories:
    python -m pipeline.tools.apply_youtube_titles

    # Apply a single category:
    python -m pipeline.tools.apply_youtube_titles --category grammar
    python -m pipeline.tools.apply_youtube_titles --category common_words
    python -m pipeline.tools.apply_youtube_titles --category vocabulary

    # Apply a single topic:
    python -m pipeline.tools.apply_youtube_titles --topic grammar_de_het

    # Update DB only (skip YouTube API):
    python -m pipeline.tools.apply_youtube_titles --skip-youtube
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
LOGGER = logging.getLogger(__name__)

KNOWN_CATEGORIES = ("grammar", "common_words", "vocabulary")


def _load_titles_from_db(
    category: str | None = None,
    topic_id: str | None = None,
) -> list[tuple[str, str]]:
    """Return [(topic_id, youtube_title)] for topics that have a youtube_title set."""
    from pipeline.core.db import get_connection

    with get_connection() as conn:
        if topic_id:
            rows = conn.execute(
                "SELECT id, youtube_title FROM topics WHERE id = ? AND youtube_title IS NOT NULL",
                [topic_id],
            ).fetchall()
        elif category:
            rows = conn.execute(
                "SELECT id, youtube_title FROM topics WHERE category = ? AND youtube_title IS NOT NULL",
                [category],
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, youtube_title FROM topics WHERE youtube_title IS NOT NULL"
            ).fetchall()

    return [(r["id"], r["youtube_title"]) for r in rows]


def _get_db_rows(topic_ids: list[str]) -> dict[str, dict]:
    from pipeline.core.db import get_connection

    result: dict[str, dict] = {}
    with get_connection() as conn:
        for tid in topic_ids:
            row = conn.execute(
                """
                SELECT pj.id AS pj_id, pj.artifact_json
                FROM canonical_scripts cs
                JOIN publish_jobs pj ON pj.canonical_script_id = cs.id
                  AND pj.id = (SELECT MAX(id) FROM publish_jobs WHERE canonical_script_id = cs.id)
                WHERE cs.topic_id = ?
                ORDER BY cs.id DESC LIMIT 1
                """,
                [tid],
            ).fetchone()
            if not row or not row["artifact_json"]:
                continue
            a = json.loads(row["artifact_json"])
            result[tid] = {
                "pj_id": row["pj_id"],
                "artifact": a,
                "video_id": a.get("youtube", {}).get("video_id", ""),
                "current_title": a.get("metadata", {}).get("title", ""),
            }
    return result


def _update_db(pj_id: int, artifact: dict, new_title: str) -> None:
    from pipeline.core.db import get_connection

    artifact.setdefault("metadata", {})["title"] = new_title
    with get_connection() as conn:
        conn.execute(
            "UPDATE publish_jobs SET artifact_json = ? WHERE id = ?",
            [json.dumps(artifact, ensure_ascii=False), pj_id],
        )


def _update_youtube(youtube, video_id: str, new_title: str) -> None:
    current = youtube.videos().list(part="snippet", id=video_id).execute()
    if not current.get("items"):
        raise ValueError(f"Video {video_id} not found on YouTube")
    snippet = current["items"][0]["snippet"]
    snippet["title"] = new_title[:100]
    youtube.videos().update(part="snippet", body={"id": video_id, "snippet": snippet}).execute()


def run(
    titles: list[tuple[str, str]],
    dry_run: bool = False,
    skip_youtube: bool = False,
) -> None:
    if not titles:
        LOGGER.warning("No topics with youtube_title found for the given filter.")
        return

    db_rows = _get_db_rows([tid for tid, _ in titles])

    youtube = None
    if not dry_run and not skip_youtube:
        from pipeline.publish.upload_youtube import _get_youtube_client
        youtube = _get_youtube_client()

    ok = skip = already_ok = fail = 0

    for tid, new_title in titles:
        row = db_rows.get(tid)
        if not row:
            LOGGER.warning("SKIP  %-45s  no publish artifact in DB", tid)
            skip += 1
            continue

        vid = row["video_id"]
        current = row["current_title"]

        if current == new_title and not dry_run:
            LOGGER.info("OK    %-45s  already up to date", tid)
            already_ok += 1
            continue

        if dry_run:
            marker = "~" if current == new_title else ">"
            LOGGER.info("DRY %s %-45s  %s", marker, tid, new_title[:70])
            continue

        _update_db(row["pj_id"], row["artifact"], new_title)

        if vid and youtube:
            try:
                _update_youtube(youtube, vid, new_title)
                LOGGER.info("OK    %-45s  yt=%s", tid, vid)
                ok += 1
            except Exception as exc:
                LOGGER.warning("FAIL  %-45s  yt=%s  %s", tid, vid, exc)
                fail += 1
        else:
            reason = "no video_id" if not vid else "skip_youtube"
            LOGGER.info("DB-OK %-45s  YouTube skipped (%s)", tid, reason)
            ok += 1

    if not dry_run:
        LOGGER.info(
            "Done. updated=%d  already_ok=%d  skipped=%d  failed=%d",
            ok, already_ok, skip, fail,
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--category", choices=KNOWN_CATEGORIES, help="Only process this category")
    parser.add_argument("--topic", help="Only process this single topic_id")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without writing")
    parser.add_argument("--skip-youtube", action="store_true", help="Update DB only, skip YouTube API")
    args = parser.parse_args()

    titles = _load_titles_from_db(category=args.category, topic_id=args.topic)
    run(titles, dry_run=args.dry_run, skip_youtube=args.skip_youtube)


if __name__ == "__main__":
    main()
