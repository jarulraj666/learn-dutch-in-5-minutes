#!/usr/bin/env python3
"""Test Stage 4: Video Rendering

Run: python -m pipeline.test_stage_4_video_rendering
"""
import json
import logging
from pathlib import Path

from pipeline import settings
from pipeline.render_video import render_from_artifact

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
LOGGER = logging.getLogger(__name__)


def main():
    LOGGER.info("=== TEST STAGE 4: Video Rendering ===")
    LOGGER.info("This stage assembles audio, subtitles, and images into final MP4 video")

    # Load voice plan from stage 3
    voice_file = Path(settings.OUTPUT_DIR) / "test_stage_2_voice_plan.json"
    if not voice_file.exists():
        LOGGER.error("Voice file not found: %s", voice_file)
        LOGGER.error("Please run Stage 2 first: python -m pipeline.test_stage_2_voice_generation")
        return

    voice_plan = json.loads(voice_file.read_text(encoding="utf-8"))
    LOGGER.info("✓ Loaded voice plan: %d segments", len(voice_plan.get("voice_segments", [])))

    # Load script for metadata
    script_file = Path(settings.OUTPUT_DIR) / "test_stage_1_script.json"
    script = json.loads(script_file.read_text(encoding="utf-8")) if script_file.exists() else {}
    
    # Load subtitle plan from stage 4
    subtitle_file = Path(settings.OUTPUT_DIR) / "test_stage_3_subtitle_plan.json"
    subtitle_plan = json.loads(subtitle_file.read_text(encoding="utf-8")) if subtitle_file.exists() else {}

    # Create a minimal artifact for rendering
    artifact = {
        "voice": voice_plan,
        "subtitles": subtitle_plan,
        "script": script,
        "metadata": {
            "title": script.get("topic_title", "Lesson"),
            "description": "Test video",
        }
    }

    out_dir = Path(settings.OUTPUT_DIR)
    artifact_path = out_dir / "test_stage_4_artifact.json"
    artifact_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")

    LOGGER.info("\nRendering video from artifact...")
    try:
        render_manifest_path = render_from_artifact(artifact_path)
        render_manifest = json.loads(render_manifest_path.read_text(encoding="utf-8"))

        LOGGER.info("\n=== VIDEO RENDERING RESULTS ===")
        LOGGER.info("Render manifest: %s", render_manifest_path)
        LOGGER.info("Status: %s", "ASSEMBLED" if render_manifest.get("assembled") else "FAILED")
        
        if render_manifest.get("assembled"):
            video_file = render_manifest.get("planned_video_file", "")
            LOGGER.info("Video file: %s", video_file)
            if Path(video_file).exists():
                size_mb = Path(video_file).stat().st_size / (1024 * 1024)
                LOGGER.info("File size: %.1f MB", size_mb)
            LOGGER.info("\n✅ Video rendered successfully!")
        else:
            LOGGER.warning("Video rendering failed")
            LOGGER.info("Error details: %s", render_manifest.get("error", "Unknown error"))

        # Save render manifest
        render_file = Path(settings.OUTPUT_DIR) / "test_stage_4_render_manifest.json"
        render_file.write_text(json.dumps(render_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        LOGGER.info("\n✓ Render manifest saved to: %s", render_file)

    except Exception as e:
        LOGGER.error("❌ Video rendering failed: %s", str(e))
        raise


if __name__ == "__main__":
    main()
