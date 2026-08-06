"""Generate Voice Assets Module.

Handles dialogue audio generation using configurable TTS providers with
automatic fallback support.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

from pipeline import settings
from pipeline.clients.tts_provider_factory import create_tts_client, normalize_provider_name
from pipeline.utils import command_exists

LOGGER = logging.getLogger(__name__)


def _resolve_provider_order(category: str) -> list[str]:
    """Return ordered providers to try for the given category."""
    primary = normalize_provider_name(settings.TTS_PROVIDER)
    fallback = normalize_provider_name(settings.TTS_FALLBACK_PROVIDER)

    # Keep non-dialogue categories on Gemini for now.
    if category != "dialogue":
        return ["gemini"]

    providers: list[str] = [primary]
    if fallback and fallback != primary:
        providers.append(fallback)
    return providers


def _clamp_speed(speed: float) -> float:
    if speed < 0.5:
        return 0.5
    if speed > 2.0:
        return 2.0
    return speed


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

    # Build speaker gender and role maps from script metadata
    speaker_genders: dict[str, str] = {}
    speaker_roles: dict[str, str] = {}
    for s in script.get("speakers", []):
        sid = s.get("id", "")
        if sid:
            speaker_genders[sid] = s.get("gender", "")
            speaker_roles[sid] = s.get("role", "")

    voice_dir = Path(output_root) / "audio"
    voice_dir.mkdir(parents=True, exist_ok=True)

    audio_filename = f"episode_{topic_id}_{title_slug}.wav"
    
    raw_audio_path = Path(voice_dir / audio_filename)
    dialogue_audio_path = str(raw_audio_path)

    LOGGER.info(
        "Generating voice assets for %d line(s) (Language: %s, Level: %s, File: %s)",
        len(dialogue),
        language,
        script_level,
        audio_filename,
    )

    success = False
    used_provider = ""
    providers_to_try = _resolve_provider_order(category)
    LOGGER.info("tts.providers.try_order=%s", providers_to_try)

    errors: list[str] = []
    for provider_name in providers_to_try:
        try:
            client = create_tts_client(provider_name)
        except Exception as err:
            msg = f"init {provider_name} failed: {err}"
            LOGGER.warning(msg)
            errors.append(msg)
            continue

        LOGGER.info("tts.provider.attempt=%s", provider_name)
        success = client.generate_dialogue_audio(
            dialogue=dialogue,
            output_path=dialogue_audio_path,
            level=script_level,
            category=category,
            speaker_genders=speaker_genders,
            speaker_roles=speaker_roles,
        )
        if success:
            used_provider = getattr(client, "provider_name", provider_name)
            break

        msg = f"generation failed for provider={provider_name}"
        LOGGER.warning(msg)
        errors.append(msg)

    if not success:
        raise RuntimeError(
            "TTS failed for all providers. "
            f"tried={providers_to_try} errors={'; '.join(errors) if errors else 'none'}"
        )

    render_cfg = settings.load_yaml(settings.ROOT / "config/visual_style.yaml").get("render", {})
    speed_cfg = render_cfg.get("playback_speed", {})
    if isinstance(speed_cfg, dict):
        raw_speed = speed_cfg.get(category, speed_cfg.get("default", 1.0))
    else:
        raw_speed = speed_cfg
    configured_speed = _clamp_speed(float(raw_speed))
    dialogue_audio_path = str(raw_audio_path)

    LOGGER.info("✓ Full dialogue audio generated and saved: %s", dialogue_audio_path)

    return {
        "provider": used_provider,
        "audio_dir": str(voice_dir),
        "dialogue_audio": dialogue_audio_path,
        "dialogue_audio_raw": str(raw_audio_path),
        "dialogue_type": "full_conversation",
        "playback_speed": configured_speed,
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