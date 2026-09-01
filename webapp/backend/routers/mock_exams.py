from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, UploadFile
from pydantic import BaseModel

from services import pipeline_runner

ROOT = Path(__file__).resolve().parent.parent.parent.parent

router = APIRouter()


@router.get("/mock-exams")
def list_mock_exams(section: str | None = None):
    from pipeline.core.store_mock_exam import list_mock_exam_jobs
    return list_mock_exam_jobs(section)


@router.get("/mock-exams/{exam_id}")
def get_mock_exam(exam_id: str):
    from pipeline.core.store_mock_exam import load_mock_exam_job

    job = load_mock_exam_job(exam_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"No job found for {exam_id}")
    return job


class RunRequest(BaseModel):
    section: str | None = None
    exam_number: int | None = None
    stage: str  # content | media | export


@router.post("/mock-exams/run")
async def run_mock_exam_job(req: RunRequest):
    if req.stage not in ("content", "media", "export"):
        raise HTTPException(status_code=400, detail="stage must be one of content|media|export")

    cmd = ["python", "-m", "pipeline.tools.generate_and_export_mock_exams", "--stage", req.stage]
    if req.section:
        cmd += ["--section", req.section]
    if req.exam_number:
        cmd += ["--exam-number", str(req.exam_number)]

    job = await pipeline_runner.start_custom_job(cmd)
    return {"job_id": job.job_id, "started_at": job.started_at, "args": job.args}


@router.post("/mock-exams/{exam_id}/upload-image")
async def upload_mock_exam_image(
    exam_id: str,
    passage_id: str = Form(...),
    file: UploadFile = Form(...),
):
    """Manually replace a passage's image, mirroring media.py's upload-scene-image."""
    from pipeline.core.store_mock_exam import load_mock_exam_job, save_mock_exam_job

    job = load_mock_exam_job(exam_id)
    if not job or not job.get("artifact"):
        raise HTTPException(status_code=404, detail=f"No staged content for {exam_id}")

    artifact = job["artifact"]
    passage = next((p for p in artifact.get("passages", []) if p["id"] == passage_id), None)
    if not passage:
        raise HTTPException(status_code=404, detail=f"Passage {passage_id} not found in {exam_id}")

    suffix = Path(file.filename or "").suffix.lower() or ".png"
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(status_code=400, detail="Unsupported image format")

    content = await file.read()
    dest_dir = ROOT / "output" / "mock_exams" / "visuals" / exam_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{passage_id}{suffix}"
    dest.write_bytes(content)
    rel = str(dest.relative_to(ROOT))

    passage["media_urls"] = [
        u for u in passage.get("media_urls", []) if u.get("type") != "image"
    ] + [{"type": "image", "url": rel}]

    save_mock_exam_job(exam_id, job["section"], job["exam_number"], job["level"], artifact, job["status"])
    return {"path": rel, "passage_id": passage_id}


@router.post("/mock-exams/{exam_id}/upload-option-image")
async def upload_mock_exam_option_image(
    exam_id: str,
    question_id: str = Form(...),
    option_index: int = Form(...),
    file: UploadFile = Form(...),
):
    """Manually upload a photo for one option of a rare picture-choice MC question."""
    from pipeline.core.store_mock_exam import load_mock_exam_job, save_mock_exam_job

    job = load_mock_exam_job(exam_id)
    if not job or not job.get("artifact"):
        raise HTTPException(status_code=404, detail=f"No staged content for {exam_id}")

    artifact = job["artifact"]
    question = next((q for q in artifact.get("questions", []) if q["id"] == question_id), None)
    if not question:
        raise HTTPException(status_code=404, detail=f"Question {question_id} not found in {exam_id}")

    prompts = question.get("option_image_prompts")
    if not prompts or not (0 <= option_index < len(prompts)):
        raise HTTPException(status_code=400, detail="Question has no such picture-choice option")

    suffix = Path(file.filename or "").suffix.lower() or ".png"
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(status_code=400, detail="Unsupported image format")

    content = await file.read()
    dest_dir = ROOT / "output" / "mock_exams" / "visuals" / exam_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{question_id}-option{option_index}{suffix}"
    dest.write_bytes(content)
    rel = str(dest.relative_to(ROOT))

    urls = question.get("option_media_urls") or [None] * len(prompts)
    urls[option_index] = rel
    question["option_media_urls"] = urls

    save_mock_exam_job(exam_id, job["section"], job["exam_number"], job["level"], artifact, job["status"])
    return {"path": rel, "question_id": question_id, "option_index": option_index}
