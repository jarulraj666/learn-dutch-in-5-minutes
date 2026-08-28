"""Normalize CEFR level values across the database.

Older artifacts store ``level: "A1"`` while the pipeline and configs use
``"A1A2"``. The learner app groups lessons into courses by level, so the values
must be consistent.

Usage:
    python -m pipeline.tools.normalize_levels --dry-run
    python -m pipeline.tools.normalize_levels
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize level values (A1/A2 → A1A2)")
    parser.add_argument("--dry-run", action="store_true", help="Report only; no writes")
    args = parser.parse_args()

    from pipeline.core.db import get_connection
    from pipeline.stages import normalize_level

    topic_changes: list[tuple[str, str, str]] = []
    artifact_changes: list[tuple[int, str, str]] = []

    with get_connection() as conn:
        for row in conn.execute("SELECT id, level FROM topics").fetchall():
            new = normalize_level(row["level"] or "")
            if new and new != row["level"]:
                topic_changes.append((row["id"], row["level"], new))

        for row in conn.execute(
            "SELECT id, artifact_json FROM publish_jobs WHERE artifact_json IS NOT NULL"
        ).fetchall():
            try:
                artifact = json.loads(row["artifact_json"])
            except json.JSONDecodeError:
                continue
            old = artifact.get("level", "")
            new = normalize_level(old)
            nested_old = (artifact.get("topic") or {}).get("level", "")
            script_old = (artifact.get("script") or {}).get("level", "")
            if new == old and normalize_level(nested_old) == nested_old and normalize_level(script_old) == script_old:
                continue
            artifact_changes.append((row["id"], old, new))

    print(f"topics to update:    {len(topic_changes)}")
    print(f"artifacts to update: {len(artifact_changes)}")
    for topic_id, old, new in topic_changes[:10]:
        print(f"  topic {topic_id}: {old} → {new}")

    if args.dry_run or not (topic_changes or artifact_changes):
        return 0

    with get_connection() as conn:
        for topic_id, _old, new in topic_changes:
            conn.execute("UPDATE topics SET level = ? WHERE id = ?", [new, topic_id])

        for job_id, _old, _new in artifact_changes:
            row = conn.execute(
                "SELECT artifact_json FROM publish_jobs WHERE id = ?", [job_id]
            ).fetchone()
            artifact = json.loads(row["artifact_json"])
            artifact["level"] = normalize_level(artifact.get("level", ""))
            for key in ("topic", "script"):
                nested = artifact.get(key)
                if isinstance(nested, dict) and nested.get("level"):
                    nested["level"] = normalize_level(nested["level"])
            conn.execute(
                "UPDATE publish_jobs SET artifact_json = ? WHERE id = ?",
                [json.dumps(artifact, ensure_ascii=False), job_id],
            )

    print(f"✅ Normalized {len(topic_changes)} topics and {len(artifact_changes)} artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
