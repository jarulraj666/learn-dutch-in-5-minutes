#!/usr/bin/env python3
"""Test Stage 3c: Karaoke/SRT Generation from STT Segments

Run: python -m pipeline.test_stage_3c_karaoke_generation
"""

import json
import logging
from pathlib import Path

from pipeline import settings
from pipeline.generate.generate_subtitles import generate_karaoke_from_segments

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
LOGGER = logging.getLogger(__name__)


def main() -> None:
    LOGGER.info("=== TEST STAGE 3c: Karaoke Generation from STT Segments ===")

    out_dir = Path(settings.OUTPUT_DIR)
    stage_3a_file = out_dir / "test_stage_3a_stt_segments.json"

    if not stage_3a_file.exists():
        LOGGER.error("Stage 3a output not found: %s", stage_3a_file)
        LOGGER.error("Please run Stage 3a first: python -m pipeline.test_stage_3a_speech_to_text")
        return

    payload = json.loads(stage_3a_file.read_text(encoding="utf-8"))
    segments = payload.get("segments", [])
    ctx = payload.get("_pipeline_context", {})

    topic_id = ctx.get("topic_id", "test")
    level = ctx.get("level", "A1A2")
    category = ctx.get("category", "dialogue")
    title_slug = ctx.get("title_slug", "lesson")

    if not isinstance(segments, list) or not segments:
        LOGGER.error("No transcript segments found in %s", stage_3a_file)
        return

    LOGGER.info("✓ Loaded STT segments: %d", len(segments))
    LOGGER.info(
        "Context: level=%s category=%s topic_id=%s slug=%s",
        level,
        category,
        topic_id,
        title_slug,
    )

    subtitle_files = generate_karaoke_from_segments(
        segments=segments,
        output_root=str(out_dir),
        level=level,
        category=category,
        topic_id=topic_id,
        title_slug=title_slug,
    )

    subtitle_plan = {
        "karaoke_file": subtitle_files.get("ass_karaoke", ""),
        "srt_en": subtitle_files.get("en", ""),
        "srt_files": subtitle_files,
        "_pipeline_context": {
            "topic_id": topic_id,
            "level": level,
            "category": category,
            "title_slug": title_slug,
        },
    }

    subtitle_file = out_dir / "test_stage_3_subtitle_plan.json"
    subtitle_file.write_text(json.dumps(subtitle_plan, ensure_ascii=False, indent=2), encoding="utf-8")

    LOGGER.info("✓ Karaoke ASS file: %s", subtitle_files.get("ass_karaoke", ""))
    LOGGER.info("✓ English SRT file: %s", subtitle_files.get("en", ""))
    LOGGER.info("✓ Subtitle plan saved to: %s", subtitle_file)


if __name__ == "__main__":
    main()
