"""Generate A2 mock exam content and media (Staatsexamen NT2 Programma I style).

Content generation mirrors pipeline/generate/generate_quiz.py: build a prompt
from prompts/A2/mock_exam_<section>.md, call Gemini, then validate/normalize
the JSON response into the schemas/mock_exam.schema.json shape.

Media generation (audio/image/video) is a separate, independently callable
step that reuses existing pipeline building blocks (TTS client, image stage,
video renderer) but is best-effort: failures are logged per-passage so a
single bad fragment never blocks the rest of an exam. See
pipeline/tools/generate_and_export_mock_exams.py for the CLI that wires
content generation, media generation and Postgres export together.
"""
from __future__ import annotations

import logging
import random
from pathlib import Path
from typing import Any

from pipeline import settings

LOGGER = logging.getLogger(__name__)

SECTIONS = ("reading", "listening", "writing", "speaking", "knm")

# Exact real-exam structure per section (see plan / user-provided spec).
SECTION_SPECS: dict[str, dict[str, Any]] = {
    "reading":   {"total_questions": 25, "time_limit_minutes": 65, "parts_count": 1, "pass_threshold": 18, "max_score": 25},
    "listening": {"total_questions": 25, "time_limit_minutes": 45, "parts_count": 1, "pass_threshold": 18, "max_score": 25},
    "writing":   {"total_questions": 4,  "time_limit_minutes": 40, "parts_count": 4, "pass_threshold": None, "max_score": 37},
    "speaking":  {"total_questions": 16, "time_limit_minutes": 36, "parts_count": 4, "pass_threshold": None, "max_score": None},
    "knm":       {"total_questions": 40, "time_limit_minutes": 45, "parts_count": 1, "pass_threshold": 28, "max_score": 40},
}

_VALID_PASSAGE_TYPES = {"text", "audio", "video", "one_picture", "two_picture", "three_picture"}
_VALID_QUESTION_TYPES = {"multiple_choice", "open_written", "open_spoken"}
_VALID_KNM_CATEGORIES = {"customs", "education", "healthcare", "housing", "history_geography"}


# ---------------------------------------------------------------------------
# Content generation
# ---------------------------------------------------------------------------

def _prompt_path(section: str) -> Path:
    return settings.ROOT / f"prompts/A2/mock_exam_{section}.md"


def _build_prompt(section: str, exam_number: int) -> str:
    template = _prompt_path(section).read_text(encoding="utf-8")
    return template.replace("{exam_number}", str(exam_number))


def _normalize_passage(raw: Any, exam_id: str, index: int) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    passage_type = str(raw.get("passage_type", "")).strip().lower()
    if passage_type not in _VALID_PASSAGE_TYPES:
        return None
    return {
        "id": f"{exam_id}-p{index}",
        "order_index": index,
        "part_number": raw.get("part_number"),
        "passage_type": passage_type,
        "title": str(raw.get("title", "")).strip(),
        "content_nl": str(raw.get("content_nl", "")).strip(),
        "content_en": (str(raw["content_en"]).strip() if raw.get("content_en") else None),
        "scene_description": str(raw.get("scene_description", "")).strip(),
        "media_urls": [],
        "render_manifest_path": None,
        "image_prompt": None,
    }


