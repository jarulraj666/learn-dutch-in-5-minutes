from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from pipeline import settings
from pipeline.core.db import get_connection, init_db, seed_topics_from_config
from pipeline.core.store_content import update_publish_job_status
from pipeline.publish.upload_youtube import build_upload_payload, upload_video
from pipeline.utils import now_utc_iso


def _due_jobs(include_future: bool = False, job_id: int | None = None) -> list[dict]:
    now_iso = datetime.now(timezone.utc).isoformat()
    statuses = ("ready_for_upload", "upload_failed", "scheduled", "upload_dry_run")

    if job_id is not None:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, canonical_script_id, scheduled_at, status, 
                       artifact_json, artifact_file_path, video_file_path
                FROM publish_jobs
                WHERE id = ?
                """,
                (job_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    with get_connection() as conn:
        if include_future:
            rows = conn.execute(
                """
                SELECT id, canonical_script_id, scheduled_at, status, 
                       artifact_json, artifact_file_path, video_file_path
                FROM publish_jobs
                WHERE status IN (?, ?, ?, ?)
                ORDER BY scheduled_at ASC
                """,
                statuses,
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, canonical_script_id, scheduled_at, status, 
                       artifact_json, artifact_file_path, video_file_path
                FROM publish_jobs
                WHERE status IN (?, ?, ?, ?)
                  AND scheduled_at <= ?
                ORDER BY scheduled_at ASC
                """,
                (*statuses, now_iso),
            ).fetchall()

    return [dict(r) for r in rows]


def _load_artifact(row: dict) -> dict | None:
    """Load artifact from database JSON string or file fallback.
    
    Args:
        row: Database row with artifact_json and artifact_file_path
    
    Returns:
        Artifact dict or None if cannot be loaded
    """
    # Try loading from database JSON first
    if row.get("artifact_json"):
        try:
            if isinstance(row["artifact_json"], str):
                return json.loads(row["artifact_json"])
            else:
                return row["artifact_json"]
        except (json.JSONDecodeError, TypeError):
            pass
    
    # Fallback: load from file
    if row.get("artifact_file_path"):
        artifact_path = Path(row["artifact_file_path"])
        if artifact_path.exists():
            try:
                return json.loads(artifact_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, IOError):
                pass
    
    return None


def _artifact_path(row: dict) -> Path:
    """Get artifact file path from database or construct fallback."""
    if row.get("artifact_file_path"):
        return Path(row["artifact_file_path"])
    out_dir = settings.OUTPUT_DIR
    if not out_dir.is_absolute():
        out_dir = settings.ROOT / out_dir
    return out_dir / f"episode_{row['canonical_script_id']}.json"


def _video_path(row: dict, artifact: dict | None) -> Path | None:
    """Extract video file path from database or artifact.
    
    Args:
        row: Database row with video_file_path
        artifact: Artifact dict loaded from database/file
    
    Returns:
        Path to video file or None
    """
    # Primary: use database video_file_path if set
    if row.get("video_file_path"):
        return Path(row["video_file_path"])
    
    # Secondary: extract from artifact
    if artifact:
        planned = artifact.get("render", {}).get("planned_video_file", "")
        if planned:
            return Path(planned)
        
        # Try storage.archived_video_file
        archived = artifact.get("storage", {}).get("archived_video_file", "")
        if archived:
            return Path(archived)
    
    return None



def process_pending(dry_run: bool = True, include_future: bool = False, job_id: int | None = None) -> list[dict]:
    jobs = _due_jobs(include_future=include_future, job_id=job_id)
    results: list[dict] = []

    for job in jobs:
        job_id = int(job["id"])
        
        # Load artifact from database JSON or file
        artifact = _load_artifact(job)
        if not artifact:
            update_publish_job_status(job_id, "upload_failed", "Failed to load artifact JSON")
            results.append({"job_id": job_id, "status": "upload_failed", "reason": "artifact_load_failed"})
            continue
        
        artifact_path = _artifact_path(job)
        video_path = _video_path(job, artifact)

        if dry_run:
            payload = build_upload_payload(artifact_path)
            update_publish_job_status(job_id, "upload_dry_run", "Dry run completed")
            results.append(
                {
                    "job_id": job_id,
                    "status": "upload_dry_run",
                    "artifact": str(artifact_path),
                    "video": str(video_path) if video_path else "",
                    "payload_title": payload.get("snippet", {}).get("title", ""),
                }
            )
            continue

        if not video_path or not video_path.exists():
            update_publish_job_status(job_id, "upload_failed", f"Missing video: {video_path}")
            results.append({"job_id": job_id, "status": "upload_failed", "reason": "video_missing"})
            continue

        try:
            uploaded = upload_video(artifact_path, video_path)
            update_publish_job_status(
                job_id,
                "uploaded",
                "Uploaded to YouTube and playlist processed",
                youtube_video_id=uploaded.get("video_id"),
                published_at=now_utc_iso(),
            )
            results.append(
                {
                    "job_id": job_id,
                    "status": "uploaded",
                    "video_id": uploaded.get("video_id"),
                    "playlist_id": uploaded.get("playlist_id"),
                    "published_at": now_utc_iso(),
                }
            )
        except Exception as exc:
            update_publish_job_status(job_id, "upload_failed", str(exc))
            results.append({"job_id": job_id, "status": "upload_failed", "reason": str(exc)})

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Process pending publish jobs")
    parser.add_argument("--execute", action="store_true", help="Execute real uploads instead of dry-run")
    parser.add_argument("--include-future", action="store_true", help="Include future scheduled jobs")
    parser.add_argument("--job-id", type=int, help="Process a specific publish job id")
    args = parser.parse_args()

    init_db()
    seed_topics_from_config()

    results = process_pending(
        dry_run=not args.execute,
        include_future=args.include_future,
        job_id=args.job_id,
    )
    print(json.dumps({"count": len(results), "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
