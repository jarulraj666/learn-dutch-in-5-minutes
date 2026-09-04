from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.clients.key_rotator import KeyRotator


class WritingFeedbackError(RuntimeError):
    pass


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise WritingFeedbackError("Gemini returned an invalid feedback response")
    return parsed


async def _grade_writing_task(task: dict[str, Any], keys: list[str], key_offset: int) -> dict[str, Any]:
    """Grade one task, preferring a distinct key when several are available."""
    is_speaking_transcript = task.get("assessment_mode") == "speaking_transcript"
    examiner = "speaking" if is_speaking_transcript else "writing"
    assessment_criteria = (
        "Assess task completion, intelligibility, relevant everyday vocabulary, and basic spoken Dutch sentence structure."
        if is_speaking_transcript
        else "Assess grammar for basic Dutch sentence structure and word order; spelling for everyday words, capital letters, sentence punctuation, and factual details in forms; vocabulary for appropriate everyday Dutch; and cohesion for logical sentence flow using basic connectors."
    )
    response_criteria = (
        '[{"criterion":"adequacy_understandability","score":0},{"criterion":"grammar","score":0},{"criterion":"vocabulary","score":0},{"criterion":"cohesion","score":0}]'
        if is_speaking_transcript
        else '[{"criterion":"adequacy_understandability","score":0},{"criterion":"grammar","score":0},{"criterion":"spelling","score":0},{"criterion":"vocabulary","score":0},{"criterion":"cohesion","score":0}]'
    )
    transcript_instruction = (
        "This is an automatic WhisperX transcript of spoken Dutch, not a written answer. "
        "Assess what the learner intended and communicated aloud. Ignore misspellings, missing punctuation, "
        "capitalisation, and likely speech-recognition errors; do not mention or score spelling. "
        "Focus on task completion, intelligibility, relevant vocabulary, and spoken sentence structure. "
        if is_speaking_transcript else ""
    )
    prompt = f"""You are a fair Dutch NT2 Programma I (A2) {examiner} examiner.
Evaluate the learner answer against the task, source text, and rubric. Award only whole points and never exceed each criterion's maximum. `adequacy_understandability` is a strict gatekeeper: award it 0 when the answer is off-topic, not understandable, or misses a required task point; when it is 0, all other criterion scores must be 0 and the overall `score` must be 0. Within adequacy, check the required format: e-mails need a greeting, message, and closing; notes must communicate every requested action; wijkkrant texts need at least three complete sentences and all three requested ideas; forms need every factual field, appropriate selections, and all open fields completed. {assessment_criteria} Do not penalize harmless article confusion at A2 when meaning is clear. Your `score` must equal the sum of `criterion_scores`. Be encouraging but precise. Give feedback primarily in clear, concise English. You may quote a Dutch phrase from the learner's answer and provide a corrected Dutch phrase when that makes the improvement concrete, but explain the correction in English. In `possible_answer`, provide an improved Dutch rewrite of the learner's own answer: preserve their facts, choices, names, dates, and intended meaning; correct grammar, spelling, word order, punctuation, and cohesion; and add only the minimum content needed to satisfy a missing task requirement. Do not replace it with an unrelated example or copy the stored model answer.

{transcript_instruction}

Return strict JSON only, in this exact shape:
{{"id":"task id","score":0,"feedback":"2-4 short sentences, mostly English. Mention what was done well and the most useful improvements; optionally include one short Dutch correction in quotation marks.","possible_answer":"An improved Dutch rewrite of the learner's answer that preserves their details and completes the task.","criterion_scores":{response_criteria}}}

TASK:
""" + json.dumps(task, ensure_ascii=False)

    ordered_keys = keys[key_offset:] + keys[:key_offset]
    rotator = KeyRotator(ordered_keys, "gemini")
    request_body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
    }
    last_error: Exception | None = None
    async with httpx.AsyncClient(timeout=75, trust_env=False) as client:
        for key in rotator.available_keys():
            try:
                response = await client.post(
                    "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent",
                    params={"key": key},
                    json=request_body,
                )
                if response.status_code == 429:
                    rotator.mark_rate_limited(key, WritingFeedbackError(response.text))
                    last_error = WritingFeedbackError("Gemini is temporarily rate limited")
                    continue
                response.raise_for_status()
                data = response.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                item = _extract_json(text)
                if str(item.get("id")) != str(task["id"]):
                    raise WritingFeedbackError("Gemini returned feedback for the wrong task")
                return item
            except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError, WritingFeedbackError) as exc:
                last_error = exc

    raise WritingFeedbackError("Writing feedback could not be generated") from last_error


async def grade_writing_answers(tasks: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Grade submitted writing tasks concurrently, one Gemini call per task.

    The reference answers and rubrics are intentionally passed only to Gemini on
    the server. The learner receives scoring, actionable feedback, and one
    original possible Dutch response rather than the stored answer key.
    """
    keys = [key.strip() for key in os.environ.get("GEMINI_API_KEYS", "").split(",") if key.strip()]
    if not keys:
        raise WritingFeedbackError("Writing feedback is unavailable because no Gemini key is configured")

    outcomes = await asyncio.gather(
        *(_grade_writing_task(task, keys, index % len(keys)) for index, task in enumerate(tasks)),
        return_exceptions=True,
    )
    feedback = {
        str(item["id"]): item
        for item in outcomes
        if isinstance(item, dict) and item.get("id")
    }
    if not feedback:
        raise WritingFeedbackError("Writing feedback could not be generated")
    return feedback