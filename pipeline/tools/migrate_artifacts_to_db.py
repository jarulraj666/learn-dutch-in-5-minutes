"""Migrate existing disk artifact JSON files into the database.

Run once to populate publish_jobs.artifact_json for topics that have disk
artifacts but no DB blob.

Usage:
    python -m pipeline.tools.migrate_artifacts_to_db [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import settings  # noqa: E402
from pipeline.core.db import get_connection  # noqa: E402


def _find_all_artifacts() -> list[Path]:
    """Glob all episode artifact JSON files on disk."""
    found = []
    for p in sorted((ROOT / "output").glob("**/*.json")):
        if "render_manifest" in p.name or p.name.startswith("."):
            continue
        if not p.name.startswith("episode_"):
            continue
        found.append(p)
    return found


def _get_publish_job(conn, topic_id: str) -> dict | None:
    row = conn.execute(
        """
        SELECT pj.id, pj.artifact_json, pj.artifact_file_path
        FROM publish_jobs pj
        JOIN canonical_scripts cs ON cs.id = pj.canonical_script_id
        WHERE cs.topic_id = ?
        ORDER BY pj.id DESC LIMIT 1
        """,
        [topic_id],
    ).fetchone()
    return dict(row) if row else None


def migrate(dry_run: bool = False) -> None:
    artifacts = _find_all_artifacts()
    print(f"Found {len(artifacts)} artifact files on disk.")

    migrated = skipped = missing_job = errors = 0

    with get_connection() as conn:
        for path in artifacts:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"  ✗ Cannot read {path.name}: {e}")
                errors += 1
                continue

            topic_id = data.get("topic_id")
            if not topic_id:
                continue

            job = _get_publish_job(conn, topic_id)
            if job is None:
                print(f"  ⚠ No publish_job for {topic_id} — skipping")
                missing_job += 1
                continue

            if job["artifact_json"]:
                # Already has a blob — skip unless the disk file is newer
                skipped += 1
                continue

            rel_path = str(path.relative_to(ROOT))
            print(f"  → Migrating {topic_id} from {rel_path}")
            if not dry_run:
                conn.execute(
                    """
                    UPDATE publish_jobs
                    SET artifact_json = ?,
                        artifact_file_path = ?,
                        artifact_path = ?
                    WHERE id = ?
                    """,
                    [
                        json.dumps(data, ensure_ascii=False),
                        rel_path,
                        rel_path,
                        job["id"],
                    ],
                )
            migrated += 1

    print()
    print(f"{'[DRY RUN] ' if dry_run else ''}Results:")
    print(f"  Migrated  : {migrated}")
    print(f"  Skipped (already in DB): {skipped}")
    print(f"  No publish_job found   : {missing_job}")
    print(f"  Errors    : {errors}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Show what would be migrated without writing")
    args = parser.parse_args()
    migrate(dry_run=args.dry_run)
