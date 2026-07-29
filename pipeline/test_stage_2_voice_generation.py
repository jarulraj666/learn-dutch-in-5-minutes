#!/usr/bin/env python3
"""Test Stage 2: Voice Generation (Parkiet TTS)

Run: python -m pipeline.test_stage_2_voice_generation
"""
import json
import logging
from pathlib import Path

from pipeline import settings
from pipeline.generate_voice import generate_voice_assets

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
LOGGER = logging.getLogger(__name__)


def main():
    LOGGER.info("=== TEST STAGE 2: Voice Generation (Parkiet TTS) ===")
    LOGGER.info("This stage generates audio segments using Parkiet Dutch TTS")
    LOGGER.info("Note: First run will download Parkiet model (~1.6GB), may take 10-15 minutes")

    # Load script from stage 1
    script_file = Path(settings.OUTPUT_DIR) / "test_stage_1_script.json"
    if not script_file.exists():
        LOGGER.error("Script file not found: %s", script_file)
        LOGGER.error("Please run Stage 1 first: python -m pipeline.test_stage_1_script_generation")
        return

    script = json.loads(script_file.read_text(encoding="utf-8"))
    LOGGER.info("✓ Loaded script: %d dialogue lines, language=%s", 
               len(script.get("dialogue", [])), script.get("language"))

    # Generate voice assets
    out_dir = Path(settings.OUTPUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    LOGGER.info("\nGenerating voice assets with Parkiet TTS...")
    try:
        voice_plan = generate_voice_assets(script, output_root=str(out_dir))
        LOGGER.info("✓ Voice generation complete")

        # Show results
        segments = voice_plan.get("voice_segments", [])
        LOGGER.info("\n=== VOICE GENERATION RESULTS ===")
        LOGGER.info("Generated segments: %d", len(segments))
        
        for i, segment in enumerate(segments, 1):
            audio_file = segment.get("audio_file", "")
            speaker = segment.get("speaker", "")
            duration = segment.get("duration_seconds", 0)
            LOGGER.info("  %d. %s [%s] %.2f sec", i, Path(audio_file).name, speaker, duration)

        # Save voice plan for next stage
        voice_file = Path(settings.OUTPUT_DIR) / "test_stage_2_voice_plan.json"
        voice_file.write_text(json.dumps(voice_plan, ensure_ascii=False, indent=2), encoding="utf-8")
        LOGGER.info("\n✓ Voice plan saved to: %s", voice_file)
        
        LOGGER.info("\n✅ Parkiet TTS is working correctly!")
        LOGGER.info("📝 For next stage, run: python -m pipeline.test_stage_3_subtitle_generation")

    except Exception as e:
        LOGGER.error("❌ Voice generation failed: %s", str(e))
        LOGGER.error("\nTroubleshooting:")
        LOGGER.error("- Check Parkiet model download progress")
        LOGGER.error("- Ensure at least 10GB RAM available")
        LOGGER.error("- Check internet connection for model download")
        LOGGER.error("- Review config/pedagogy.yaml for language_provider_map")
        raise


if __name__ == "__main__":
    main()
