"""
Generate Voice Assets Module

Handles dialogue audio generation using GeminiTTSClient with automatic 
chunking and settings-driven voice configuration.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pipeline import settings
from pipeline.clients.gemini_tts_client import create_gemini_client

LOGGER = logging.getLogger(__name__)


def generate_voice_assets(
    script: dict[str, Any],
    output_root: str,
    level: str,
    category: str,
    topic_id: str,
    title_slug: str,
) -> dict[str, Any]:
    """Generates audio files for a dialogue script.

    Args:
        script: Dictionary containing 'dialogue', 'language', and 'level'.
        output_root: Root directory path for output files.
        level: CEFR level (A1, A2, B1, B2).
        category: Content category (common_words, dialogue, etc.).
        topic_id: Topic ID used in the output filename.
        title_slug: URL-safe title slug used in the output filename.

    Returns:
        Dictionary containing execution metadata and the output file path.
    """
    dialogue = script.get("dialogue", [])
    if not dialogue:
        raise ValueError("Script must contain a non-empty 'dialogue' list.")

    speech_cfg = settings.PEDAGOGY_CONFIG.get("speech", {})
    language = script.get("language") or speech_cfg.get("language", "nl")
    script_level = level or script.get("level", "A1")

    voice_dir = Path(output_root) / "audio"
    voice_dir.mkdir(parents=True, exist_ok=True)

    audio_filename = f"episode_{topic_id}_{title_slug}.wav"
    
    dialogue_audio_path = str(voice_dir / audio_filename)

    api_key = getattr(settings, "GEMINI_TTS_API_KEY", None)
    if not api_key:
        raise RuntimeError("GEMINI_TTS_API_KEY is missing from pipeline settings.")

    client = create_gemini_client(api_key)
    if not client:
        raise RuntimeError("Failed to initialize GeminiTTSClient.")

    LOGGER.info(
        "Generating voice assets for %d line(s) (Language: %s, Level: %s, File: %s)",
        len(dialogue),
        language,
        script_level,
        audio_filename,
    )

    success = client.generate_dialogue_audio(
        dialogue=dialogue,
        output_path=dialogue_audio_path,
        level=script_level,
    )

    if not success:
        raise RuntimeError("Gemini TTS failed to generate complete dialogue audio.")

    LOGGER.info("✓ Full dialogue audio generated and saved: %s", dialogue_audio_path)

    return {
        "provider": "gemini",
        "audio_dir": str(voice_dir),
        "dialogue_audio": dialogue_audio_path,
        "dialogue_type": "full_conversation",
        "line_count": len(dialogue),
    }


def plan_voice_assets(
    script: dict[str, Any],
    output_root: str = "output",
    level: str = "A1",
    category: str = "dialogue",
    topic_id: str = "unknown",
    title_slug: str = "lesson",
) -> dict[str, Any]:
    """Alias function to execute voice asset generation."""
    return generate_voice_assets(
        script,
        output_root=output_root,
        level=level,
        category=category,
        topic_id=topic_id,
        title_slug=title_slug,
    )


if __name__ == "__main__":
    # Example standalone execution for testing
    logging.basicConfig(level=logging.INFO)

    sample_script = {
        "language": "nl",
        "level": "A1",
        "dialogue": [
            {"Speaker1" : "Hallo! Welkom bij de les van vandaag."},
            { "Speaker2" : "Hallo docent, ik ben er klaar voor."},
        ],
    }

    try:
        result = generate_voice_assets(
            sample_script,
            output_root="output",
            level="A1",
            category="dialogue",
            topic_id="test_001",
            title_slug="sample_lesson",
        )
        print("Asset Generation Result:", result)
    except Exception as err:
        LOGGER.error("Execution failed: %s", err)