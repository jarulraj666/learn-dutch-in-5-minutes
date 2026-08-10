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
    topic: TopicChoice, language: str, level: str = "A1A2"
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
    topic: TopicChoice, language: str = "nl", level: str = "A1A2"
) -> dict[str, Any]:
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
            
            # Generate 5-6 scene-based image prompts for dialogue (new multi-image feature)
            try:
                image_prompts = _generate_multiple_image_prompts(script, speaker_metadata, topic)
                if image_prompts:
                    script["image_prompts"] = image_prompts
                    LOGGER.info(
                        "Generated %d image prompts for dialogue scenes (multi-image feature)",
                        len(image_prompts),
                    )
            except Exception as e:
                LOGGER.warning(
                    "Failed to generate multiple image prompts for dialogue: %s. Falling back to single image.",
                    str(e),
                )
                # image_prompt field remains available from LLM response for backward compatibility

    return script


def _is_rate_limited(exc: Exception) -> bool:
    """Return True if the exception indicates a Gemini 429 / quota error."""
    msg = str(exc).upper()
    return "429" in msg or "RESOURCE_EXHAUSTED" in msg or "QUOTA" in msg


def _generate_script_gemini(prompt: str) -> dict[str, Any]:
    from google import genai
    from google.genai import types

    if not settings.GEMINI_API_KEYS:
        raise ValueError("No Gemini API keys configured. Set GEMINI_API_KEYS in .env")

    models_to_try = ["gemini-3.6-flash", "gemini-3.5-flash"]

    for api_key in settings.GEMINI_KEY_ROTATOR.available_keys():
        client = genai.Client(api_key=api_key)
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
                    model_name, len(model_output),
                )
                return _extract_json(model_output)
            except Exception as e:
                if _is_rate_limited(e):
                    LOGGER.warning(
                        "Gemini 429 rate limit on %s — rotating to next key", model_name,
                    )
                    settings.GEMINI_KEY_ROTATOR.mark_rate_limited(api_key, exc=e)
                    break  # skip remaining models for this key, try next key
                LOGGER.warning("Gemini model %s failed: %s", model_name, str(e))
                continue

    raise RuntimeError("All Gemini API keys and models exhausted for script generation")


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


