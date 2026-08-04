#!/usr/bin/env python3
"""Test Stage 3: Subtitle Generation from Audio (No Script Required)

Run: python -m pipeline.test_stage_3_subtitle_generation
"""
import json
import logging
from pathlib import Path

from pipeline import settings
from pipeline.generate.generate_subtitles import plan_subtitles

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
LOGGER = logging.getLogger(__name__)


def main():
    LOGGER.info("=== TEST STAGE 3: Audio-Direct Subtitle Generation ===")

    out_dir = Path(settings.OUTPUT_DIR)

    # Load pipeline context from voice plan
    voice_file = out_dir / "test_stage_2_voice_plan.json"
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

    # Determine audio path from voice plan or hierarchical default
    if voice_file.exists():
        voice_plan = json.loads(voice_file.read_text(encoding="utf-8"))
        wav_path = voice_plan.get("dialogue_audio", "")
        wav_file = Path(wav_path) if wav_path else None
    else:
        wav_file = None

    # Fallback to expected hierarchical path
    if not wav_file or not wav_file.exists():
        wav_file = out_dir / level / category / "audio" / f"episode_{topic_id}_{title_slug}.wav"

    if not wav_file.exists():
        LOGGER.error("WAV audio file not found: %s", wav_file)
        LOGGER.error("Please run Stage 2 first: python -m pipeline.test_stage_2_voice_generation")
        return

    LOGGER.info("✓ Found audio file: %s", wav_file)
    LOGGER.info("Context: level=%s category=%s topic_id=%s slug=%s language=%s", level, category, topic_id, title_slug, language)

    # Load script dialogue for exact text alignment (avoids Whisper transcription errors)
    script_dialogue = None
    if script_file.exists():
        script = json.loads(script_file.read_text(encoding="utf-8"))
        script_dialogue = script.get("dialogue")
        if script_dialogue:
            LOGGER.info("✓ Script loaded: %d dialogue lines for text alignment", len(script_dialogue))
        else:
            LOGGER.info("Script has no dialogue — falling back to Whisper transcription")

    # Generate karaoke subtitles: Whisper timing + script text (or Whisper-only if no script)
    LOGGER.info("\nGenerating karaoke subtitles (script-aligned)...")
    subtitle_plan = plan_subtitles(
        wav_path=str(wav_file),
        output_root=str(out_dir),
        level=level,
        category=category,
        topic_id=topic_id,
        title_slug=title_slug,
        language=language,
        script_dialogue=script_dialogue,
    )

    # Show results
    karaoke_file = subtitle_plan.get("karaoke_file")
    LOGGER.info("\n=== SUBTITLE GENERATION RESULTS ===")
    LOGGER.info("Karaoke ASS file: %s", karaoke_file)

    if karaoke_file and Path(karaoke_file).exists():
        ass_content = Path(karaoke_file).read_text(encoding="utf-8")
        LOGGER.info("\nFirst few lines of generated ASS file:\n")
        LOGGER.info(ass_content[:700] + ("..." if len(ass_content) > 700 else ""))
        LOGGER.info("\n✓ Karaoke subtitles generated successfully!")
    else:
        LOGGER.warning("No Karaoke ASS file generated")

    # Save plan for stage 4 (include pipeline context)
    subtitle_plan["_pipeline_context"] = {
        "topic_id": topic_id,
        "level": level,
        "category": category,
        "title_slug": title_slug,
    }
    subtitle_file = out_dir / "test_stage_3_subtitle_plan.json"
    subtitle_file.write_text(json.dumps(subtitle_plan, ensure_ascii=False, indent=2), encoding="utf-8")
    LOGGER.info("✓ Subtitle plan saved to: %s", subtitle_file)


if __name__ == "__main__":
    main()