from fastapi import APIRouter
from services import db as db_service

router = APIRouter()


@router.get("/topics")
def list_topics(
    level: str | None = None,
    category: str | None = None,
    status: str | None = None,
    search: str | None = None,
):
    return db_service.list_topics(level=level, category=category, status=status, search=search)


@router.get("/topics/{topic_id}")
def get_topic(topic_id: str):
    from fastapi import HTTPException
    from services.artifact import get_topic_media
    import json

    topic = db_service.get_topic(topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    topic["media"] = get_topic_media(
        topic_id,
        artifact_path=topic.get("artifact_path"),
        artifact_json_str=topic.get("artifact_json"),
    )

    # Fall back to artifact JSON for youtube_video_id if publish_jobs column is NULL
    if not topic.get("youtube_video_id") and topic.get("artifact_json"):
        try:
            artifact = json.loads(topic["artifact_json"])
            vid = (artifact.get("youtube") or {}).get("video_id")
            if vid:
                topic["youtube_video_id"] = vid
        except Exception:
            pass

    return topic


@router.patch("/topics/{topic_id}/status")
def reset_topic_status(topic_id: str, status: str = "pending"):
    from fastapi import HTTPException

    allowed = {"pending", "generated", "ready_to_publish", "done"}
    if status not in allowed:
        raise HTTPException(status_code=400, detail=f"status must be one of {allowed}")
    ok = db_service.update_topic_status(topic_id, status)
    if not ok:
        raise HTTPException(status_code=404, detail="Topic not found")
    return {"ok": True, "status": status}


@router.post("/topics/{topic_id}/sync-artifact")
def sync_artifact(topic_id: str):
    """Re-read the artifact JSON from disk and update publish_jobs.artifact_json."""
    from fastapi import HTTPException
    from services.artifact import find_artifact, load_artifact

    artifact_file = find_artifact(topic_id)
    if not artifact_file:
        raise HTTPException(status_code=404, detail=f"No artifact file found for topic {topic_id}")

    artifact = load_artifact(artifact_file)
    if not artifact:
        raise HTTPException(status_code=500, detail="Could not load artifact from disk")

    ok = db_service.update_publish_job_artifact_json(topic_id, artifact)
    return {"ok": True, "synced": ok, "artifact_path": str(artifact_file)}


@router.get("/stats")
def get_stats():
    return db_service.get_stats()
