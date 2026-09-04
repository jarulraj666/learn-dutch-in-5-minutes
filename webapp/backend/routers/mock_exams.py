from __future__ import annotations

import asyncio
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
    stage: str  # content | media | question_audio | export


@router.post("/mock-exams/run")
async def run_mock_exam_job(req: RunRequest):
    if req.stage not in ("content", "media", "question_audio", "export"):
        raise HTTPException(status_code=400, detail="stage must be one of content|media|question_audio|export")

    cmd = ["python", "-m", "pipeline.tools.generate_and_export_mock_exams", "--stage", req.stage]
    if req.section:
        cmd += ["--section", req.section]
    if req.exam_number:
        cmd += ["--exam-number", str(req.exam_number)]

    job = await pipeline_runner.start_custom_job(cmd)
    return {"job_id": job.job_id, "started_at": job.started_at, "args": job.args}


@router.post("/mock-exams/{exam_id}/refresh-image-prompt")
async def refresh_mock_exam_image_prompt(
    exam_id: str,
    passage_id: str = Form(...),
):
    """Rebuild one passage's image prompt without changing its content or media."""
    from pipeline.generate.generate_mock_exam import _build_exam_image_prompt
    from pipeline.core.store_mock_exam import load_mock_exam_job, save_mock_exam_job

    job = load_mock_exam_job(exam_id)
    if not job or not job.get("artifact"):
        raise HTTPException(status_code=404, detail=f"No staged content for {exam_id}")

    artifact = job["artifact"]
    passage = next((p for p in artifact.get("passages", []) if p["id"] == passage_id), None)
    if not passage:
        raise HTTPException(status_code=404, detail=f"Passage {passage_id} not found in {exam_id}")

    scene_description = passage.get("scene_description") or passage.get("content_nl") or passage.get("title")
    if not scene_description:
        raise HTTPException(status_code=400, detail="Passage has no scene description or content")

    if passage.get("passage_type") in {"two_picture", "three_picture"}:
        scenes = [scene.strip() for scene in scene_description.split("|") if scene.strip()]
        passage["image_prompt"] = [_build_exam_image_prompt(scene) for scene in scenes]
    else:
        passage["image_prompt"] = [_build_exam_image_prompt(scene_description, passage.get("presenter_gender"))]

    save_mock_exam_job(exam_id, job["section"], job["exam_number"], job["level"], artifact, job["status"])
    return {"passage_id": passage_id, "image_prompt": passage["image_prompt"]}


@router.post("/mock-exams/{exam_id}/upload-image")
async def upload_mock_exam_image(
    exam_id: str,
    passage_id: str = Form(...),
    image_index: int = Form(0),
    file: UploadFile = Form(...),
):
    """Upload or replace one image panel for a mock-exam passage."""
    from pipeline.core.store_mock_exam import load_mock_exam_job, save_mock_exam_job

    job = load_mock_exam_job(exam_id)
    if not job or not job.get("artifact"):
        raise HTTPException(status_code=404, detail=f"No staged content for {exam_id}")

    artifact = job["artifact"]
    passage = next((p for p in artifact.get("passages", []) if p["id"] == passage_id), None)
    if not passage:
        raise HTTPException(status_code=404, detail=f"Passage {passage_id} not found in {exam_id}")

    expected_images = {"one_picture": 1, "two_picture": 2, "three_picture": 3}.get(passage.get("passage_type"), 1)
    if not 0 <= image_index < expected_images:
        raise HTTPException(status_code=400, detail=f"Image index must be between 0 and {expected_images - 1}")

    suffix = Path(file.filename or "").suffix.lower() or ".png"
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(status_code=400, detail="Unsupported image format")

    content = await file.read()
    dest_dir = ROOT / "output" / "mock_exams" / "visuals" / exam_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    suffix_name = "" if expected_images == 1 else f"-panel-{image_index + 1}"
    dest = dest_dir / f"{passage_id}{suffix_name}{suffix}"
    dest.write_bytes(content)
    rel = str(dest.relative_to(ROOT))

    non_images = [u for u in passage.get("media_urls", []) if u.get("type") != "image"]
    images = [u for u in passage.get("media_urls", []) if u.get("type") == "image"]
    while len(images) <= image_index:
        images.append({"type": "image", "url": ""})
    images[image_index] = {"type": "image", "url": rel}
    passage["media_urls"] = non_images + [image for image in images if image["url"]]

    save_mock_exam_job(exam_id, job["section"], job["exam_number"], job["level"], artifact, job["status"])
    return {"path": rel, "passage_id": passage_id}