def _normalize_question(
    raw: Any, exam_id: str, index: int, passage_id_map: dict[str, str]
) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    question_type = str(raw.get("question_type", "")).strip().lower()
    if question_type not in _VALID_QUESTION_TYPES:
        return None
    question_text = str(raw.get("question_text", "")).strip()
    if not question_text:
        return None

    year_asked = raw.get("year_asked")
    item: dict[str, Any] = {
        "id": f"{exam_id}-q{index}",
        "passage_id": passage_id_map.get(str(raw.get("passage_id", ""))),
        "part_number": raw.get("part_number"),
        "order_index": index,
        "question_text": question_text,
        "question_type": question_type,
        "explanation": str(raw.get("explanation", "")).strip(),
        "max_score": int(raw.get("max_score") or 1),
        "year_asked": year_asked if isinstance(year_asked, int) else None,
        "category": None,
        "options": None,
        "answer": None,
        "grading_rubric": None,
        "model_answer": None,
        "option_image_prompts": None,
        "option_media_urls": None,
    }

    if question_type == "multiple_choice":
        options = [str(o).strip() for o in (raw.get("options") or []) if str(o).strip()]
        answer = str(raw.get("answer", "")).strip()
        if len(options) < 2 or not answer or answer not in options:
            LOGGER.warning("mock_exam: dropping MC question with bad options/answer: %s", question_text[:60])
            return None

        # Rare "picture-choice" questions (real exam sometimes shows 3-4 photos per option
        # instead of text, e.g. "what's in Suzanne's bag?"): the LLM can supply one image
        # prompt per option, in the same order as `options`.
        raw_option_prompts = raw.get("option_image_prompts")
        option_prompts: list[str] | None = None
        if isinstance(raw_option_prompts, list) and len(raw_option_prompts) == len(options):
            option_prompts = [str(p).strip() for p in raw_option_prompts]

        # LLMs tend to cluster the correct answer in one option position (often 2nd) even
        # when told to vary it — shuffle deterministically so the true distribution is even.
        # Shuffle options and their image prompts together so they stay aligned.
        rng = random.Random(f"{exam_id}-q{index}")
        if option_prompts:
            pairs = list(zip(options, option_prompts))
            rng.shuffle(pairs)
            options, option_prompts = [p[0] for p in pairs], [p[1] for p in pairs]
        else:
            rng.shuffle(options)

        item["options"] = options
        item["answer"] = answer
        item["option_image_prompts"] = option_prompts
        if option_prompts:
            item["option_media_urls"] = [None] * len(option_prompts)
        category = str(raw.get("category", "")).strip().lower() or None
        item["category"] = category if category in _VALID_KNM_CATEGORIES else None
    else:
        rubric = raw.get("grading_rubric")
        item["grading_rubric"] = rubric if isinstance(rubric, list) else []
        item["model_answer"] = str(raw.get("model_answer", "")).strip()

    return item


def normalize_mock_exam(raw: dict[str, Any], section: str, exam_number: int) -> dict[str, Any]:
    """Coerce a raw LLM response into the canonical mock-exam artifact shape."""
    if section not in SECTION_SPECS:
        raise ValueError(f"Unknown section: {section}")

    exam_id = f"a2-{section}-{exam_number}"
    spec = SECTION_SPECS[section]

    raw_passages = raw.get("passages") if isinstance(raw.get("passages"), list) else []
    passages: list[dict[str, Any]] = []
    passage_id_map: dict[str, str] = {}
    for i, rp in enumerate(raw_passages, start=1):
        norm = _normalize_passage(rp, exam_id, i)
        if norm:
            raw_id = str(rp.get("id", "")) if isinstance(rp, dict) else ""
            if raw_id:
                passage_id_map[raw_id] = norm["id"]
            passages.append(norm)

    raw_questions = raw.get("questions") if isinstance(raw.get("questions"), list) else []
    questions: list[dict[str, Any]] = []
    for i, rq in enumerate(raw_questions, start=1):
        norm = _normalize_question(rq, exam_id, i, passage_id_map)
        if norm:
            questions.append(norm)

    if len(questions) != spec["total_questions"]:
        LOGGER.warning(
            "mock_exam: %s expected %d questions, got %d",
            exam_id, spec["total_questions"], len(questions),
        )

    return {
        "id": exam_id,
        "section": section,
        "level": "A2",
        "exam_number": exam_number,
        "title": str(raw.get("title", "")).strip() or f"{section.title()} - Oefenexamen {exam_number}",
        "instructions": str(raw.get("instructions", "")).strip(),
        "time_limit_minutes": spec["time_limit_minutes"],
        "total_questions": len(questions),
        "parts_count": spec["parts_count"],
        "pass_threshold": spec["pass_threshold"],
        "max_score": spec["max_score"],
        "passages": passages,
        "questions": questions,
    }


def generate_mock_exam_content(section: str, exam_number: int, verify: bool = True) -> dict[str, Any]:
    """Call the LLM and return a normalized mock-exam artifact for one exam.

    When *verify* is true (default), multiple-choice questions get a second-pass
    QA review (see verify_mock_exam_questions) that catches the kind of error a
    single generation pass tends to make — e.g. misreading overlapping time
    ranges in a schedule and picking the wrong day/option as the answer.

    The verifier can drop ambiguous questions, and the LLM itself sometimes
    under/over-generates, so this retries (regenerating from scratch) until the
    artifact has exactly spec["total_questions"] questions, up to MAX_ATTEMPTS.
    """
    from pipeline.generate.generate_script import _generate_script_gemini

    if section not in SECTION_SPECS:
        raise ValueError(f"Unknown section: {section}")

    spec = SECTION_SPECS[section]
    exam_id = f"a2-{section}-{exam_number}"
    max_attempts = 3
    last_artifact: dict[str, Any] | None = None

    for attempt in range(1, max_attempts + 1):
        prompt = _build_prompt(section, exam_number)
        result = _generate_script_gemini(prompt)
        if not isinstance(result, dict):
            raise ValueError(f"mock exam generation returned no object for {section} #{exam_number}")

        artifact = normalize_mock_exam(result, section, exam_number)
        if verify and any(q["question_type"] == "multiple_choice" for q in artifact["questions"]):
            artifact = verify_mock_exam_questions(artifact)

        last_artifact = artifact
        if len(artifact["questions"]) == spec["total_questions"]:
            return artifact

        LOGGER.warning(
            "mock_exam: %s attempt %d/%d produced %d questions, need exactly %d — retrying",
            exam_id, attempt, max_attempts, len(artifact["questions"]), spec["total_questions"],
        )

    raise ValueError(
        f"mock exam generation for {exam_id} could not reach exactly "
        f"{spec['total_questions']} questions after {max_attempts} attempts "
        f"(last attempt had {len(last_artifact['questions']) if last_artifact else 0})"
    )


