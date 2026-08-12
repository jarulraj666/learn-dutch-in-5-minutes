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


@router.get("/publish/instagram/{topic_id}/shorts")
def get_shorts(topic_id: str):
    from services.artifact import get_topic_media

    media = get_topic_media(topic_id)
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
