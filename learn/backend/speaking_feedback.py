from __future__ import annotations

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

_MODULE_DIR = Path(__file__).resolve().parent
ROOT = _MODULE_DIR.parents[1] if _MODULE_DIR.name == "backend" else _MODULE_DIR


class SpeakingFeedbackError(RuntimeError):
    pass


def _label_from_transcript(transcript: str) -> str:
    word_count = len(transcript.split())
    if word_count >= 18:
        return "Excellent"
    if word_count >= 7:
        return "Good"
    return "Improvement needed"


def _gemini_keys() -> list[str]:
    if not os.environ.get("GEMINI_API_KEYS"):
        load_dotenv(ROOT / ".env")
    return [key.strip() for key in os.environ.get("GEMINI_API_KEYS", "").split(",") if key.strip()]


def _transcribe(audio_path: Path) -> str:
    import torch
    import whisperx

    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    model = whisperx.load_model(os.getenv("WHISPERX_MODEL", "base"), device, compute_type=compute_type, language="nl")
    result = model.transcribe(str(audio_path), batch_size=8)
    return " ".join(segment.get("text", "").strip() for segment in result.get("segments", [])).strip()


async def evaluate_speaking_recording(audio_path: Path, question_text: str, rubric: list[dict], model_answer: str) -> dict[str, str]:
    try:
        transcript = await asyncio.to_thread(_transcribe, audio_path)
    except Exception as exc:
        raise SpeakingFeedbackError("WhisperX could not transcribe this recording") from exc
    audio_path.unlink(missing_ok=True)
    if not transcript:
        return {
            "label": "Improvement needed",
            "spoken_text": "",
            "feedback": "No clear Dutch speech was recognised in this recording.",
            "possible_answer": model_answer,
        }

    try:
        from writing_feedback import _grade_writing_task
    except ModuleNotFoundError:
        from learn.backend.writing_feedback import _grade_writing_task

    keys = _gemini_keys()
    if not keys:
        return {
            "label": _label_from_transcript(transcript),
            "spoken_text": transcript,
            "feedback": "Your response was assessed from the amount of recognised Dutch speech.",
            "possible_answer": model_answer,
        }

    feedback = await _grade_writing_task({
        "id": "speaking",
        "assessment_mode": "speaking_transcript",
        "question_text": question_text,
        "learner_answer": transcript,
        "rubric": rubric,
        "model_answer": model_answer,
    }, keys, 0)
    score = int(feedback.get("score", 0))
    maximum = sum(int(item.get("max_points", 0)) for item in rubric)
    if maximum and score >= maximum * 0.8:
        label = "Excellent"
    elif maximum and score >= maximum * 0.5:
        label = "Good"
    else:
        label = "Improvement needed"
    return {
        "label": label,
        "spoken_text": transcript,
        "feedback": str(feedback.get("feedback", "")),
        "possible_answer": str(feedback.get("possible_answer", model_answer)),
    }