_VERIFY_PROMPT_PATH_NAME = "mock_exam_verify"


def verify_mock_exam_questions(artifact: dict[str, Any]) -> dict[str, Any]:
    """Second-pass QA: re-derive each MC answer from its passage, fix or drop bad ones.

    Best-effort — if the verifier call itself fails, the original artifact is
    returned unchanged rather than blocking content generation entirely.
    """
    import json as _json

    from pipeline.generate.generate_script import _generate_script_gemini

    mc_questions = [q for q in artifact["questions"] if q["question_type"] == "multiple_choice"]
    if not mc_questions:
        return artifact

    payload = {
        "passages": [
            {"id": p["id"], "content_nl": p["content_nl"]} for p in artifact["passages"]
        ],
        "questions": [
            {
                "id": q["id"],
                "passage_id": q["passage_id"],
                "question_text": q["question_text"],
                "options": q["options"],
                "answer": q["answer"],
            }
            for q in mc_questions
        ],
    }

    template = (settings.ROOT / f"prompts/A2/{_VERIFY_PROMPT_PATH_NAME}.md").read_text(encoding="utf-8")
    prompt = template.replace("{payload_json}", _json.dumps(payload, ensure_ascii=False, indent=2))

    try:
        result = _generate_script_gemini(prompt)
        reviews = result.get("reviews") if isinstance(result, dict) else None
        if not isinstance(reviews, list):
            raise ValueError("verifier returned no 'reviews' array")
    except Exception:
        LOGGER.exception("mock_exam: verifier pass failed for %s, keeping unverified answers", artifact["id"])
        return artifact

    review_by_id = {r.get("id"): r for r in reviews if isinstance(r, dict)}
    drop_ids: set[str] = set()
    for q in mc_questions:
        review = review_by_id.get(q["id"])
        if not review:
            continue
        verdict = str(review.get("verdict", "ok")).strip().lower()
        if verdict == "fix":
            corrected = str(review.get("corrected_answer", "")).strip()
            if corrected and corrected in q["options"]:
                LOGGER.info(
                    "mock_exam: verifier corrected %s answer %r -> %r (%s)",
                    q["id"], q["answer"], corrected, review.get("reason", ""),
                )
                q["answer"] = corrected
        elif verdict == "drop":
            LOGGER.warning(
                "mock_exam: verifier dropped ambiguous question %s (%s)",
                q["id"], review.get("reason", ""),
            )
            drop_ids.add(q["id"])

    if drop_ids:
        artifact["questions"] = [q for q in artifact["questions"] if q["id"] not in drop_ids]
        artifact["total_questions"] = len(artifact["questions"])

    return artifact


# ---------------------------------------------------------------------------
# Media generation (best-effort; failures are logged and swallowed per-passage)
# ---------------------------------------------------------------------------

