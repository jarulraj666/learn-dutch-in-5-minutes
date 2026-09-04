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
import re
import json
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
    "speaking":  {"total_questions": 16, "time_limit_minutes": 35, "parts_count": 4, "pass_threshold": None, "max_score": None},
    "knm":       {"total_questions": 40, "time_limit_minutes": 45, "parts_count": 1, "pass_threshold": 28, "max_score": 40},
}

_VALID_PASSAGE_TYPES = {"text", "audio", "video", "one_picture", "two_picture", "three_picture"}
_VALID_QUESTION_TYPES = {"multiple_choice", "open_written", "open_spoken"}
_VALID_KNM_CATEGORIES = {
    "customs", "work_income", "education", "healthcare",
    "housing", "institutions", "government", "history_geography",
}


def _load_approved_exam_plan(section: str, exam_number: int) -> dict[str, Any] | None:
    if section not in {"listening", "knm"}:
        return None
    scenario_path = settings.ROOT / "config" / f"mock_exam_{section}_scenarios.json"
    if not scenario_path.exists():
        return None
    scenario_plans = json.loads(scenario_path.read_text(encoding="utf-8"))
    scenario_plan = scenario_plans.get("exams", {}).get(str(exam_number))
    return scenario_plan if isinstance(scenario_plan, dict) else None


def _default_listening_display_prompt(passage: dict[str, Any]) -> str:
    title = str(passage.get("title") or "dit fragment").strip()
    media_word = "video" if passage.get("passage_type") == "video" else "fragment"
    return f"U hoort een {media_word}: {title}.\n\nLees eerst de vraag.\nLuister daarna naar het {media_word}."


_STILL_IMAGE_STYLE = (
    "Naturalistic educational assessment still, landscape 16:9, eye-level medium-wide shot, "
    "realistic daylight, clear uncluttered composition, no readable text, labels, logos, "
    "speech bubbles or watermarks."
)


def _with_still_image_style(scene: str) -> str:
    """Append the shared assessment-photo style used by every picture task."""
    scene = scene.strip()
    if not scene or _STILL_IMAGE_STYLE.split(",")[0].lower() in scene.lower():
        return scene
    if not scene.endswith("."):
        scene = f"{scene}."
    return f"{scene} {_STILL_IMAGE_STYLE}"


def knm_question_audio_script(question: dict[str, Any], passage: dict[str, Any] | None = None) -> str:
    """Spoken script of one KNM item: the situation and the question, as shown on the left panel."""
    situation = str((passage or {}).get("content_nl", "")).strip()
    question_text = str(question.get("question_text", "")).strip()
    return "\n\n".join(part for part in (situation, question_text) if part)


# ---------------------------------------------------------------------------
# Content generation
# ---------------------------------------------------------------------------

def _prompt_path(section: str) -> Path:
    return settings.ROOT / f"prompts/A2/mock_exam_{section}.md"


def _with_sentence_breaks(script: str) -> str:
    """Insert one-second SSML pauses after complete sentences, except the final one."""
    sentences = re.findall(r"[^.?!]+[.?!]", script)
    if len(sentences) < 2:
        return script
    return ' <break time="1s" /> '.join(sentence.strip() for sentence in sentences)


def _with_part_two_reminder(script: str) -> str:
    """Ensure one-picture task audio ends with the learner's visual reminder."""
    return script if script.endswith("Gebruik het plaatje.") else f"{script}\n\nGebruik het plaatje."