@router.post("/mock-exams/{exam_id}/upload-audio")
async def upload_mock_exam_audio(
    exam_id: str,
    passage_id: str = Form(...),
    file: UploadFile = Form(...),
):
    """Upload narration/dialogue audio for a mock-exam passage."""
    from pipeline.core.store_mock_exam import load_mock_exam_job, save_mock_exam_job

    job = load_mock_exam_job(exam_id)
    if not job or not job.get("artifact"):
        raise HTTPException(status_code=404, detail=f"No staged content for {exam_id}")

    artifact = job["artifact"]
    passage = next((p for p in artifact.get("passages", []) if p["id"] == passage_id), None)
    if not passage:
        raise HTTPException(status_code=404, detail=f"Passage {passage_id} not found in {exam_id}")

    suffix = Path(file.filename or "").suffix.lower() or ".mp3"
    if suffix not in {".mp3", ".wav", ".m4a", ".ogg"}:
        raise HTTPException(status_code=400, detail="Unsupported audio format")

    content = await file.read()
    dest_dir = ROOT / "output" / "mock_exams" / "audio" / exam_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{passage_id}{suffix}"
    dest.write_bytes(content)
    rel = str(dest.relative_to(ROOT))

    passage["media_urls"] = [
        url for url in passage.get("media_urls", []) if url.get("type") != "audio"
    ] + [{"type": "audio", "url": rel}]

    save_mock_exam_job(exam_id, job["section"], job["exam_number"], job["level"], artifact, job["status"])
    return {"path": rel, "passage_id": passage_id}


@router.post("/mock-exams/{exam_id}/upload-video")
async def upload_mock_exam_video(
    exam_id: str,
    passage_id: str = Form(...),
    file: UploadFile = Form(...),
):
    """Upload the sole learner-facing media file for a speaking video passage."""
    from pipeline.core.store_mock_exam import load_mock_exam_job, save_mock_exam_job

    job = load_mock_exam_job(exam_id)
    if not job or not job.get("artifact"):
        raise HTTPException(status_code=404, detail=f"No staged content for {exam_id}")

    artifact = job["artifact"]
    passage = next((p for p in artifact.get("passages", []) if p["id"] == passage_id), None)
    if not passage or passage.get("passage_type") != "video":
        raise HTTPException(status_code=404, detail=f"Video passage {passage_id} not found in {exam_id}")

    suffix = Path(file.filename or "").suffix.lower() or ".mp4"
    if suffix not in {".mp4", ".webm", ".mov", ".m4v"}:
        raise HTTPException(status_code=400, detail="Unsupported video format")

    content = await file.read()
    dest_dir = ROOT / "output" / "mock_exams" / "video" / exam_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{passage_id}{suffix}"
    dest.write_bytes(content)
    rel = str(dest.relative_to(ROOT))

    # Export consumes media_urls verbatim, so retain only this selected video for learners.
    passage["media_urls"] = [{"type": "video", "url": rel}]
    save_mock_exam_job(exam_id, job["section"], job["exam_number"], job["level"], artifact, job["status"])
    return {"path": rel, "passage_id": passage_id}


@router.post("/mock-exams/{exam_id}/generate-voice")
async def generate_mock_exam_voice(
    exam_id: str,
    passage_id: str = Form(...),
):
    """Generate a speaking-video voice with ElevenLabs using its presenter gender."""
    from pipeline import settings
    from pipeline.clients.elevenlabs_tts_client import create_elevenlabs_client
    from pipeline.core.store_mock_exam import load_mock_exam_job, save_mock_exam_job

    job = load_mock_exam_job(exam_id)
    if not job or not job.get("artifact"):
        raise HTTPException(status_code=404, detail=f"No staged content for {exam_id}")

    artifact = job["artifact"]
    passage = next((p for p in artifact.get("passages", []) if p["id"] == passage_id), None)
    if not passage or passage.get("passage_type") != "video":
        raise HTTPException(status_code=404, detail=f"Video passage {passage_id} not found in {exam_id}")
    if not passage.get("content_nl"):
        raise HTTPException(status_code=400, detail="The video passage has no voice script")
    if not settings.ELEVENLABS_API_KEY:
        raise HTTPException(status_code=503, detail="ELEVENLABS_API_KEY is not configured")

    presenter_gender = passage.get("presenter_gender")
    if presenter_gender not in {"female", "male"}:
        presenter_gender = "female"
    client = create_elevenlabs_client(settings.ELEVENLABS_API_KEY)
    if not client:
        raise HTTPException(status_code=503, detail="Could not initialize ElevenLabs")

    dest_dir = ROOT / "output" / "mock_exams" / "audio" / exam_id
    output_path = dest_dir / f"{passage_id}.wav"
    generated = await asyncio.to_thread(
        client.generate_dialogue_audio,
        [{"speaker": "Presenter", "line": passage["content_nl"]}],
        str(output_path),
        "A1A2",
        "dialogue",
        {"Presenter": presenter_gender},
    )
    if not generated:
        raise HTTPException(status_code=502, detail="ElevenLabs could not generate the voice")

    rel = str(output_path.relative_to(ROOT))
    passage["media_urls"] = [
        url for url in passage.get("media_urls", []) if url.get("type") != "audio"
    ] + [{"type": "audio", "url": rel}]
    save_mock_exam_job(exam_id, job["section"], job["exam_number"], job["level"], artifact, job["status"])
    return {"path": rel, "passage_id": passage_id, "presenter_gender": presenter_gender}