def _generate_multiple_image_prompts(
    script: dict[str, Any],
    speaker_metadata: dict[str, Any],
    topic: TopicChoice,
) -> list[dict[str, Any]]:
    """Generate 5-6 scene-based image prompts keyed to Dutch trigger sentences.
    
    Identifies 5-6 distinct visual scenes from the dialogue and stores the exact
    Dutch sentence that triggers each scene change. At render time (Stage 4), the
    ASS subtitle file is used to look up when that sentence was spoken to get
    precise image display timing.
    
    See: prompts/dialogue_image_prompt.md for template details and examples.
    
    Args:
        script: Generated script dict containing dialogue and image_prompt
        speaker_metadata: Speaker info including scenario
        topic: Topic metadata
    
    Returns:
        List of dicts with keys: scene, prompt, description, trigger_sentence
    """
    from google import genai
    from google.genai import types
    
    dialogue = script.get("dialogue", [])
    scenario = speaker_metadata.get("scenario", "Dutch conversation")
    speakers = speaker_metadata.get("speakers", [])
    
    if not dialogue or len(dialogue) < 10:
        LOGGER.warning("Dialogue too short for multi-scene generation; using single prompt")
        return []
    
    s1 = next((s for s in speakers if s["id"] == "Speaker1"), {})
    s2 = next((s for s in speakers if s["id"] == "Speaker2"), {})
    speaker1_gender = s1.get("gender", "female")
    speaker2_gender = s2.get("gender", "male")
    speaker1_role = s1.get("role", "Speaker1")
    speaker2_role = s2.get("role", "Speaker2")
    
    # Build dialogue text with line numbers for LLM scene analysis (no timing needed)
    dialogue_lines = []
    for idx, line_dict in enumerate(dialogue):
        if isinstance(line_dict, dict):
            for speaker, content in line_dict.items():
                dialogue_lines.append(f"Line {idx+1} - {speaker}: {content}")
                break
        else:
            dialogue_lines.append(f"Line {idx+1}: {line_dict}")
    
    dialogue_text = "\n".join(dialogue_lines)
    
    # Ask LLM to identify scenes by the exact Dutch sentence that starts each scene
    scene_detection_prompt = f"""You are analyzing a Dutch dialogue to identify 5-6 distinct visual scenes for video illustration.

## Dialogue
{dialogue_text}

## Metadata
- Scenario: {scenario}
- Speaker 1 ({speaker1_role}): {speaker1_gender}
- Speaker 2 ({speaker2_role}): {speaker2_gender}
- Title hint: {topic.title_hint}

## Task
Identify 5-6 distinct visual moments in this dialogue where the scene naturally shifts.
For each scene, pick the EXACT Dutch sentence from the dialogue that marks the START of that scene.

Rules:
- Copy the sentence exactly as it appears in the dialogue (keep original Dutch text, spelling, punctuation)
- Each trigger_sentence must be a unique line from the dialogue
- Scenes should cover the full dialogue from start to finish
- First scene should start with the very first line

Output ONLY valid JSON with no text before or after:
{{
  "scenes": [
    {{
      "scene": 1,
      "trigger_sentence": "Exact Dutch sentence from the dialogue",
      "visual_focus": "greeting and initial setup",
      "description": "Two speakers meeting and greeting each other"
    }},
    {{
      "scene": 2,
      "trigger_sentence": "Another exact Dutch sentence from the dialogue",
      "visual_focus": "main conversation topic",
      "description": "Engaged discussion about the main topic"
    }}
  ]
}}
"""
    
    if not settings.GEMINI_API_KEYS:
        LOGGER.warning("No Gemini API keys for scene detection; returning empty list")
        return []
    
    scenes_data = None
    for api_key in settings.GEMINI_KEY_ROTATOR.available_keys():
        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=scene_detection_prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                ),
            )
            scenes_data = _extract_json(response.text)
            LOGGER.info("Scene detection successful; found %d scenes", len(scenes_data.get("scenes", [])))
            break
        except Exception as e:
            if _is_rate_limited(e):
                LOGGER.warning("Gemini 429 on scene detection — rotating to next key")
                settings.GEMINI_KEY_ROTATOR.mark_rate_limited(api_key, exc=e)
                continue
            LOGGER.warning("Scene detection failed: %s", str(e))
            continue
    
    if not scenes_data or not scenes_data.get("scenes"):
        LOGGER.warning("Failed to detect scenes from dialogue")
        return []
    
    scenes = scenes_data.get("scenes", [])
    if len(scenes) > 6:
        scenes = scenes[:6]
    
    # Load the level-specific dialogue_image_prompt.md template as the consistent
    # base for ALL scene prompts — ensures identical character style across all images.
    level = script.get("level", "A1A2")
    template_path = settings.ROOT / f"prompts/{level}/dialogue_image_prompt.md"
    if template_path.exists():
        template_text = template_path.read_text(encoding="utf-8").strip()
        base_prompt = (
            template_text
            .replace("{scenario}", scenario)
            .replace("{topic_title}", topic.title_hint)
            .replace("{speaker1_role}", speaker1_role)
            .replace("{speaker1_gender}", speaker1_gender)
            .replace("{speaker2_role}", speaker2_role)
            .replace("{speaker2_gender}", speaker2_gender)
        )
        LOGGER.debug("Loaded dialogue_image_prompt.md from %s", template_path)
    else:
        LOGGER.warning("dialogue_image_prompt.md not found at %s; using script image_prompt", template_path)
        base_prompt = script.get("image_prompt", "")
    
    # Merge in the LLM's scene description (specific environment details from Stage 1)
    scene_description_from_script = script.get("image_prompt", "")
    
    # Build scene-specific prompts keyed to trigger sentences
    image_prompts = []
    for scene_item in scenes:
        scene_num = scene_item.get("scene", 0)
        trigger_sentence = scene_item.get("trigger_sentence", "")
        visual_focus = scene_item.get("visual_focus", "conversation")
        description = scene_item.get("description", "")
        
        # Build prompt: consistent template base + scene-specific environment + scene focus
        # The template ensures same characters; environment and focus change per scene.
        scene_prompt = (
            f"{base_prompt} "
            f"Environment: {scene_description_from_script} "
            f"Scene focus: {description}. "
            f"Visual emphasis: {visual_focus}."
        )
        
        image_prompts.append({
            "scene": scene_num,
            "prompt": scene_prompt,
            "description": description,
            "trigger_sentence": trigger_sentence,
        })
        LOGGER.debug(
            "Scene %d: trigger=%r — visual focus: %s",
            scene_num, trigger_sentence[:60], visual_focus
        )
    
    LOGGER.info("Generated %d scene-based image prompts with trigger sentences", len(image_prompts))
    return image_prompts