def _build_prompt(section: str, exam_number: int) -> str:
    template = _prompt_path(section).read_text(encoding="utf-8")
    prompt = template.replace("{exam_number}", str(exam_number))
    if section == "speaking":
        scenario_path = settings.ROOT / "config" / "mock_exam_speaking_scenarios.json"
        scenario_plans = json.loads(scenario_path.read_text(encoding="utf-8"))
        scenario_plan = scenario_plans["exams"].get(str(exam_number))
        if not scenario_plan:
            raise ValueError(f"No speaking scenario plan for exam #{exam_number}")
        scenario_plan = json.loads(json.dumps(scenario_plan))
        for item in scenario_plan["parts"]["1"]:
            item["script"] = _with_sentence_breaks(item["script"])
        for item in scenario_plan["parts"]["2"]:
            item["script"] = _with_part_two_reminder(item["script"])
        prompt += (
            "\n\n## Selected approved scenario plan - mandatory\n\n"
            "Use every entry below exactly once. For Part 1, copy `script` into `content_nl`. "
            "For Parts 2-4, copy `script` into `question_text`. Do not change the planned scenario "
            "or script, but create the matching title, media description, model answer and rubric.\n\n"
            + json.dumps(scenario_plan, ensure_ascii=False, indent=2)
        )
        return prompt
    if section == "listening":
        scenario_plan = _load_approved_exam_plan(section, exam_number)
        if scenario_plan:
            prompt += (
                "\n\n## Selected approved listening exam plan - mandatory\n\n"
                "Use this exam plan exactly once. Copy every passage `content_nl` as the spoken audio script. "
                "Copy every question, option, answer and explanation exactly. Do not add, remove, rewrite, "
                "reorder, paraphrase or duplicate any item. Return the same shape as the normal output schema.\n\n"
                + json.dumps(scenario_plan, ensure_ascii=False, indent=2)
            )
            return prompt
    exam_id = f"a2-{section}-{exam_number}"
    from pipeline.core.store_mock_exam import list_mock_exam_artifacts

    previous_exams = list_mock_exam_artifacts(section, exclude_exam_id=exam_id)
    if not previous_exams:
        return prompt

    used_items = []
    for previous_exam in previous_exams:
        artifact = previous_exam["artifact"]
        passages_by_id = {passage["id"]: passage for passage in artifact.get("passages", [])}
        for question in artifact.get("questions", []):
            passage = passages_by_id.get(question.get("passage_id"), {})
            context = passage.get("content_nl") or passage.get("title") or passage.get("scene_description", "")
            used_items.append(
                f"- Exam {previous_exam['exam_number']}, part {question.get('part_number')}: "
                f"{context[:180]} | {question.get('question_text', '')[:180]}"
            )

    if used_items:
        prompt += (
            "\n\n## Previously generated scenarios - mandatory exclusion list\n\n"
            "The following are already used in other staged exams. Do not repeat, paraphrase, "
            "or make a near-duplicate of their setting, relationship, situation, task, or required answer. "
            "Invent a materially different scenario for every new question.\n"
            + "\n".join(used_items)
        )
    return prompt


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
        "display_prompt_nl": str(raw.get("display_prompt_nl", "")).strip(),
        "content_nl": str(raw.get("content_nl", "")).strip(),
        "content_en": (str(raw["content_en"]).strip() if raw.get("content_en") else None),
        "scene_description": str(raw.get("scene_description", "")).strip(),
        "presenter_gender": (str(raw.get("presenter_gender", "")).strip().lower() if passage_type == "video" else None),
        "media_urls": raw.get("media_urls") if isinstance(raw.get("media_urls"), list) else [],
        "render_manifest_path": str(raw.get("render_manifest_path", "")).strip() or None,
        "image_prompt": raw.get("image_prompt") if raw.get("image_prompt") else None,
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
        "question_audio_url": str(raw.get("question_audio_url", "")).strip() or None,
        "question_options_audio_url": str(raw.get("question_options_audio_url", "")).strip() or None,
        "option_audio_cues": raw.get("option_audio_cues") if isinstance(raw.get("option_audio_cues"), list) else None,
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
        "option_audio_urls": raw.get("option_audio_urls") if isinstance(raw.get("option_audio_urls"), list) else None,
        "option_media_urls": None,
        "audio_script": str(raw.get("audio_script", "")).strip() or None,
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
            if norm["passage_type"] == "video":
                if norm["presenter_gender"] not in {"female", "male"}:
                    norm["presenter_gender"] = "female" if i % 2 == 0 else "male"
                norm["image_prompt"] = [_build_exam_image_prompt(
                    norm["scene_description"] or norm["content_nl"], norm["presenter_gender"]
                )]
            if section == "listening" and not norm["display_prompt_nl"]:
                norm["display_prompt_nl"] = _default_listening_display_prompt(norm)
            passages.append(norm)

    raw_questions = raw.get("questions") if isinstance(raw.get("questions"), list) else []
    questions: list[dict[str, Any]] = []
    for i, rq in enumerate(raw_questions, start=1):
        norm = _normalize_question(rq, exam_id, i, passage_id_map)
        if norm:
            questions.append(norm)

    if section == "speaking":
        passages_by_id = {passage["id"]: passage for passage in passages}
        for question in questions:
            passage = passages_by_id.get(question["passage_id"])
            if passage and passage["passage_type"] in {"one_picture", "two_picture", "three_picture"}:
                passage["content_nl"] = question["question_text"]

    if section == "knm":
        passages_by_id = {passage["id"]: passage for passage in passages}
        for passage in passages:
            passage["scene_description"] = _with_still_image_style(passage["scene_description"])
            if passage["scene_description"]:
                passage["image_prompt"] = [_build_exam_image_prompt(passage["scene_description"])]
        for question in questions:
            question["audio_script"] = knm_question_audio_script(
                question, passages_by_id.get(question["passage_id"])
            )

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


