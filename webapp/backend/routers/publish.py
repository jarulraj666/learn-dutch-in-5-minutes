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


class ReelScheduleRequest(BaseModel):
    scheduled_at: str  # ISO 8601 — set to schedule, or empty string to clear


@router.get("/publish/queue")
def get_publish_queue(status: str | None = None):
    return db_service.list_publish_jobs(status=status)


@router.get("/publish/platform-status")
def get_platform_status():
    """Aggregate publish status across YouTube, YT Shorts, Instagram, TikTok, Facebook."""
    import json as _json
    from services.db import get_connection

    sql = """
        SELECT
            t.id AS topic_id,
            COALESCE(cs.title, t.title_hint) AS title,
            t.level,
            t.category,
            pj.youtube_video_id,
            pj.status AS yt_status,
            pj.scheduled_at,
            pj.published_at,
            pj.artifact_json
        FROM topics t
        LEFT JOIN canonical_scripts cs ON cs.topic_id = t.id
            AND cs.id = (SELECT MAX(id) FROM canonical_scripts WHERE topic_id = t.id)
        LEFT JOIN publish_jobs pj ON pj.canonical_script_id = cs.id
            AND pj.id = (SELECT MAX(id) FROM publish_jobs WHERE canonical_script_id = cs.id)
        WHERE cs.id IS NOT NULL
        ORDER BY
            CASE WHEN pj.scheduled_at IS NULL THEN 1 ELSE 0 END,
            pj.scheduled_at DESC
    """

    with get_connection() as conn:
        rows = conn.execute(sql).fetchall()

    counts: dict = {
        "youtube":        {"published": 0, "scheduled": 0, "pending": 0},
        "youtube_shorts": {"published": 0, "scheduled": 0, "pending": 0},
        "instagram":      {"published": 0, "scheduled": 0, "pending": 0},
        "tiktok":         {"published": 0, "scheduled": 0, "pending": 0},
        "facebook":       {"published": 0, "scheduled": 0, "pending": 0},
    }
    items = []

    for row in rows:
        artifact: dict = {}
        if row["artifact_json"]:
            try:
                artifact = _json.loads(row["artifact_json"])
            except Exception:
                pass

        shorts_raw: list[dict] = artifact.get("shorts") or []

        # ── YouTube main video ───────────────────────────────────────────────
        if row["youtube_video_id"]:
            counts["youtube"]["published"] += 1
        elif row["scheduled_at"]:
            counts["youtube"]["scheduled"] += 1
        else:
            counts["youtube"]["pending"] += 1

        # ── Shorts (one entry per scene) ─────────────────────────────────────
        shorts_out = []
        for s in shorts_raw:
            yt_short = s.get("youtube") or {}
            ig = s.get("instagram") or {}
            tt = s.get("tiktok") or {}
            fb = s.get("facebook") or {}

            has_video = bool(s.get("video_file"))

            # YT Shorts
            if yt_short.get("short_video_id"):
                counts["youtube_shorts"]["published"] += 1
            elif has_video:
                counts["youtube_shorts"]["pending"] += 1

            # Instagram
            if ig.get("reel_id"):
                counts["instagram"]["published"] += 1
            elif s.get("instagram_scheduled_at"):
                counts["instagram"]["scheduled"] += 1
            elif has_video:
                counts["instagram"]["pending"] += 1

            # TikTok
            if tt.get("publish_id"):
                counts["tiktok"]["published"] += 1
            elif s.get("tiktok_scheduled_at"):
                counts["tiktok"]["scheduled"] += 1
            elif has_video:
                counts["tiktok"]["pending"] += 1

            # Facebook
            if fb.get("post_id"):
                counts["facebook"]["published"] += 1
            elif s.get("facebook_scheduled_at"):
                counts["facebook"]["scheduled"] += 1
            elif has_video:
                counts["facebook"]["pending"] += 1

            yt_id = yt_short.get("short_video_id")
            ig_id = ig.get("reel_id")

            shorts_out.append({
                "scene": s.get("scene"),
                "description": s.get("description"),
                "video_file": s.get("video_file"),
                "reel_scheduled_at": s.get("reel_scheduled_at"),
                "youtube": {
                    "short_video_id": yt_id,
                    "url": f"https://youtube.com/shorts/{yt_id}" if yt_id else None,
                    "playlist_name": yt_short.get("playlist_name"),
                } if yt_short else None,
                "instagram": {
                    "reel_id": ig_id,
                    "permalink": ig.get("permalink"),
                    "manually_marked": ig.get("manually_marked", False),
                    "scheduled_at": s.get("instagram_scheduled_at"),
                } if ig or s.get("instagram_scheduled_at") else None,
                "tiktok": {
                    "publish_id": tt.get("publish_id"),
                    "scheduled_at": s.get("tiktok_scheduled_at"),
                } if tt or s.get("tiktok_scheduled_at") else None,
                "facebook": {
                    "post_id": fb.get("post_id"),
                    "video_id": fb.get("video_id"),
                    "manually_marked": fb.get("manually_marked", False),
                    "scheduled_at": s.get("facebook_scheduled_at"),
                } if fb or s.get("facebook_scheduled_at") else None,
            })

        items.append({
            "topic_id": row["topic_id"],
            "title": row["title"],
            "level": row["level"],
            "category": row["category"],
            "youtube": {
                "video_id": row["youtube_video_id"],
                "url": f"https://youtube.com/watch?v={row['youtube_video_id']}" if row["youtube_video_id"] else None,
                "status": row["yt_status"] or "pending",
                "scheduled_at": row["scheduled_at"],
                "published_at": row["published_at"],
            },
            "shorts": shorts_out,
        })

    return {"counts": counts, "items": items}