def _blank_ass_path(output_path: Path) -> Path:
    """Write a structurally valid ASS file with zero Dialogue lines.

    render_from_artifact() requires a karaoke ASS file to exist, but burning
    the Dutch transcript into a *listening* exam video would give away the
    answer. An ASS with headers only and no events renders nothing.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1920\n"
        "PlayResY: 1080\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,Arial,48,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n",
        encoding="utf-8",
    )
    return output_path


def _build_exam_image_prompt(scene_description: str) -> str:
    """Build a single-scene image prompt with no forced character count.

    Deliberately does NOT reuse prompts/image_prompt.md or
    prompts/dialogue_image_prompt.md — both mandate exactly two conversing
    characters, which is wrong for exam picture-description tasks that show
    one everyday scene (which may have 0, 1 or several people in it).
    """
    return (
        "Create one high-quality 16:9 illustration in a clean, bright cartoon style "
        "depicting this everyday Dutch scene, suitable for a language-exam picture-description task.\n"
        f"Scene: {scene_description}\n"
        "Rules: no text, captions, watermarks or speech bubbles anywhere in the image. "
        "People and objects should be clear and unambiguous, since a learner must describe what they see."
    )


def _synthesize_passage_audio(passage: dict[str, Any], output_path: Path) -> bool:
    from pipeline.clients.tts_provider_factory import create_tts_client

    output_path.parent.mkdir(parents=True, exist_ok=True)
    client = create_tts_client(settings.TTS_PROVIDER)
    return client.generate_dialogue_audio(
        [{"speaker": "Narrator", "line": passage["content_nl"]}],
        str(output_path),
        level="A1A2",
        category="dialogue",
        speaker_genders={"Narrator": "female"},
    )


def generate_passage_media(exam_id: str, passage: dict[str, Any], output_root: Path) -> None:
    """Best-effort media generation for one passage. Mutates passage in place."""
    passage_type = passage["passage_type"]
    passage_id = passage["id"]
    media_dir = output_root / "mock_exams"

    try:
        if passage_type == "audio":
            audio_path = media_dir / "audio" / exam_id / f"{passage_id}.wav"
            if _synthesize_passage_audio(passage, audio_path):
                passage["media_urls"].append({"type": "audio", "url": str(audio_path)})

        elif passage_type == "video":
            audio_path = media_dir / "audio" / exam_id / f"{passage_id}.wav"
            if not _synthesize_passage_audio(passage, audio_path):
                LOGGER.error("mock_exam media: TTS failed for %s", passage_id)
                return

            from pipeline.stages import stage_image, stage_render

            image_prompt = _build_exam_image_prompt(passage.get("scene_description") or passage["content_nl"])
            primary_image, _files, _seed = stage_image(
                topic_id=passage_id,
                topic_title=passage.get("title") or passage_id,
                image_prompt=image_prompt,
                image_prompts=[],
                level="A2",
                category="mock_exam",
                output_root=media_dir,
            )
            if not primary_image:
                LOGGER.error("mock_exam media: image generation failed for %s", passage_id)
                return

            ass_path = _blank_ass_path(media_dir / "subtitles" / exam_id / f"{passage_id}.ass")
            manifest_path = stage_render({
                "topic_id": passage_id,
                "level": "A2",
                "category": "mock_exam",
                "title_slug": passage_id,
                "audio_file": str(audio_path),
                "karaoke_file": str(ass_path),
                "generated_image_file": primary_image,
            })

            import json as _json
            manifest = _json.loads(Path(manifest_path).read_text(encoding="utf-8"))
            video_path = manifest.get("planned_video_file")
            if video_path:
                passage["media_urls"].append({"type": "video", "url": video_path})
                passage["render_manifest_path"] = str(manifest_path)
            passage["image_prompt"] = [image_prompt]

        elif passage_type in ("one_picture", "two_picture", "three_picture"):
            scenes = [s.strip() for s in (passage.get("scene_description") or "").split("|") if s.strip()]
            if not scenes:
                scenes = [passage.get("content_nl") or passage.get("title") or "an everyday Dutch scene"]

            from pipeline.stages import stage_image

            image_prompts = [{"scene": i + 1, "prompt": _build_exam_image_prompt(s)} for i, s in enumerate(scenes)]
            primary_image, all_files, _seed = stage_image(
                topic_id=passage_id,
                topic_title=passage.get("title") or passage_id,
                image_prompt=image_prompts[0]["prompt"] if image_prompts else "",
                image_prompts=image_prompts if len(image_prompts) > 1 else [],
                level="A2",
                category="mock_exam",
                output_root=media_dir,
            )
            files = all_files or ([primary_image] if primary_image else [])
            passage["media_urls"] = [{"type": "image", "url": f} for f in files]
            passage["image_prompt"] = [p["prompt"] for p in image_prompts]

    except Exception:
        LOGGER.exception("mock_exam media: generation failed for passage %s", passage_id)


def generate_mock_exam_media(artifact: dict[str, Any], output_root: Path | None = None) -> dict[str, Any]:
    """Generate media for every non-text passage in *artifact*. Mutates and returns artifact.

    Text passages never get an auto-generated image (real exam ads/notices only rarely show a
    photo), but if the LLM populated `scene_description` on one, we still surface an image_prompt
    so an admin can generate the picture separately and upload it via the Media tab.
    """
    output_root = output_root or (settings.ROOT / "output")
    for passage in artifact.get("passages", []):
        if passage["passage_type"] != "text":
            generate_passage_media(artifact["id"], passage, output_root)
        elif passage.get("scene_description"):
            passage["image_prompt"] = [_build_exam_image_prompt(passage["scene_description"])]
    return artifact