def _has_expected_picture_panels(artifact: dict[str, Any]) -> bool:
    expected_panels = {"two_picture": 2, "three_picture": 3}
    for passage in artifact["passages"]:
        expected = expected_panels.get(passage["passage_type"])
        if expected is None:
            continue
        scenes = [scene.strip() for scene in passage.get("scene_description", "").split("|") if scene.strip()]
        if len(scenes) != expected:
            LOGGER.warning(
                "mock_exam: %s requires %d independent image prompts, got %d",
                passage["id"], expected, len(scenes),
            )
            return False
    return True


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

    approved_plan = _load_approved_exam_plan(section, exam_number)
    if approved_plan:
        artifact = normalize_mock_exam(approved_plan, section, exam_number)
        spec = SECTION_SPECS[section]
        if len(artifact["questions"]) != spec["total_questions"]:
            raise ValueError(
                f"approved mock exam plan for {artifact['id']} has "
                f"{len(artifact['questions'])} questions, expected {spec['total_questions']}"
            )
        return artifact

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
        if len(artifact["questions"]) == spec["total_questions"] and (
            section != "speaking" or _has_expected_picture_panels(artifact)
        ):
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


def _image_scene_description(scene_description: str) -> str:
    """Extract an image-only scene from a Part 1 video production prompt."""
    scene = re.sub(
        r"^Short naturalistic educational assessment video,\s*8-12 seconds,\s*"
        r"landscape 16:9,\s*one continuous eye-level medium-wide shot of\s*",
        "",
        scene_description.strip(),
        flags=re.IGNORECASE,
    )
    scene = re.sub(
        r"\s*Naturalistic educational assessment still,\s*landscape 16:9,\s*"
        r"eye-level medium-wide shot,\s*realistic daylight,\s*clear uncluttered composition,\s*"
        r"no readable text,\s*labels,\s*logos,\s*speech bubbles or watermarks\.\s*$",
        "",
        scene,
        flags=re.IGNORECASE,
    )
    return scene or scene_description


