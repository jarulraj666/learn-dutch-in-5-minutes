from __future__ import annotations

import json
import logging
import re
from typing import Any

import requests

from pipeline import settings
from pipeline.select_topic import TopicChoice

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
    cleaned = re.sub(r',(\s*[}\]])', r'\1', cleaned)
    
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    
    # Pass 2: Remove common quote/escape issues
    # Replace smart quotes with regular quotes
    cleaned = cleaned.replace('"', '"').replace('"', '"').replace(''', "'").replace(''', "'")
    
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    
    # Pass 3: Handle incomplete/truncated JSON by finding last valid closing brace
    # Count braces to find where JSON structure breaks
    brace_depth = 0
    bracket_depth = 0
    in_string = False
    escape_next = False
    last_valid_pos = -1
    
    for i, char in enumerate(cleaned):
        if escape_next:
            escape_next = False
            continue
        
        if char == '\\':
            escape_next = True
            continue
        
        if char == '"' and not escape_next:
            in_string = not in_string
            continue
        
        if in_string:
            continue
        
        if char == '{':
            brace_depth += 1
            last_valid_pos = i
        elif char == '}':
            brace_depth -= 1
            if brace_depth == 0:
                last_valid_pos = i
        elif char == '[':
            bracket_depth += 1
        elif char == ']':
            bracket_depth -= 1
    
    # If we found a valid closing brace, truncate there
    if last_valid_pos > 0 and brace_depth == 0:
        truncated = cleaned[:last_valid_pos + 1]
        try:
            return json.loads(truncated)
        except json.JSONDecodeError:
            pass
    
    # Pass 4: Try to fix dialogue array specifically (most common issue)
    # Look for "dialogue": [ ... incomplete
    dialogue_match = re.search(r'"dialogue"\s*:\s*\[(.*?)(?=,\s*"|\})', cleaned, re.DOTALL)
    if dialogue_match:
        LOGGER.warning("Attempting to reconstruct partial dialogue array")
        # This is complex - better to fail than return broken data
        pass
    
    raise ValueError(f"Failed to parse JSON after cleanup attempts: {str(first_error)}")



def _prompt_for_topic(topic: TopicChoice, language: str, level: str = "A1", skill_type: str = "listening") -> str:
    base_prompt = (settings.ROOT / "prompts/base_template.md").read_text(encoding="utf-8")

    skill_prompt_path = settings.ROOT / f"prompts/{level}/{skill_type}.md"
    if not skill_prompt_path.exists():
        raise FileNotFoundError(
            f"No prompt found for level={level!r} skill={skill_type!r}. "
            f"Expected: {skill_prompt_path}"
        )
    skill_prompt = skill_prompt_path.read_text(encoding="utf-8")

    lang_instructions = {
        "nl": "Generate dialogue in Dutch. All vocabulary should have 'nl' and 'en' translations.",
        "en": "Generate dialogue in English. All vocabulary should have 'en' and 'nl' translations.",
    }

    lang_instr = lang_instructions.get(language, lang_instructions["nl"])

    return (
        f"{base_prompt}\n\n"
        f"{skill_prompt}\n"
        f"\n{lang_instr}\n"
        f"Topic id: {topic.topic_id}\n"
        f"Topic hint: {topic.title_hint}\n"
        f"Track: {topic.track}\n"
        f'Set the "language" field in JSON to "{language}".\n'
        f"Keep content at CEFR {level} and output strict JSON only."
    )





def generate_script(topic: TopicChoice, language: str = "nl", level: str = "A1", skill_type: str = "listening") -> dict[str, Any]:
    prompt = _prompt_for_topic(topic, language, level=level, skill_type=skill_type)

    # Try Gemini first (handles long JSON outputs reliably), fall back to Ollama
    if settings.GEMINI_API_KEY:
        try:
            return _generate_script_gemini(prompt)
        except Exception as e:
            LOGGER.warning("Gemini script generation failed, falling back to Ollama: %s", str(e))

    return _generate_script_ollama(prompt)


def _generate_script_gemini(prompt: str) -> dict[str, Any]:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    models_to_try = ["gemini-3.5-flash-lite", "gemini-2.5-flash", "gemini-2.0-flash"]

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
                LOGGER.warning("Empty response from %s, trying next model", model_name)
                continue
            LOGGER.info("Script generated via Gemini model=%s chars=%d", model_name, len(model_output))
            return _extract_json(model_output)
        except Exception as e:
            LOGGER.warning("Gemini model %s failed: %s", model_name, str(e))
            continue

    raise RuntimeError("All Gemini models failed for script generation")


def _generate_script_ollama(prompt: str) -> dict[str, Any]:
    payload = {
        "model": settings.OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
    }

    url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/generate"

    response = requests.post(url, json=payload, timeout=180)
    response.raise_for_status()
    model_output = response.json().get("response", "")
    script = _extract_json(model_output)
    return script