@router.patch("/publish/{job_id}/reschedule")
def reschedule(job_id: int, req: RescheduleRequest):
    from fastapi import HTTPException

    ok = db_service.reschedule_publish_job(job_id, req.scheduled_at)
    if not ok:
        raise HTTPException(status_code=404, detail="Publish job not found")
    return {"ok": True}


@router.post("/publish/youtube/{topic_id}/mark-uploaded")
async def mark_youtube_uploaded(topic_id: str, video_id: str):
    """Manually set the YouTube video ID for a topic and mark it uploaded.

    Use this when the video was uploaded outside the pipeline.
    """
    from fastapi import HTTPException
    from services.artifact import load_artifact_from_db, save_artifact
    from services.db import get_connection

    artifact = load_artifact_from_db(topic_id)
    if not artifact:
        raise HTTPException(status_code=404, detail=f"Artifact not found for topic_id={topic_id}")

    artifact.setdefault("youtube", {})["video_id"] = video_id
    save_artifact(topic_id, artifact)

    # Update publish_jobs table
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE publish_jobs SET youtube_video_id = ?, status = 'uploaded'
            WHERE id = (
                SELECT pj.id FROM canonical_scripts cs
                JOIN publish_jobs pj ON pj.canonical_script_id = cs.id
                WHERE cs.topic_id = ?
                ORDER BY pj.id DESC LIMIT 1
            )
            """,
            [video_id, topic_id],
        )

    return {"ok": True, "topic_id": topic_id, "video_id": video_id}


@router.patch("/publish/reels/{topic_id}/scene/{scene}/schedule")
def schedule_reel(topic_id: str, scene: int, req: ReelScheduleRequest):
    """Set or clear the manual schedule for a single reel scene.

    Pass ``scheduled_at`` as an ISO 8601 string to schedule it.
    Pass an empty string to clear (unschedule).
    """
    import json as _json
    from fastapi import HTTPException
    from services.artifact import load_artifact_from_db, save_artifact

    artifact = load_artifact_from_db(topic_id)
    if not artifact:
        raise HTTPException(status_code=404, detail=f"Artifact not found for topic_id={topic_id}")

    shorts: list[dict] = artifact.get("shorts", [])
    match = next((i for i, s in enumerate(shorts) if str(s.get("scene")) == str(scene)), None)
    if match is None:
        raise HTTPException(status_code=404, detail=f"Scene {scene} not found in shorts list")

    if req.scheduled_at:
        artifact["shorts"][match]["reel_scheduled_at"] = req.scheduled_at
        artifact["shorts"][match]["instagram_scheduled_at"] = req.scheduled_at
        artifact["shorts"][match]["facebook_scheduled_at"] = req.scheduled_at
        artifact["shorts"][match]["tiktok_scheduled_at"] = req.scheduled_at
    else:
        for field in ("reel_scheduled_at", "instagram_scheduled_at", "facebook_scheduled_at", "tiktok_scheduled_at"):
            artifact["shorts"][match].pop(field, None)

    save_artifact(topic_id, artifact)
    return {"ok": True, "scene": scene, "reel_scheduled_at": req.scheduled_at or None}


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
    from services.artifact import load_artifact_from_db, save_artifact

    artifact = load_artifact_from_db(topic_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

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

    save_artifact(topic_id, artifact)
    return {"ok": True, "scene": scene, **ig_result}


@router.post("/publish/instagram/{topic_id}/shorts/{scene}/upload")
async def upload_instagram_scene(topic_id: str, scene: int):
    """Upload a single scene's short to Instagram immediately."""
    from fastapi import HTTPException
    from services.artifact import load_artifact_from_db, save_artifact

    artifact = load_artifact_from_db(topic_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

    shorts = artifact.get("shorts", [])
    idx = next((i for i, s in enumerate(shorts) if str(s.get("scene")) == str(scene)), None)
    if idx is None:
        raise HTTPException(status_code=404, detail=f"Scene {scene} not found in shorts")

    short = shorts[idx]
    if short.get("instagram", {}).get("reel_id"):
        raise HTTPException(status_code=409, detail="Scene already uploaded to Instagram")

    from pipeline.stages import stage_upload_short_instagram
    artifact_file = save_artifact(topic_id, artifact)  # ensure disk copy exists for upload stage
    try:
        ig_result = stage_upload_short_instagram(artifact, short)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    artifact["shorts"][idx]["instagram"] = ig_result
    artifact["shorts"][idx]["reel_id"] = ig_result.get("reel_id")
    artifact["shorts"][idx]["permalink"] = ig_result.get("permalink")
    save_artifact(topic_id, artifact)
    return ig_result


@router.post("/publish/instagram/{topic_id}/shorts/{scene}/schedule")
async def schedule_instagram_scene(topic_id: str, scene: int, scheduled_at: str):
    """Set (or clear) a scheduled publish time for a single scene.

    Pass scheduled_at as ISO 8601 (e.g. 2026-08-15T14:00:00).
    Pass scheduled_at="" to clear the schedule.
    """
    from fastapi import HTTPException
    from services.artifact import load_artifact_from_db, save_artifact

    artifact = load_artifact_from_db(topic_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

    shorts = artifact.get("shorts", [])
    idx = next((i for i, s in enumerate(shorts) if str(s.get("scene")) == str(scene)), None)
    if idx is None:
        raise HTTPException(status_code=404, detail=f"Scene {scene} not found in shorts")

    artifact["shorts"][idx]["instagram_scheduled_at"] = scheduled_at or None
    save_artifact(topic_id, artifact)
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
    from services.artifact import load_artifact_from_db, save_artifact

    artifact = load_artifact_from_db(topic_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

    shorts = artifact.get("shorts", [])
    idx = next((i for i, s in enumerate(shorts) if str(s.get("scene")) == str(scene)), None)
    if idx is None:
        raise HTTPException(status_code=404, detail=f"Scene {scene} not found in shorts")
    if artifact["shorts"][idx].get("facebook", {}).get("post_id"):
        raise HTTPException(status_code=409, detail="Scene already uploaded to Facebook")

    from pipeline.stages import stage_upload_short_facebook
    artifact_file = save_artifact(topic_id, artifact)
    try:
        fb_result = stage_upload_short_facebook(artifact, shorts[idx])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    artifact["shorts"][idx]["facebook"] = fb_result
    save_artifact(topic_id, artifact)
    return fb_result


@router.post("/publish/facebook/{topic_id}/shorts/{scene}/schedule")
async def schedule_facebook_scene(topic_id: str, scene: int, scheduled_at: str):
    """Set (or clear) a scheduled publish time for a Facebook Reel.

    Pass scheduled_at as UTC ISO 8601. Pass "" to clear.
    """
    from fastapi import HTTPException
    from services.artifact import load_artifact_from_db, save_artifact

    artifact = load_artifact_from_db(topic_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

    shorts = artifact.get("shorts", [])
    idx = next((i for i, s in enumerate(shorts) if str(s.get("scene")) == str(scene)), None)
    if idx is None:
        raise HTTPException(status_code=404, detail=f"Scene {scene} not found in shorts")

    artifact["shorts"][idx]["facebook_scheduled_at"] = scheduled_at or None
    save_artifact(topic_id, artifact)
    return {"ok": True, "scene": scene, "scheduled_at": scheduled_at or None}


@router.post("/publish/facebook/{topic_id}/shorts/{scene}/mark-uploaded")
async def mark_facebook_scene_uploaded(
    topic_id: str, scene: int, post_id: str = "", video_id: str = "",
):
    """Manually mark a scene as uploaded to Facebook without actually uploading."""
    from fastapi import HTTPException
    from services.artifact import load_artifact_from_db, save_artifact

    artifact = load_artifact_from_db(topic_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

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
    save_artifact(topic_id, artifact)
    return {"ok": True, "scene": scene, **fb_result}


# ---------------------------------------------------------------------------
# TikTok endpoints
# ---------------------------------------------------------------------------

@router.post("/publish/tiktok/{topic_id}/shorts/{scene}/upload")
async def upload_tiktok_scene(topic_id: str, scene: int):
    """Upload a single scene's short to TikTok immediately."""
    from fastapi import HTTPException
    from services.artifact import load_artifact_from_db, save_artifact

    artifact = load_artifact_from_db(topic_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

    shorts = artifact.get("shorts", [])
    idx = next((i for i, s in enumerate(shorts) if str(s.get("scene")) == str(scene)), None)
    if idx is None:
        raise HTTPException(status_code=404, detail=f"Scene {scene} not found in shorts")
    if artifact["shorts"][idx].get("tiktok", {}).get("publish_id"):
        raise HTTPException(status_code=409, detail="Scene already uploaded to TikTok")

    from pipeline.stages import stage_upload_short_tiktok
    try:
        tt_result = stage_upload_short_tiktok(artifact, shorts[idx])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    artifact["shorts"][idx]["tiktok"] = tt_result
    save_artifact(topic_id, artifact)
    return tt_result


@router.post("/publish/tiktok/{topic_id}/shorts/{scene}/schedule")
async def schedule_tiktok_scene(topic_id: str, scene: int, scheduled_at: str):
    """Set (or clear) a scheduled publish time for a TikTok Short.

    Pass scheduled_at as UTC ISO 8601. Pass "" to clear.
    """
    from fastapi import HTTPException
    from services.artifact import load_artifact_from_db, save_artifact

    artifact = load_artifact_from_db(topic_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

    shorts = artifact.get("shorts", [])
    idx = next((i for i, s in enumerate(shorts) if str(s.get("scene")) == str(scene)), None)
    if idx is None:
        raise HTTPException(status_code=404, detail=f"Scene {scene} not found in shorts")

    artifact["shorts"][idx]["tiktok_scheduled_at"] = scheduled_at or None
    save_artifact(topic_id, artifact)
    return {"ok": True, "scene": scene, "scheduled_at": scheduled_at or None}


@router.post("/publish/tiktok/{topic_id}/shorts/{scene}/mark-uploaded")
async def mark_tiktok_scene_uploaded(
    topic_id: str, scene: int, publish_id: str = "",
):
    """Manually mark a scene as uploaded to TikTok without actually uploading."""
    from fastapi import HTTPException
    from services.artifact import load_artifact_from_db, save_artifact

    artifact = load_artifact_from_db(topic_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

    shorts = artifact.get("shorts", [])
    idx = next((i for i, s in enumerate(shorts) if str(s.get("scene")) == str(scene)), None)
    if idx is None:
        raise HTTPException(status_code=404, detail=f"Scene {scene} not found in shorts")

    tt_result = {
        "publish_id": publish_id or f"manual_{topic_id}_scene{scene}",
        "manually_marked": True,
    }
    artifact["shorts"][idx]["tiktok"] = tt_result
    save_artifact(topic_id, artifact)
    return {"ok": True, "scene": scene, **tt_result}