def _build_exam_image_prompt(scene_description: str, presenter_gender: str | None = None) -> str:
    """Build a single-scene image prompt with no forced character count.

    Deliberately does NOT reuse prompts/image_prompt.md or
    prompts/dialogue_image_prompt.md — both mandate exactly two conversing
    characters, which is wrong for exam picture-description tasks that show
    one everyday scene (which may have 0, 1 or several people in it).
    """
    presenter = (
        f"The image contains exactly one adult {presenter_gender} speaking presenter. "
        "They face straight toward the camera at eye level, clearly visible from the front. "
        "Do not include any other people, including in the background, reflections, posters, or screens.\n"
        if presenter_gender in {"female", "male"} else ""
    )
    image_scene = _image_scene_description(scene_description)
    return (
        "Create one high-quality naturalistic 16:9 assessment photograph "
        "depicting this everyday Dutch scene, suitable for a language-exam picture-description task.\n"
        f"{presenter}"
        f"Scene: {image_scene}\n"
        "Rules: no text, captions, watermarks or speech bubbles anywhere in the image. "
        "People and objects should be clear and unambiguous, since a learner must describe what they see."
    )


def _role_gender(scene: str, role: str, fallback: str) -> str:
    role_pattern = re.escape(role).replace(r"\ ", r"\s+")
    if re.search(rf"\b(?:female|woman|mevrouw|girl|young woman)\b[^.]*\b{role_pattern}\b", scene):
        return "female"
    if re.search(rf"\b(?:male|man|meneer|boy)\b[^.]*\b{role_pattern}\b", scene):
        return "male"
    if re.search(rf"\b{role_pattern}\b[^.]*\b(?:female|woman|mevrouw|girl|young woman)\b", scene):
        return "female"
    if re.search(rf"\b{role_pattern}\b[^.]*\b(?:male|man|meneer|boy)\b", scene):
        return "male"
    return fallback


def _listening_roles_from_scene(scene: str, first_line: str) -> tuple[dict[str, str], dict[str, str]]:
    first_line = first_line.lower()
    service_opener = bool(re.search(r"\b(?:kan ik u ergens mee helpen|kan ik u helpen|wat kan ik voor u)\b", first_line))

    speaker1_role = "speaker"
    speaker2_role = "speaker"
    speaker1_gender = "female"
    speaker2_gender = "male"

    if "pharmacist" in scene:
        speaker1_role, speaker2_role = "customer", "pharmacist"
        speaker1_gender = _role_gender(scene, "customer", "male")
        speaker2_gender = _role_gender(scene, "pharmacist", "female")
    elif "shop assistant" in scene:
        if service_opener:
            speaker1_role, speaker2_role = "shop assistant", "customer"
            speaker1_gender = _role_gender(scene, "shop assistant", "female")
            speaker2_gender = _role_gender(scene, "customer", "male")
        else:
            speaker1_role, speaker2_role = "customer", "shop assistant"
            speaker1_gender = _role_gender(scene, "customer", "male")
            speaker2_gender = _role_gender(scene, "shop assistant", "female")
    elif "fitness trainer" in scene:
        speaker1_role, speaker2_role = "gym member", "fitness trainer"
        speaker1_gender = _role_gender(scene, "gym member", "male")
        speaker2_gender = _role_gender(scene, "fitness trainer", "female")
    elif "baker" in scene:
        if service_opener:
            speaker1_role, speaker2_role = "baker", "customer"
            speaker1_gender = _role_gender(scene, "baker", "male")
            speaker2_gender = _role_gender(scene, "customer", "female")
        else:
            speaker1_role, speaker2_role = "customer", "baker"
            speaker1_gender = _role_gender(scene, "customer", "female")
            speaker2_gender = _role_gender(scene, "baker", "male")
    elif re.search(r"\b(?:employee|staff member)\b", scene):
        service_role = "employee" if "employee" in scene else "staff member"
        if service_opener:
            speaker1_role, speaker2_role = service_role, "customer"
            speaker1_gender = _role_gender(scene, service_role, "male")
            speaker2_gender = _role_gender(scene, "customer", "female" if "young woman" in scene else "male")
        else:
            speaker1_role, speaker2_role = "customer", service_role
            speaker1_gender = _role_gender(scene, "customer", "female" if "young woman" in scene else "male")
            speaker2_gender = "male" if "young woman" in scene and re.search(r"\b(?:employee|staff member)\b", scene) else _role_gender(scene, service_role, "male" if speaker1_gender == "female" else "female")
    elif "colleagues" in scene:
        speaker1_role, speaker2_role = "colleague", "colleague"
        if re.search(r"\b(?:hoi|hallo)\s+mark\b", first_line):
            speaker1_gender, speaker2_gender = "female", "male"
        else:
            speaker1_gender, speaker2_gender = "male", "female"
    elif "friends" in scene:
        speaker1_role, speaker2_role = "friend", "friend"
        speaker1_gender, speaker2_gender = "female", "male"
    elif "a man" in scene and "a woman" in scene:
        speaker1_gender, speaker2_gender = "male", "female"

    return (
        {"Speaker1": speaker1_gender, "Speaker2": speaker2_gender},
        {"Speaker1": speaker1_role, "Speaker2": speaker2_role},
    )


