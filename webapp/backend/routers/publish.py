from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from services import db as db_service

ROOT = Path(__file__).resolve().parent.parent.parent.parent
PYTHON = sys.executable

router = APIRouter()


class RescheduleRequest(BaseModel):
    scheduled_at: str  # ISO 8601


@router.get("/publish/queue")
def get_publish_queue(status: str | None = None):
    return db_service.list_publish_jobs(status=status)


@router.patch("/publish/{job_id}/reschedule")
def reschedule(job_id: int, req: RescheduleRequest):
    from fastapi import HTTPException

    ok = db_service.reschedule_publish_job(job_id, req.scheduled_at)
    if not ok:
        raise HTTPException(status_code=404, detail="Publish job not found")
    return {"ok": True}


@router.post("/publish/dry-run")
def publish_dry_run():
    result = subprocess.run(
        [PYTHON, "-m", "pipeline.publish.publish_pending", "--include-future"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    return {"stdout": result.stdout, "stderr": result.stderr, "exit_code": result.returncode}


@router.post("/publish/execute")
def publish_execute():
    result = subprocess.run(
        [PYTHON, "-m", "pipeline.publish.publish_pending", "--execute", "--include-future"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=300,
    )
    return {"stdout": result.stdout, "stderr": result.stderr, "exit_code": result.returncode}


@router.post("/publish/instagram/{topic_id}/shorts/{scene}/mark-uploaded")
async def mark_instagram_scene_uploaded(
    topic_id: str,
    scene: int,
    reel_id: str = "",
    permalink: str = "",
):
    """Manually mark a scene as uploaded to Instagram without actually uploading.

    Useful when the upload was done outside the pipeline.
    reel_id and permalink are optional — pass them if you have them.
    """
    import json as _json
    from fastapi import HTTPException
    from services.artifact import find_artifact, load_artifact
    from services.db import update_publish_job_artifact_json

    artifact_file = find_artifact(topic_id)
    if not artifact_file:
        raise HTTPException(status_code=404, detail="Artifact not found")
    artifact = load_artifact(artifact_file)
    if not artifact:
        raise HTTPException(status_code=500, detail="Could not load artifact")

    shorts = artifact.get("shorts", [])
    idx = next((i for i, s in enumerate(shorts) if str(s.get("scene")) == str(scene)), None)
    if idx is None:
        raise HTTPException(status_code=404, detail=f"Scene {scene} not found in shorts")

    ig_result = {
        "reel_id": reel_id or f"manual_{topic_id}_scene{scene}",
        "permalink": permalink or None,
        "manually_marked": True,
    }
    artifact["shorts"][idx]["instagram"] = ig_result
    artifact["shorts"][idx]["reel_id"] = ig_result["reel_id"]
    if permalink:
        artifact["shorts"][idx]["permalink"] = permalink

    artifact_file.write_text(_json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")
    update_publish_job_artifact_json(topic_id, artifact)
    return {"ok": True, "scene": scene, **ig_result}


@router.post("/publish/instagram/{topic_id}/shorts/{scene}/upload")
async def upload_instagram_scene(topic_id: str, scene: int):
    """Upload a single scene's short to Instagram immediately."""
    from fastapi import HTTPException
    from services.artifact import find_artifact, load_artifact
    from services.db import update_publish_job_artifact_json

    artifact_file = find_artifact(topic_id)
    if not artifact_file:
        raise HTTPException(status_code=404, detail="Artifact not found")
    artifact = load_artifact(artifact_file)
    if not artifact:
        raise HTTPException(status_code=500, detail="Could not load artifact")

    shorts = artifact.get("shorts", [])
    idx = next((i for i, s in enumerate(shorts) if str(s.get("scene")) == str(scene)), None)
    if idx is None:
        raise HTTPException(status_code=404, detail=f"Scene {scene} not found in shorts")

    short = shorts[idx]
    if short.get("instagram", {}).get("reel_id"):
        raise HTTPException(status_code=409, detail="Scene already uploaded to Instagram")

    from pipeline.stages import stage_upload_short_instagram
    try:
        ig_result = stage_upload_short_instagram(artifact, str(artifact_file), short)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    artifact["shorts"][idx]["instagram"] = ig_result
    # Back-compat: also set top-level reel_id so existing MediaTab still shows it
    artifact["shorts"][idx]["reel_id"] = ig_result.get("reel_id")
    artifact["shorts"][idx]["permalink"] = ig_result.get("permalink")
    artifact_file.write_text(
        __import__("json").dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    update_publish_job_artifact_json(topic_id, artifact)
    return ig_result


@router.post("/publish/instagram/{topic_id}/shorts/{scene}/schedule")
async def schedule_instagram_scene(topic_id: str, scene: int, scheduled_at: str):
    """Set (or clear) a scheduled publish time for a single scene.

    Pass scheduled_at as ISO 8601 (e.g. 2026-08-15T14:00:00).
    Pass scheduled_at="" to clear the schedule.
    """
    from fastapi import HTTPException
    from services.artifact import find_artifact, load_artifact
    from services.db import update_publish_job_artifact_json

    artifact_file = find_artifact(topic_id)
    if not artifact_file:
        raise HTTPException(status_code=404, detail="Artifact not found")
    artifact = load_artifact(artifact_file)
    if not artifact:
        raise HTTPException(status_code=500, detail="Could not load artifact")

    shorts = artifact.get("shorts", [])
    idx = next((i for i, s in enumerate(shorts) if str(s.get("scene")) == str(scene)), None)
    if idx is None:
        raise HTTPException(status_code=404, detail=f"Scene {scene} not found in shorts")

    artifact["shorts"][idx]["instagram_scheduled_at"] = scheduled_at or None
    artifact_file.write_text(
        __import__("json").dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    update_publish_job_artifact_json(topic_id, artifact)
    return {"ok": True, "scene": scene, "scheduled_at": scheduled_at or None}


@router.get("/publish/instagram/{topic_id}/shorts")
def get_shorts(topic_id: str):
    from services.artifact import get_topic_media
    from services import db as db_service

    artifact_json_str = db_service.get_artifact_json(topic_id)
    media = get_topic_media(topic_id, artifact_json_str=artifact_json_str)
    return media.get("shorts", [])


@router.post("/publish/instagram/{topic_id}/publish-draft")
def publish_instagram_draft(topic_id: str, container_id: str):
    import os
    import requests

    ig_user_id = os.getenv("INSTAGRAM_ACCOUNT_ID")
    ig_token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
    if not ig_user_id or not ig_token:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Instagram credentials not configured")

    resp = requests.post(
        f"https://graph.facebook.com/v21.0/{ig_user_id}/media_publish",
        params={"creation_id": container_id, "access_token": ig_token},
        timeout=30,
    )
    return resp.json()


# ---------------------------------------------------------------------------
# Facebook Reels endpoints
# ---------------------------------------------------------------------------

@router.post("/publish/facebook/{topic_id}/shorts/{scene}/upload")
async def upload_facebook_scene(topic_id: str, scene: int):
    """Upload a single scene's short to Facebook as a Reel immediately."""
    from fastapi import HTTPException
    from services.artifact import find_artifact, load_artifact
    from services.db import update_publish_job_artifact_json

    artifact_file = find_artifact(topic_id)
    if not artifact_file:
        raise HTTPException(status_code=404, detail="Artifact not found")
    artifact = load_artifact(artifact_file)
    if not artifact:
        raise HTTPException(status_code=500, detail="Could not load artifact")

    shorts = artifact.get("shorts", [])
    idx = next((i for i, s in enumerate(shorts) if str(s.get("scene")) == str(scene)), None)
    if idx is None:
        raise HTTPException(status_code=404, detail=f"Scene {scene} not found in shorts")
    if artifact["shorts"][idx].get("facebook", {}).get("post_id"):
        raise HTTPException(status_code=409, detail="Scene already uploaded to Facebook")

    from pipeline.stages import stage_upload_short_facebook
    try:
        fb_result = stage_upload_short_facebook(artifact, str(artifact_file), shorts[idx])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    artifact["shorts"][idx]["facebook"] = fb_result
    artifact_file.write_text(
        __import__("json").dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    update_publish_job_artifact_json(topic_id, artifact)
    return fb_result


@router.post("/publish/facebook/{topic_id}/shorts/{scene}/schedule")
async def schedule_facebook_scene(topic_id: str, scene: int, scheduled_at: str):
    """Set (or clear) a scheduled publish time for a Facebook Reel.

    Pass scheduled_at as UTC ISO 8601. Pass "" to clear.
    """
    from fastapi import HTTPException
    from services.artifact import find_artifact, load_artifact
    from services.db import update_publish_job_artifact_json

    artifact_file = find_artifact(topic_id)
    if not artifact_file:
        raise HTTPException(status_code=404, detail="Artifact not found")
    artifact = load_artifact(artifact_file)
    if not artifact:
        raise HTTPException(status_code=500, detail="Could not load artifact")

    shorts = artifact.get("shorts", [])
    idx = next((i for i, s in enumerate(shorts) if str(s.get("scene")) == str(scene)), None)
    if idx is None:
        raise HTTPException(status_code=404, detail=f"Scene {scene} not found in shorts")

    artifact["shorts"][idx]["facebook_scheduled_at"] = scheduled_at or None
    artifact_file.write_text(
        __import__("json").dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    update_publish_job_artifact_json(topic_id, artifact)
    return {"ok": True, "scene": scene, "scheduled_at": scheduled_at or None}


@router.post("/publish/facebook/{topic_id}/shorts/{scene}/mark-uploaded")
async def mark_facebook_scene_uploaded(
    topic_id: str, scene: int, post_id: str = "", video_id: str = "",
):
    """Manually mark a scene as uploaded to Facebook without actually uploading."""
    from fastapi import HTTPException
    from services.artifact import find_artifact, load_artifact
    from services.db import update_publish_job_artifact_json

    artifact_file = find_artifact(topic_id)
    if not artifact_file:
        raise HTTPException(status_code=404, detail="Artifact not found")
    artifact = load_artifact(artifact_file)
    if not artifact:
        raise HTTPException(status_code=500, detail="Could not load artifact")

    shorts = artifact.get("shorts", [])
    idx = next((i for i, s in enumerate(shorts) if str(s.get("scene")) == str(scene)), None)
    if idx is None:
        raise HTTPException(status_code=404, detail=f"Scene {scene} not found in shorts")

    fb_result = {
        "post_id": post_id or f"manual_{topic_id}_scene{scene}",
        "video_id": video_id or "",
        "manually_marked": True,
    }
    artifact["shorts"][idx]["facebook"] = fb_result
    artifact_file.write_text(
        __import__("json").dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    update_publish_job_artifact_json(topic_id, artifact)
    return {"ok": True, "scene": scene, **fb_result}
