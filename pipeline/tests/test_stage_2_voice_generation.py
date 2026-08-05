#!/usr/bin/env python3
"""Test Stage 2: Voice Generation (Configured TTS Provider)

Run: python -m pipeline.test_stage_2_voice_generation
"""

import json
import logging
from pathlib import Path

from pipeline import settings
from pipeline.generate.generate_voice import generate_voice_assets

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
LOGGER = logging.getLogger(__name__)


def main():
    LOGGER.info("=== TEST STAGE 2: Voice Generation (Configured TTS Provider) ===")

    # Load script from Stage 1 output
    out_dir = Path(settings.OUTPUT_DIR)
    script_file = out_dir / "test_stage_1_script.json"

    if not script_file.exists():
        LOGGER.error("Script file not found: %s", script_file)
        LOGGER.error("Please run Stage 1 first: python -m pipeline.test_stage_1_script_generation")
        return

    script = json.loads(script_file.read_text(encoding="utf-8"))
    ctx = script.get("_pipeline_context", {})
    topic_id = ctx.get("topic_id", "test")
    level = ctx.get("level", "A1")
    category = ctx.get("category", "dialogue")
    title_slug = ctx.get("title_slug", "lesson")
    LOGGER.info(
        "✓ Loaded script: %d dialogue lines, language=%s, level=%s, category=%s, slug=%s",
        len(script.get("dialogue", [])),
        script.get("language", "nl"),
        level,
        category,
        title_slug,
    )

    LOGGER.info(
        "Generating voice assets (provider=%s, fallback=%s)...",
        settings.TTS_PROVIDER,
        settings.TTS_FALLBACK_PROVIDER,
    )
    try:
        voice_plan = generate_voice_assets(
            script,
            output_root=str(out_dir),
            level=level,
            category=category,
            topic_id=topic_id,
            title_slug=title_slug,
        )
        LOGGER.info("✓ Voice generation complete")

        # Save voice plan for Stage 3
        voice_file = out_dir / "test_stage_2_voice_plan.json"
        voice_file.write_text(json.dumps(voice_plan, ensure_ascii=False, indent=2), encoding="utf-8")

        LOGGER.info("\n=== VOICE GENERATION RESULTS ===")
        LOGGER.info("Provider used: %s", voice_plan.get("provider", "unknown"))
        LOGGER.info("Audio saved to: %s", voice_plan.get("dialogue_audio"))
        LOGGER.info("✓ Voice plan saved to: %s", voice_file)
        LOGGER.info("\n✅ TTS generation is working correctly!")
        LOGGER.info("📝 Next stage: python -m pipeline.test_stage_3_subtitle_generation")

    except Exception as e:
        LOGGER.error("❌ Voice generation failed: %s", e)
        LOGGER.error("\nTroubleshooting:")
        LOGGER.error("- Verify TTS_PROVIDER and TTS_FALLBACK_PROVIDER in .env")
        LOGGER.error("- If using Gemini: verify GEMINI_TTS_API_KEY (or GEMINI_API_KEY)")
        LOGGER.error("- If using ElevenLabs: verify ELEVENLABS_API_KEY and voice IDs in config/pedagogy.yaml")
        LOGGER.error("- Check network connectivity to provider APIs")
        raise


if __name__ == "__main__":
    main()