def _listening_passage_dialogue(passage: dict[str, Any]) -> tuple[list[dict[str, str]], dict[str, str], dict[str, str]]:
    script = str(passage.get("content_nl", "")).strip()
    scene = str(passage.get("scene_description", "")).lower()
    parts = [part.strip() for part in re.split(r"\s+-\s+", script) if part.strip()]
    if len(parts) < 2:
        return [{"Speaker1": script}], {"Speaker1": "female", "Speaker2": "male"}, {"Speaker1": "narrator", "Speaker2": "speaker"}

    turns = [{"Speaker1" if index % 2 == 0 else "Speaker2": line} for index, line in enumerate(parts)]
    speaker_genders, speaker_roles = _listening_roles_from_scene(scene, parts[0])
    return turns, speaker_genders, speaker_roles


def _is_listening_multi_speaker_passage(exam_id: str, passage: dict[str, Any]) -> bool:
    return "-listening-" in exam_id and bool(passage.get("scene_description")) and " - " in str(passage.get("content_nl", ""))


def _synthesize_passage_audio(passage: dict[str, Any], output_path: Path, provider_name: str | None = None) -> bool:
    from pipeline.clients.tts_provider_factory import create_tts_client

    output_path.parent.mkdir(parents=True, exist_ok=True)
    client = create_tts_client(provider_name or settings.TTS_PROVIDER)
    if passage.get("scene_description") and " - " in str(passage.get("content_nl", "")):
        dialogue, speaker_genders, speaker_roles = _listening_passage_dialogue(passage)
        return client.generate_dialogue_audio(
            dialogue,
            str(output_path),
            level="A1A2",
            category="dialogue",
            speaker_genders=speaker_genders,
            speaker_roles=speaker_roles,
        )

    presenter_gender = passage.get("presenter_gender")
    if presenter_gender not in {"female", "male"}:
        presenter_gender = "female"
    return client.generate_dialogue_audio(
        [{"Speaker1": passage["content_nl"]}],
        str(output_path),
        level="A1A2",
        category="dialogue",
        speaker_genders={"Speaker1": presenter_gender, "Speaker2": "male" if presenter_gender == "female" else "female"},
        speaker_roles={"Speaker1": "narrator", "Speaker2": "speaker"},
    )


def _synthesize_text_audio(
    text: str, output_path: Path, provider_name: str = "gemini", client: Any | None = None
) -> bool:
    from pipeline.clients.tts_provider_factory import create_tts_client

    if not text.strip():
        return False
    output_path.parent.mkdir(parents=True, exist_ok=True)
    client = client or create_tts_client(provider_name)
    return client.generate_dialogue_audio(
        [{"Speaker1": text.strip()}],
        str(output_path),
        level="A1A2",
        category="mock_exam_item",
        speaker_genders={"Speaker1": "female", "Speaker2": "male"},
        speaker_roles={"Speaker1": "exam narrator", "Speaker2": "exam narrator"},
    )


