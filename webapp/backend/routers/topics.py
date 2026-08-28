from fastapi import APIRouter
from pydantic import BaseModel
from services import db as db_service

router = APIRouter()


class ScriptUpdateRequest(BaseModel):
    script: dict


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

    artifact = None
    if topic.get("artifact_json"):
        try:
            artifact = json.loads(topic["artifact_json"])
        except Exception:
            artifact = None

    # Fall back to artifact JSON for youtube_video_id if publish_jobs column is NULL
    if not topic.get("youtube_video_id") and artifact:
        vid = (artifact.get("youtube") or {}).get("video_id")
        if vid:
            topic["youtube_video_id"] = vid

    # Surface expressive-tag dialogue produced by stage 2 for pipeline status + UI.
    topic["tts_dialogue"] = artifact.get("tts_dialogue", []) if artifact else []

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


@router.put("/topics/{topic_id}/script")
def update_topic_script(topic_id: str, req: ScriptUpdateRequest):
    from fastapi import HTTPException

    script = req.script
    if not isinstance(script, dict):
        raise HTTPException(status_code=400, detail="script must be a JSON object")
    dialogue = script.get("dialogue") or script.get("script")
    if not isinstance(dialogue, list) or len(dialogue) == 0:
        raise HTTPException(status_code=400, detail="script must contain non-empty dialogue or script array")

    ok = db_service.update_topic_script(topic_id, script)
    if not ok:
        raise HTTPException(status_code=404, detail="Topic or canonical script not found")
    return {"ok": True}


@router.get("/stats")
def get_stats():
    return db_service.get_stats()
