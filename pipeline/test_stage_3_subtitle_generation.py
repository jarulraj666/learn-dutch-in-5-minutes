#!/usr/bin/env python3
"""Test Stage 3: Subtitle Generation

Run: python -m pipeline.test_stage_3_subtitle_generation
"""
import json
import logging
from pathlib import Path

from pipeline import settings
from pipeline.generate_subtitles import plan_subtitles

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
LOGGER = logging.getLogger(__name__)


def main():
    LOGGER.info("=== TEST STAGE 3: Subtitle Generation ===")
    LOGGER.info("This stage generates bilingual subtitles for the dialogue")

    # Load script from stage 1
    script_file = Path(settings.OUTPUT_DIR) / "test_stage_1_script.json"
    if not script_file.exists():
        LOGGER.error("Script file not found: %s", script_file)
        LOGGER.error("Please run Stage 1 first: python -m pipeline.test_stage_1_script_generation")
        return

    script = json.loads(script_file.read_text(encoding="utf-8"))
    LOGGER.info("✓ Loaded script: %d dialogue lines", len(script.get("dialogue", [])))

    # Generate subtitles
    LOGGER.info("\nGenerating bilingual subtitles...")
    subtitle_plan = plan_subtitles(script)

    # Show results
    srt_file = subtitle_plan.get("srt_file")
    LOGGER.info("\n=== SUBTITLE GENERATION RESULTS ===")
    LOGGER.info("SRT file: %s", srt_file)

    if srt_file and Path(srt_file).exists():
        srt_content = Path(srt_file).read_text(encoding="utf-8")
        lines = srt_content.split("\n")
        LOGGER.info("SRT file size: %d lines", len(lines))
        LOGGER.info("\nFirst few subtitles:")
        LOGGER.info(srt_content[:500] + ("..." if len(srt_content) > 500 else ""))
        
        LOGGER.info("\n✓ Subtitles generated successfully")
    else:
        LOGGER.warning("No SRT file generated")

    # Save subtitle plan for next stage
    subtitle_file = Path(settings.OUTPUT_DIR) / "test_stage_3_subtitle_plan.json"
    subtitle_file.write_text(json.dumps(subtitle_plan, ensure_ascii=False, indent=2), encoding="utf-8")
    LOGGER.info("✓ Subtitle plan saved to: %s", subtitle_file)
    
    LOGGER.info("\n📝 For final stage, run: python -m pipeline.test_stage_4_video_rendering")


if __name__ == "__main__":
    main()