@router.post("/mock-exams/{exam_id}/generate-passage-audio")
async def generate_mock_exam_passage_audio(
    exam_id: str,
    passage_id: str = Form(...),
):
    """Generate audio for one picture-task instruction without changing its content or image."""
    from pipeline import settings
    from pipeline.generate.generate_mock_exam import _synthesize_passage_audio, _with_part_two_reminder
    from pipeline.core.store_mock_exam import load_mock_exam_job, save_mock_exam_job

    job = load_mock_exam_job(exam_id)
    if not job or not job.get("artifact"):
        raise HTTPException(status_code=404, detail=f"No staged content for {exam_id}")

    artifact = job["artifact"]
    passage = next((p for p in artifact.get("passages", []) if p["id"] == passage_id), None)
    if not passage or passage.get("passage_type") not in {"one_picture", "two_picture", "three_picture"}:
        raise HTTPException(status_code=404, detail=f"Picture passage {passage_id} not found in {exam_id}")
    question = next((q for q in artifact.get("questions", []) if q.get("passage_id") == passage_id), None)
    if not question or not question.get("question_text"):
        raise HTTPException(status_code=400, detail="Passage has no audio script")
    if not settings.TTS_PROVIDER:
        raise HTTPException(status_code=503, detail="TTS_PROVIDER is not configured")

    audio_path = ROOT / "output" / "mock_exams" / "audio" / exam_id / f"{passage_id}.wav"
    script = _with_part_two_reminder(question["question_text"])
    audio_passage = {**passage, "content_nl": script}
    generated = await asyncio.to_thread(_synthesize_passage_audio, audio_passage, audio_path)
    if not generated:
        raise HTTPException(status_code=502, detail="Could not generate passage audio")

    rel = str(audio_path.relative_to(ROOT))
    passage["media_urls"] = [
        url for url in passage.get("media_urls", []) if url.get("type") != "audio"
    ] + [{"type": "audio", "url": rel}]
    save_mock_exam_job(exam_id, job["section"], job["exam_number"], job["level"], artifact, job["status"])
    return {"path": rel, "passage_id": passage_id, "script": script}


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


def _load_question(exam_id: str, question_id: str):
    from pipeline.core.store_mock_exam import load_mock_exam_job

    job = load_mock_exam_job(exam_id)
    if not job or not job.get("artifact"):
        raise HTTPException(status_code=404, detail=f"No staged content for {exam_id}")

    artifact = job["artifact"]
    question = next((q for q in artifact.get("questions", []) if q["id"] == question_id), None)
    if not question:
        raise HTTPException(status_code=404, detail=f"Question {question_id} not found in {exam_id}")
    return job, artifact, question


@router.post("/mock-exams/{exam_id}/upload-question-audio")
async def upload_mock_exam_question_audio(
    exam_id: str,
    question_id: str = Form(...),
    file: UploadFile = Form(...),
):
    """Upload the spoken clip that the learner hears next to one question."""
    from pipeline.core.store_mock_exam import save_mock_exam_job

    job, artifact, question = _load_question(exam_id, question_id)

    suffix = Path(file.filename or "").suffix.lower() or ".mp3"
    if suffix not in {".mp3", ".wav", ".m4a", ".ogg"}:
        raise HTTPException(status_code=400, detail="Unsupported audio format")

    content = await file.read()
    dest_dir = ROOT / "output" / "mock_exams" / "audio" / exam_id / "questions"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{question_id}{suffix}"
    dest.write_bytes(content)
    rel = str(dest.relative_to(ROOT))

    question["question_audio_url"] = rel
    save_mock_exam_job(exam_id, job["section"], job["exam_number"], job["level"], artifact, job["status"])
    return {"path": rel, "question_id": question_id}


@router.post("/mock-exams/{exam_id}/generate-question-audio")
async def generate_mock_exam_question_audio(
    exam_id: str,
    question_id: str = Form(...),
):
    """Generate the spoken clip for one question from its audio script."""
    from pipeline import settings
    from pipeline.generate.generate_mock_exam import generate_knm_question_audio, knm_question_audio_script
    from pipeline.core.store_mock_exam import save_mock_exam_job

    job, artifact, question = _load_question(exam_id, question_id)
    passage = next((p for p in artifact.get("passages", []) if p["id"] == question.get("passage_id")), None)
    script = (question.get("audio_script") or knm_question_audio_script(question, passage)).strip()
    if not script:
        raise HTTPException(status_code=400, detail="Question has no audio script")
    if not settings.GEMINI_TTS_API_KEYS:
        raise HTTPException(status_code=503, detail="GEMINI_TTS_API_KEYS is not configured")

    question["audio_script"] = script
    generated = await asyncio.to_thread(
        generate_knm_question_audio, exam_id, question, ROOT / "output", True
    )
    if not generated:
        raise HTTPException(status_code=502, detail="Could not generate question audio")

    save_mock_exam_job(exam_id, job["section"], job["exam_number"], job["level"], artifact, job["status"])
    return {"path": question["question_audio_url"], "question_id": question_id, "script": script}
