#!/usr/bin/env python3
"""Test Stage 3a: Speech-to-Text Extraction (WhisperX)

Run: python -m pipeline.test_stage_3a_speech_to_text
"""

import json
import logging
from pathlib import Path

from pipeline import settings
from pipeline.generate_subtitles import transcribe_audio_segments

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
LOGGER = logging.getLogger(__name__)


def _load_context(out_dir: Path) -> tuple[str, str, str, str, str]:
    script_file = out_dir / "test_stage_1_script.json"

    topic_id = "test"
    level = "A1"
    category = "dialogue"
    title_slug = "lesson"
    language = "nl"

    if script_file.exists():
        script = json.loads(script_file.read_text(encoding="utf-8"))
        ctx = script.get("_pipeline_context", {})
        topic_id = ctx.get("topic_id", topic_id)
        level = ctx.get("level", level)
        category = ctx.get("category", category)
        title_slug = ctx.get("title_slug", title_slug)
        language = script.get("language", language)

    return topic_id, level, category, title_slug, language


def _resolve_audio_path(out_dir: Path, topic_id: str, level: str, category: str, title_slug: str) -> Path:
    voice_file = out_dir / "test_stage_2_voice_plan.json"
    if voice_file.exists():
        voice_plan = json.loads(voice_file.read_text(encoding="utf-8"))
        wav_path = voice_plan.get("dialogue_audio", "")
        wav_file = Path(wav_path) if wav_path else None
    else:
        wav_file = None

    if not wav_file or not wav_file.exists():
        wav_file = out_dir / level / category / "audio" / f"episode_{topic_id}_{title_slug}.wav"

    return wav_file


def main() -> None:
    LOGGER.info("=== TEST STAGE 3a: Speech-to-Text (WhisperX) ===")

    out_dir = Path(settings.OUTPUT_DIR)
    topic_id, level, category, title_slug, language = _load_context(out_dir)
    wav_file = _resolve_audio_path(out_dir, topic_id, level, category, title_slug)

    if not wav_file.exists():
        LOGGER.error("WAV audio file not found: %s", wav_file)
        LOGGER.error("Please run Stage 2 first: python -m pipeline.test_stage_2_voice_generation")
        return

    LOGGER.info("✓ Found audio file: %s", wav_file)
    LOGGER.info(
        "Context: level=%s category=%s topic_id=%s slug=%s language=%s",
        level,
        category,
        topic_id,
        title_slug,
        language,
    )

    script_dialogue = None
    script_file = out_dir / "test_stage_1_script.json"
    if script_file.exists():
        script = json.loads(script_file.read_text(encoding="utf-8"))
        script_dialogue = script.get("dialogue")

    LOGGER.info("\nExtracting transcript segments with timestamps...")
    segments = transcribe_audio_segments(
        wav_path=wav_file,
        language=language,
        script_dialogue=script_dialogue,
    )

    stage_3a_file = out_dir / "test_stage_3a_stt_segments.json"
    stage_3a_file.write_text(
        json.dumps(
            {
                "segments": segments,
                "_pipeline_context": {
                    "topic_id": topic_id,
                    "level": level,
                    "category": category,
                    "title_slug": title_slug,
                    "language": language,
                    "audio_file": str(wav_file),
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    LOGGER.info("✓ STT segments extracted: %d", len(segments))
    LOGGER.info("✓ Stage 3a output saved to: %s", stage_3a_file)


if __name__ == "__main__":
    main()