def knm_question_audio_path(exam_id: str, question_id: str, output_root: Path) -> Path:
    return output_root / "mock_exams" / "audio" / exam_id / "questions" / f"{question_id}.wav"


def generate_knm_question_audio(
    exam_id: str, question: dict[str, Any], output_root: Path, overwrite: bool = False, client: Any | None = None
) -> bool:
    """Voice one KNM item with Gemini. Every item uses the same female exam narrator."""
    script = (question.get("audio_script") or "").strip()
    if not script:
        return False

    audio_path = knm_question_audio_path(exam_id, question["id"], output_root)
    if audio_path.exists() and not overwrite:
        question["question_audio_url"] = _media_url_from_path(audio_path)
        return True
    try:
        if not _synthesize_text_audio(script, audio_path, "gemini", client):
            LOGGER.warning("mock_exam media: no audio generated for %s", question["id"])
            return False
    except Exception:
        LOGGER.exception("mock_exam media: question audio failed for %s", question["id"])
        return False

    question["question_audio_url"] = _media_url_from_path(audio_path)
    return True


def generate_listening_question_audio(exam_id: str, question: dict[str, Any], output_root: Path) -> None:
    """Generate Gemini TTS clips for the question and each answer option."""
    if question.get("question_type") != "multiple_choice":
        return
    media_dir = output_root / "mock_exams" / "audio" / exam_id
    question_id = question["id"]
    question_audio_path = media_dir / "questions_fast" / f"{question_id}.wav"
    try:
        question_ready = question_audio_path.exists() or _synthesize_text_audio(
            question.get("question_text", ""), question_audio_path
        )
    except Exception:
        LOGGER.exception("mock_exam media: question audio failed for %s", question_id)
        question_ready = False
    if question_ready:
        question["question_audio_url"] = str(question_audio_path)

    option_audio_urls: list[str | None] = []
    for index, option in enumerate(question.get("options") or [], start=1):
        option_audio_path = media_dir / "options_fast" / f"{question_id}-o{index}.wav"
        option_label = chr(64 + index)
        try:
            option_ready = option_audio_path.exists() or _synthesize_text_audio(f"{option_label}. {option}", option_audio_path)
        except Exception:
            LOGGER.exception("mock_exam media: option audio failed for %s option %d", question_id, index)
            option_ready = False
        if option_ready:
            option_audio_urls.append(str(option_audio_path))
        else:
            option_audio_urls.append(None)
    if option_audio_urls:
        question["option_audio_urls"] = option_audio_urls
    _combine_listening_question_audio(question, output_root)


def _audio_path_from_url(url: str, output_root: Path) -> Path:
    path = Path(url)
    if path.is_absolute():
        return path
    root = output_root.parent if output_root.name == "output" else settings.ROOT
    return root / path


def _media_url_from_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(settings.ROOT.resolve()))
    except ValueError:
        return str(path)


