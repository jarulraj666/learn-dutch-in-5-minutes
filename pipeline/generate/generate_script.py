from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from pipeline import settings
from pipeline.core.select_topic import TopicChoice
from pipeline.utils import iter_dialogue_turns, to_compact_dialogue

LOGGER = logging.getLogger(__name__)


def _extract_json(text: str) -> dict[str, Any]:
    # Extract JSON object from text
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("No JSON object found in model output")

    json_text = match.group(0)
    first_error = None

    # Try parsing as-is first
    try:
        return json.loads(json_text)
    except json.JSONDecodeError as e:
        first_error = e
        LOGGER.debug("First parse attempt failed: %s", str(e))

    # Log the problematic JSON for debugging
    snippet = json_text[:500] if len(json_text) > 500 else json_text
    LOGGER.error(
        "json_parse_failed error=%s text_snippet=%s",
        str(first_error),
        snippet.replace("\n", " ")[:300],
    )

    # Pass 1: Remove trailing commas before } or ]
    cleaned = json_text
    cleaned = re.sub(r",(\s*[}\]])", r"\1", cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Pass 2: Remove common quote/escape issues
    cleaned = (
        cleaned.replace('"', '"')
        .replace('"', '"')
        .replace("'", "'")
        .replace("'", "'")
    )

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Pass 3: Handle incomplete/truncated JSON by finding last valid closing brace
    brace_depth = 0
    bracket_depth = 0
    in_string = False
    escape_next = False
    last_valid_pos = -1

    for i, char in enumerate(cleaned):
        if escape_next:
            escape_next = False
            continue

        if char == "\\":
            escape_next = True
            continue

        if char == '"' and not escape_next:
            in_string = not in_string
            continue

        if in_string:
            continue

        if char == "{":
            brace_depth += 1
            last_valid_pos = i
        elif char == "}":
            brace_depth -= 1
            if brace_depth == 0:
                last_valid_pos = i
        elif char == "[":
            bracket_depth += 1
        elif char == "]":
            bracket_depth -= 1

    if last_valid_pos > 0 and brace_depth == 0:
        truncated = cleaned[: last_valid_pos + 1]
        try:
            return json.loads(truncated)
        except json.JSONDecodeError:
            pass

    raise ValueError(
        f"Failed to parse JSON after cleanup attempts: {str(first_error)}"
    )


def _prompt_for_topic(
    topic: TopicChoice, language: str, level: str = "A1"
) -> str:
    category = getattr(topic, "category", "dialogue")
    LOGGER.info(
        "Generating prompt for topic_id=%s category=%s level=%s language=%s",
        topic.topic_id,
        category,
        level,
        language,
    )
    prompt_path = settings.ROOT / f"prompts/{level}/{category}.md"
    if not prompt_path.exists():
        raise FileNotFoundError(
            f"No prompt found for level={level!r} category={category!r}. "
            f"Expected: {prompt_path}"
        )
    prompt = prompt_path.read_text(encoding="utf-8")

    # Substitute speaker metadata placeholders for dialogue category
    if category == "dialogue":
        speaker_meta = _build_speaker_metadata(topic)
        if speaker_meta:
            speakers = speaker_meta.get("speakers", [])
            s1 = next((s for s in speakers if s["id"] == "Speaker1"), {})
            s2 = next((s for s in speakers if s["id"] == "Speaker2"), {})
            scenario = speaker_meta.get("scenario") or "a real-world Dutch conversation"
            prompt = (
                prompt
                .replace("{speaker1_role}", s1.get("role", "speaker"))
                .replace("{speaker1_gender}", s1.get("gender", "female"))
                .replace("{speaker2_role}", s2.get("role", "speaker"))
                .replace("{speaker2_gender}", s2.get("gender", "male"))
                .replace("{scenario}", scenario)
                .replace("{title_hint}", topic.title_hint)
            )

    return (
        f"{prompt}\n\n"
        f"---\n"
        f"Topic id: {topic.topic_id}\n"
        f"Topic hint: {topic.title_hint}\n"
        f"Category: {category}\n"
        f'Set the "language" field in JSON to "{language}".\n'
        f"Set dialogue format to compact speaker-key objects, e.g. {{\"Speaker1\": \"Hello\"}}.\n"
        f"Keep content at CEFR {level} and output strict JSON only."
    )


def _build_script_text(turns: list[tuple[str, str]]) -> str:
    """Create newline transcript in SpeakerX: text style."""
    return "\n".join(f"{speaker}: {line}" for speaker, line in turns if line)


def generate_script(
    topic: TopicChoice, language: str = "nl", level: str = "A1"
) -> dict[str, Any]:
    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set in settings/environment.")

    effective_level = getattr(topic, "level", None) or level
    category = getattr(topic, "category", "dialogue")
    prompt = _prompt_for_topic(topic, language, level=effective_level)

    LOGGER.debug("prompt_for_topic:\n%s", prompt)
    script = _generate_script_gemini(prompt)

    turns = iter_dialogue_turns(script.get("dialogue", []))
    script["dialogue"] = to_compact_dialogue(turns)
    script["script_text"] = _build_script_text(turns)

    # Inject level and category into script so downstream stages can use them
    script.setdefault("level", effective_level)
    script.setdefault("category", category)
    
    # The LLM generates image_prompt as part of the JSON response — use it directly.
    if not script.get("image_prompt"):
        LOGGER.warning("image_prompt missing from LLM response for topic_id=%s", topic.topic_id)

    # Enrich dialogue scripts with speaker metadata and scenario
    if category == "dialogue":
        speaker_metadata = _build_speaker_metadata(topic)
        if speaker_metadata:
            script["speakers"] = speaker_metadata["speakers"]
            script.setdefault("scenario", speaker_metadata.get("scenario"))

    return script


def _generate_script_gemini(prompt: str) -> dict[str, Any]:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    models_to_try = ["gemini-3.6-flash", "gemini-3.5-flash-lite"]

    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                ),
            )
            model_output = response.text
            if not model_output:
                LOGGER.warning(
                    "Empty response from %s, trying next model", model_name
                )
                continue
            LOGGER.info(
                "Script generated via Gemini model=%s chars=%d",
                model_name,
                len(model_output),
            )
            return _extract_json(model_output)
        except Exception as e:
            LOGGER.warning("Gemini model %s failed: %s", model_name, str(e))
            continue

    raise RuntimeError("All Gemini models failed for script generation")


