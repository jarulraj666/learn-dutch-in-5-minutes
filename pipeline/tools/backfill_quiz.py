"""Backfill learner-facing quizzes into stored episode artifacts.

Dialogue episodes were generated without a quiz, and older grammar/vocabulary
quizzes lack stable ids and explanations. This tool brings every stored artifact
up to the shape the learner app expects.

Usage:
    # See what would change, no writes, no LLM calls:
    python -m pipeline.tools.backfill_quiz --dry-run

    # Backfill everything that is missing or incomplete:
    python -m pipeline.tools.backfill_quiz

    # Narrow the run:
    python -m pipeline.tools.backfill_quiz --category dialogue
    python -m pipeline.tools.backfill_quiz --level A1A2
    python -m pipeline.tools.backfill_quiz --topic weather_chat

    # Regenerate even quizzes that already look complete:
    python -m pipeline.tools.backfill_quiz --force
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


def _candidate_rows(level: str | None, category: str | None, topic_id: str | None):
    """Latest publish_job per topic, with the artifact blob."""
    from pipeline.core.db import get_connection

    sql = """
        SELECT t.id AS topic_id, t.level, t.category, pj.id AS job_id, pj.artifact_json
        FROM topics t
        JOIN canonical_scripts cs ON cs.topic_id = t.id
            AND cs.id = (SELECT MAX(id) FROM canonical_scripts WHERE topic_id = t.id)
        JOIN publish_jobs pj ON pj.canonical_script_id = cs.id
            AND pj.id = (SELECT MAX(id) FROM publish_jobs WHERE canonical_script_id = cs.id)
        WHERE pj.artifact_json IS NOT NULL
    """
    params: list[str] = []
    if topic_id:
        sql += " AND t.id = ?"
        params.append(topic_id)
    if category:
        sql += " AND t.category = ?"
        params.append(category)
    if level:
        sql += " AND t.level = ?"
        params.append(level)
    sql += " ORDER BY t.category, t.order_index, t.id"

    with get_connection() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _persist(job_id: int, artifact: dict, topic_id: str, script: dict) -> None:
    from pipeline.core.db import get_connection
    from pipeline.core.store_content import store_canonical_script

    with get_connection() as conn:
        conn.execute(
            "UPDATE publish_jobs SET artifact_json = ? WHERE id = ?",
            [json.dumps(artifact, ensure_ascii=False), job_id],
        )
    store_canonical_script(
        topic_id=topic_id,
        language=script.get("language", "nl"),
        title=artifact.get("metadata", {}).get("title") or artifact.get("title_slug", ""),
        script=script,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill quizzes into stored artifacts")
    parser.add_argument("--dry-run", action="store_true", help="Report only; no LLM calls, no writes")
    parser.add_argument("--force", action="store_true", help="Regenerate even complete quizzes")
    parser.add_argument("--level", help="Restrict to one CEFR level (e.g. A1A2)")
    parser.add_argument("--category", help="Restrict to one category (e.g. dialogue)")
    parser.add_argument("--topic", help="Restrict to one topic id")
    parser.add_argument("--questions", type=int, default=5, help="Questions per quiz (default: 5)")
    parser.add_argument("--limit", type=int, help="Stop after N regenerations")
    args = parser.parse_args()

    from pipeline.generate.generate_quiz import quiz_is_complete
    from pipeline.stages import normalize_level, stage_quiz

    rows = _candidate_rows(args.level, args.category, args.topic)
    if not rows:
        print("No matching topics with a stored artifact.")
        return 0

    ok = skipped = no_script = failed = 0

    for row in rows:
        topic_id = row["topic_id"]
        try:
            artifact = json.loads(row["artifact_json"])
        except json.JSONDecodeError as exc:
            print(f"  ✗ {topic_id}: unreadable artifact_json ({exc})")
            failed += 1
            continue

        script = artifact.get("script")
        if not script or not (script.get("dialogue") or script.get("script_text")):
            print(f"  – {topic_id}: no script yet, skipping")
            no_script += 1
            continue

        existing = script.get("quiz") or []
        if quiz_is_complete(existing) and not args.force:
            skipped += 1
            continue

        reason = "incomplete" if existing else "missing"
        if args.dry_run:
            print(f"  → {topic_id} ({row['category']}): quiz {reason} ({len(existing)} questions)")
            ok += 1
            continue

        if args.limit is not None and ok >= args.limit:
            break

        level = normalize_level(artifact.get("level") or row["level"] or "A1A2")
        category = artifact.get("category") or row["category"] or "dialogue"

        try:
            quiz = stage_quiz(
                script,
                level=level,
                category=category,
                topic_id=topic_id,
                question_count=args.questions,
            )
        except Exception as exc:
            print(f"  ✗ {topic_id}: generation error — {exc}")
            failed += 1
            continue

        if not quiz:
            print(f"  ✗ {topic_id}: no valid questions produced")
            failed += 1
            continue

        script["quiz"] = quiz
        artifact["script"] = script
        try:
            _persist(row["job_id"], artifact, topic_id, script)
        except Exception as exc:
            print(f"  ✗ {topic_id}: persist failed — {exc}")
            failed += 1
            continue

        print(f"  ✓ {topic_id} ({category}): {len(quiz)} questions ({reason})")
        ok += 1

    verb = "would update" if args.dry_run else "updated"
    print(
        f"\n{verb}: {ok} · already complete: {skipped} · "
        f"no script: {no_script} · failed: {failed} · scanned: {len(rows)}"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
