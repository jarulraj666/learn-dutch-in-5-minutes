"""Generate provider-specific expression tags for TTS dialogue."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from pipeline import settings
from pipeline.clients.tts_provider_factory import normalize_provider_name
from pipeline.utils import iter_dialogue_turns

LOGGER = logging.getLogger(__name__)


_ELEVENLABS_BREAK_TAG = '<break time="0.7s"/>'
_ELEVENLABS_OLD_PAUSE_CUE_RE = re.compile(
    r"\s*(?:\.\.\.|\[short pause\]|\[pause\]|\[pause for 1 second\])\s*$",
    re.IGNORECASE,
)


def _spoken_elevenlabs_line(line: str) -> str:
    return _ELEVENLABS_OLD_PAUSE_CUE_RE.sub("", line.replace(_ELEVENLABS_BREAK_TAG, "").rstrip())


def _with_elevenlabs_break_tag(line: str) -> str:
    """End a Flash v2.5 dialogue line with a 0.7-second SSML break."""
    return f"{_spoken_elevenlabs_line(line)}{_ELEVENLABS_BREAK_TAG}"


def _add_elevenlabs_break_tags(dialogue: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Ensure each Flash v2.5 dialogue turn ends with a 0.7-second break."""
    return [
        {speaker: _with_elevenlabs_break_tag(line)}
        for speaker, line in iter_dialogue_turns(dialogue)
    ]


def add_expression_tags(
    dialogue: list[dict[str, Any]], provider_name: str
) -> list[dict[str, str]]:
    """Add LLM-selected provider tags to a temporary TTS-only dialogue copy."""
    provider_name = normalize_provider_name(provider_name)
    if provider_name == "elevenlabs":
        return _add_elevenlabs_break_tags(dialogue)

    expression_cfg = settings.PEDAGOGY_CONFIG.get("speech", {}).get("expression_tags", {})
    provider_cfg = expression_cfg.get(provider_name, {}) if isinstance(expression_cfg, dict) else {}
    if not isinstance(provider_cfg, dict) or not provider_cfg.get("enabled", False):
        return dialogue

    turns = iter_dialogue_turns(dialogue)
    seeded_turns = [
        (
            speaker,
            f"[slow] {line}".strip(),
        )
        for speaker, line in turns
    ]
    prompt = (
        "You are a TTS director. Add expressive audio tags to the dialogue for the "
        f"{provider_name} voice provider. Choose tags yourself based on each line's "
        "meaning, emotion, and conversational context. Use only tags supported by "
        "that provider, such as [excited], [sad], [angry], [curious], [whispers], "
        "[laughs], [sighs], [short pause], or [long pause] when appropriate. "
        "CRITICAL: every single dialogue line must include [slow] plus an expressive tag. "
        "Keep [slow] on every line exactly as provided. "
        "Keep every other supplied tag exactly as provided. "
        "Add at least one additional expressive tag per line (for example [curious], [excited], [serious], [laughs], [sighs], [whispers]). "
        "Put tags before spoken text. "
        "Keep every speaker, line count, and spoken word exactly unchanged. "
        "Return ONLY a JSON array in the same {SpeakerX: text} structure. "
        "Tags are instructions and must be placed in the text, but do not add commentary.\n\n"
        f"DIALOGUE: {json.dumps([{speaker: line} for speaker, line in seeded_turns], ensure_ascii=False)}"
    )

    try:
        from pipeline.generate.generate_script import _generate_script_gemini

        result = _generate_script_gemini(prompt)
        generated = result.get("dialogue", []) if isinstance(result, dict) else result
        generated_turns = iter_dialogue_turns(generated)
        if len(generated_turns) != len(turns):
            raise ValueError("LLM returned a different number of dialogue turns")

        tag_pattern = re.compile(r"\[[^\]]+\]")
        enriched: list[dict[str, str]] = []
        for (speaker, line), (generated_speaker, generated_line) in zip(turns, generated_turns):
            if speaker != generated_speaker:
                raise ValueError("LLM changed a dialogue speaker")
            selected_tags = tag_pattern.findall(generated_line)
            has_slow_tag = any(tag.strip().lower() == "[slow]" for tag in selected_tags)
            has_expression_tag = any("slow" not in tag.lower() for tag in selected_tags)
            if not has_slow_tag or not has_expression_tag:
                raise ValueError("LLM output missing required [slow] and expressive tags on a line")
            spoken_text = tag_pattern.sub("", generated_line).strip()
            if spoken_text != line:
                raise ValueError("LLM changed spoken dialogue text")
            enriched.append({speaker: f"{' '.join(dict.fromkeys(selected_tags))} {line}".strip()})
        return enriched
    except Exception as err:
        LOGGER.warning(
            "tts.expression_tags: LLM enrichment failed for %s; using plain dialogue: %s",
            provider_name,
            err,
        )
        return dialogue