def _build_speaker_metadata(topic: TopicChoice) -> dict[str, Any] | None:
    """Build speaker metadata list for dialogue topics.
    
    Returns a dict with 'speakers' list and 'scenario' for dialogue topics.
    Returns None for non-dialogue topics.
    """
    if getattr(topic, "category", None) != "dialogue":
        return None

    # Read voice mapping from config so voice_id reflects the actual configured voices
    gemini_voices = settings.PEDAGOGY_CONFIG.get("speech", {}).get("voice_map", {}).get("gemini", {})
    female_voice = gemini_voices.get("female", "Kore")
    male_voice = gemini_voices.get("male", "Puck")

    gender_to_voice = {
        "female": female_voice,
        "male": male_voice,
    }

    speakers = []
    
    # Speaker 1
    if hasattr(topic, "speaker1_role") and topic.speaker1_role:
        speaker1_gender = getattr(topic, "speaker1_gender", "female") or "female"
        speakers.append({
            "id": "Speaker1",
            "role": topic.speaker1_role,
            "gender": speaker1_gender,
            "voice_id": gender_to_voice.get(speaker1_gender, female_voice),
        })
    
    # Speaker 2
    if hasattr(topic, "speaker2_role") and topic.speaker2_role:
        speaker2_gender = getattr(topic, "speaker2_gender", "male") or "male"
        speakers.append({
            "id": "Speaker2",
            "role": topic.speaker2_role,
            "gender": speaker2_gender,
            "voice_id": gender_to_voice.get(speaker2_gender, male_voice),
        })
    
    if not speakers:
        return None

    return {
        "speakers": speakers,
        "scenario": getattr(topic, "scenario", None),
    }