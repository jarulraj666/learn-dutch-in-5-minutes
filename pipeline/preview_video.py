from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from pipeline import settings
from pipeline.db import get_connection


def _video_from_artifact(artifact_path: Path) -> Path | None:
    if not artifact_path.exists():
        return None
    data = json.loads(artifact_path.read_text(encoding="utf-8"))

    archived = data.get("storage", {}).get("archived_video_file", "")
    if archived:
        p = Path(archived)
        if p.exists():
            return p

    planned = data.get("render", {}).get("planned_video_file", "")
    if planned:
        p = Path(planned)
        if p.exists():
            return p

    return None


def _artifact_from_job(job_id: int) -> Path | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT artifact_path, canonical_script_id FROM publish_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()

    if not row:
        return None

    if row["artifact_path"]:
        return Path(row["artifact_path"])

    out_dir = settings.OUTPUT_DIR
    if not out_dir.is_absolute():
        out_dir = settings.ROOT / out_dir
    return out_dir / f"episode_{row['canonical_script_id']}.json"


def _latest_artifact() -> Path | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT artifact_path, canonical_script_id FROM publish_jobs ORDER BY id DESC LIMIT 1"
        ).fetchone()

    if not row:
        return None

    if row["artifact_path"]:
        return Path(row["artifact_path"])

    out_dir = settings.OUTPUT_DIR
    if not out_dir.is_absolute():
        out_dir = settings.ROOT / out_dir
    return out_dir / f"episode_{row['canonical_script_id']}.json"


def open_video(video_path: Path) -> None:
    subprocess.run(["open", str(video_path)], check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview a generated video locally")
    parser.add_argument("--artifact", help="Path to episode artifact JSON")
    parser.add_argument("--job-id", type=int, help="Publish job id to preview")
    parser.add_argument("--latest", action="store_true", help="Preview latest publish job video")
    args = parser.parse_args()

    artifact_path: Path | None = None
    if args.artifact:
        artifact_path = Path(args.artifact)
    elif args.job_id is not None:
        artifact_path = _artifact_from_job(args.job_id)
    elif args.latest:
        artifact_path = _latest_artifact()

    if artifact_path is None:
        raise ValueError("Provide --artifact, --job-id, or --latest")

    video_path = _video_from_artifact(artifact_path)
    if video_path is None:
        raise FileNotFoundError(f"No previewable video found from artifact: {artifact_path}")

    print(f"Opening video: {video_path}")
    open_video(video_path)


if __name__ == "__main__":
    main()