def _combine_listening_question_audio(question: dict[str, Any], output_root: Path) -> None:
    import wave as _wave

    question_audio_url = question.get("question_audio_url")
    option_audio_urls = [url for url in (question.get("option_audio_urls") or []) if url]
    if not question_audio_url or len(option_audio_urls) != len(question.get("options") or []):
        return

    source_urls = [question_audio_url, *option_audio_urls]
    source_paths = [_audio_path_from_url(url, output_root) for url in source_urls]
    if not all(path.exists() for path in source_paths):
        return

    output_path = source_paths[0].with_name(f"{question['id']}-with-options.wav")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cues: list[dict[str, float | int]] = []
    current_time = 0.0
    silence_seconds = 0.35

    try:
        with _wave.open(str(source_paths[0]), "rb") as first:
            params = first.getparams()
            frame_rate = first.getframerate()
            silence_frames = b"\0" * int(frame_rate * silence_seconds) * first.getnchannels() * first.getsampwidth()

        with _wave.open(str(output_path), "wb") as output:
            output.setparams(params)
            for index, path in enumerate(source_paths):
                with _wave.open(str(path), "rb") as source:
                    if source.getparams()[:3] != params[:3]:
                        LOGGER.warning("mock_exam media: cannot combine mismatched audio params for %s", question["id"])
                        return
                    frames = source.readframes(source.getnframes())
                    duration = source.getnframes() / source.getframerate()
                if index > 0:
                    cue_start = current_time
                    cues.append({"option_index": index - 1, "start": round(cue_start, 3), "end": round(cue_start + duration, 3)})
                output.writeframes(frames)
                current_time += duration
                if index < len(source_paths) - 1:
                    output.writeframes(silence_frames)
                    current_time += silence_seconds
    except Exception:
        LOGGER.exception("mock_exam media: combined question/options audio failed for %s", question["id"])
        return

    question["question_options_audio_url"] = _media_url_from_path(output_path)
    question["option_audio_cues"] = cues


def generate_passage_media(exam_id: str, passage: dict[str, Any], output_root: Path) -> None:
    """Best-effort media generation for one passage. Mutates passage in place."""
    passage_type = passage["passage_type"]
    passage_id = passage["id"]
    media_dir = output_root / "mock_exams"
    tts_provider = "elevenlabs" if _is_listening_multi_speaker_passage(exam_id, passage) else "gemini" if "-listening-" in exam_id else settings.TTS_PROVIDER

    try:
        if passage_type == "audio":
            audio_path = media_dir / "audio" / exam_id / f"{passage_id}.wav"
            if _synthesize_passage_audio(passage, audio_path, tts_provider):
                passage["media_urls"] = [media for media in passage.get("media_urls", []) if media.get("type") != "audio"]
                passage["media_urls"].append({"type": "audio", "url": str(audio_path)})

        elif passage_type == "video":
            audio_path = media_dir / "audio" / exam_id / f"{passage_id}.wav"
            if not _synthesize_passage_audio(passage, audio_path, tts_provider):
                LOGGER.error("mock_exam media: TTS failed for %s", passage_id)
                return

            from pipeline.stages import stage_image, stage_render

            image_prompt = _build_exam_image_prompt(
                passage.get("scene_description") or passage["content_nl"], passage.get("presenter_gender")
            )
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
        if artifact.get("section") == "listening" and not passage.get("image_prompt"):
            image_source = passage.get("scene_description") or passage.get("content_nl") or passage.get("title")
            if image_source:
                passage["image_prompt"] = [_build_exam_image_prompt(image_source, passage.get("presenter_gender"))]
        if passage["passage_type"] != "text":
            generate_passage_media(artifact["id"], passage, output_root)
        elif passage.get("scene_description"):
            passage["image_prompt"] = [_build_exam_image_prompt(passage["scene_description"])]
    if artifact.get("section") == "listening":
        for question in artifact.get("questions", []):
            generate_listening_question_audio(artifact["id"], question, output_root)
    if artifact.get("section") == "knm":
        for question in artifact.get("questions", []):
            generate_knm_question_audio(artifact["id"], question, output_root)
    return artifact


def generate_mock_exam_question_audio(
    artifact: dict[str, Any], output_root: Path | None = None, overwrite: bool = False
) -> int:
    """Voice every question of a listening/knm exam, skipping items that already have audio."""
    output_root = output_root or (settings.ROOT / "output")
    section = artifact.get("section")
    from pipeline.clients.tts_provider_factory import create_tts_client

    client = create_tts_client("gemini")
    done = 0
    for question in artifact.get("questions", []):
        if section == "knm":
            if generate_knm_question_audio(artifact["id"], question, output_root, overwrite, client):
                done += 1
        elif section == "listening":
            generate_listening_question_audio(artifact["id"], question, output_root)
            done += 1
    return done
