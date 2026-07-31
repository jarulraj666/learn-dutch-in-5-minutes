from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pipeline import settings

LOGGER = logging.getLogger(__name__)

try:
    from pipeline.gemini_tts_client import create_gemini_client
    GEMINI_CLIENT_AVAILABLE = True
except ImportError:
    GEMINI_CLIENT_AVAILABLE = False

_gemini_client = None  # Lazy-load Gemini TTS client


def generate_voice_assets(script: dict[str, Any], output_root: str = "output") -> dict[str, Any]:
    dialogue = script.get("dialogue", [])
    voice_dir = f"{output_root}/audio"
    Path(voice_dir).mkdir(parents=True, exist_ok=True)

    speech_cfg = settings.PEDAGOGY_CONFIG.get("speech", {})
    language = script.get("language") or speech_cfg.get("language", "nl")
    level = script.get("level", "A1")

    # Lazy-load Gemini TTS client
    global _gemini_client
    if _gemini_client is None and GEMINI_CLIENT_AVAILABLE and settings.GEMINI_API_KEY:
        _gemini_client = create_gemini_client(settings.GEMINI_API_KEY)

    if not _gemini_client:
        raise RuntimeError("Gemini TTS client is not available. Check GEMINI_API_KEY.")

    dialogue_audio_path = f"{voice_dir}/dialogue_full.wav"

    LOGGER.info(
        "Generating full dialogue audio (%d lines) via Gemini TTS",
        len(dialogue),
    )
    success = _gemini_client.generate_dialogue_audio(
        dialogue=dialogue,
        output_path=dialogue_audio_path,
        language=language,
        level=level,
    )

    if not success:
        raise RuntimeError("Gemini TTS failed to generate dialogue audio.")

    LOGGER.info("✓ Full dialogue audio saved: %s", dialogue_audio_path)

    return {
        "provider": "gemini",
        "audio_dir": voice_dir,
        "dialogue_audio": dialogue_audio_path,
        "dialogue_type": "full_conversation",
        "line_count": len(dialogue),
    }


def plan_voice_assets(script: dict[str, Any]) -> dict[str, Any]:
    return generate_voice_assets(script)


