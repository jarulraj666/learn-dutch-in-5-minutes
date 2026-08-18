from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from services import pipeline_runner

router = APIRouter()


class RunRequest(BaseModel):
    level: str | None = None
    category: str | None = None
    topic_id: str | None = None
    count: int = 1
    no_upload: bool = False
    script_only: bool = False
    resume_checkpoint: str | None = None


class StageRequest(BaseModel):
    topic_id: str
    stages: list[int]
    # Legacy: artifact_path still accepted but ignored (topic_id is used)
    artifact_path: str | None = None


@router.post("/pipeline/run")
async def run_pipeline(req: RunRequest):
    from fastapi import HTTPException

    try:
        job = await pipeline_runner.start_pipeline(
            level=req.level,
            category=req.category,
            topic_id=req.topic_id,
            count=req.count,
            no_upload=req.no_upload,
            script_only=req.script_only,
            resume_checkpoint=req.resume_checkpoint,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return {"job_id": job.job_id, "started_at": job.started_at, "args": job.args}


@router.post("/pipeline/run-stages")
async def run_stages(req: StageRequest):
    from fastapi import HTTPException

    try:
        job = await pipeline_runner.start_pipeline(
            topic_id=req.topic_id,
            stages=req.stages,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return {"job_id": job.job_id, "started_at": job.started_at}


@router.post("/pipeline/abort/{job_id}")
async def abort_pipeline(job_id: str):
    ok = await pipeline_runner.abort_job(job_id)
    return {"ok": ok}


@router.get("/pipeline/jobs")
def list_jobs():
    return pipeline_runner.list_jobs()


@router.get("/pipeline/jobs/{job_id}")
def get_job(job_id: str):
    from fastapi import HTTPException

    job = pipeline_runner.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": job.job_id,
        "args": job.args,
        "started_at": job.started_at,
        "status": job.status,
        "exit_code": job.exit_code,
        "log": list(job.log_buffer),
    }


@router.get("/pipeline/logs/{job_id}")
async def stream_logs(job_id: str):
    return StreamingResponse(
        pipeline_runner.stream_logs(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
