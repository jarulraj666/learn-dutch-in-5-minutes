#!/usr/bin/env python3
"""Test Stage 4: Video Rendering with Karaoke Subtitles

Run after Stages 2, 3, and 3b.
Run: python -m pipeline.test_stage_4_video_rendering
"""
import json
import logging
from pathlib import Path

from pipeline import settings
from pipeline.publish.render_video import render_from_artifact

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
LOGGER = logging.getLogger(__name__)


def main():
    LOGGER.info("=== TEST STAGE 4: Video Rendering ===")
    LOGGER.info(
        "This stage renders the final video using pre-generated audio, subtitles, and image"
    )

    out_dir = Path(settings.OUTPUT_DIR)

    # 1. Load script or voice plan to retrieve metadata and image prompt
    script_file = out_dir / "test_stage_1_script.json"
    voice_file = out_dir / "test_stage_2_voice_plan.json"

    if not voice_file.exists():
        LOGGER.error("Voice plan file not found: %s", voice_file)
        LOGGER.error(
            "Please run Stage 2 first: python -m pipeline.test_stage_2_voice_generation"
        )
        return

    voice_plan = json.loads(voice_file.read_text(encoding="utf-8"))
    dialogue_audio_path = voice_plan.get("dialogue_audio", "")

    audio_file = Path(dialogue_audio_path) if dialogue_audio_path else None
    if audio_file and not audio_file.is_absolute():
        audio_file = settings.ROOT / audio_file

    # Load pipeline context and image prompt from script JSON
    image_prompt = ""
    topic_id = "dutch_lesson_1"
    topic_title = "Dutch Lesson"
    level = "A1"
    category = "dialogue"
    title_slug = "lesson"

    if script_file.exists():
        script_data = json.loads(script_file.read_text(encoding="utf-8"))
        image_prompt = script_data.get("image_prompt", "")
        topic_id = script_data.get("topic_id", topic_id)
        topic_title = script_data.get("topic_title", topic_title)
        ctx = script_data.get("_pipeline_context", {})
        topic_id = ctx.get("topic_id", topic_id)
        level = ctx.get("level", level)
        category = ctx.get("category", category)
        title_slug = ctx.get("title_slug", title_slug)

    # Fallback audio path using hierarchical structure
    if not audio_file or not audio_file.exists():
        audio_file = out_dir / level / category / "audio" / f"episode_{topic_id}_{title_slug}.wav"

    if not audio_file.exists():
        LOGGER.error("Audio WAV file not found: %s", audio_file)
        return
    LOGGER.info("✓ Loaded voice plan with audio file: %s", audio_file)
    LOGGER.info("Context: level=%s category=%s topic_id=%s slug=%s", level, category, topic_id, title_slug)

    # 2. Load subtitle plan from Stage 3
    subtitle_file = out_dir / "test_stage_3_subtitle_plan.json"
    if not subtitle_file.exists():
        LOGGER.error("Subtitle plan file not found: %s", subtitle_file)
        LOGGER.error(
            "Please run Stage 3 first: python -m pipeline.test_stage_3_subtitle_generation"
        )
        return

    subtitle_plan = json.loads(subtitle_file.read_text(encoding="utf-8"))
    karaoke_path = subtitle_plan.get("karaoke_file") or subtitle_plan.get(
        "srt_files", {}
    ).get("ass_karaoke")
    LOGGER.info("✓ Loaded subtitle plan with karaoke file: %s", karaoke_path)

    # 3. Resolve pre-generated background image (generated in a dedicated image stage)
    image_file_path = out_dir / level / category / "visuals" / f"episode_{topic_id}_{title_slug}.png"
    if image_file_path.exists():
        LOGGER.info("✓ Found background image: %s", image_file_path)
    else:
        LOGGER.warning("⚠️ Background image not found: %s", image_file_path)
        LOGGER.warning("Run image generation first: python -m pipeline.test_stage_3b_image_generation")
        image_file_path = None

    artifact = {
        "canonical_script_id": 1,
        "level": level,
        "category": category,
        "topic_id": topic_id,
        "title_slug": title_slug,
        "audio_file": str(audio_file),
        "karaoke_file": karaoke_path,
        "image_prompt": image_prompt,
        "generated_image_file": str(image_file_path) if image_file_path else "",
        "srt_files": subtitle_plan.get("srt_files", {}),
        "voice": voice_plan,
        "topic": {
            "id": topic_id,
            "level": level,
            "category": category,
            "title_slug": title_slug,
            "title_hint": topic_title,
        },
        "metadata": {
            "title": topic_title,
            "description": "Rendered video with background image and karaoke subtitles",
        },
    }

    artifact_path = out_dir / "test_stage_4_artifact.json"
    artifact_path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    LOGGER.info("✓ Prepared artifact at: %s", artifact_path)

    # 5. Execute rendering
    LOGGER.info("\nRendering video from artifact...")
    try:
        render_manifest_path = render_from_artifact(artifact_path)
        render_manifest = json.loads(
            render_manifest_path.read_text(encoding="utf-8")
        )

        LOGGER.info("\n=== VIDEO RENDERING RESULTS ===")
        LOGGER.info("Render manifest: %s", render_manifest_path)
        LOGGER.info(
            "Status: %s",
            "ASSEMBLED" if render_manifest.get("assembled") else "FAILED",
        )

        if render_manifest.get("assembled"):
            video_file = render_manifest.get("planned_video_file", "")
            LOGGER.info("Video file: %s", video_file)
            if Path(video_file).exists():
                size_mb = Path(video_file).stat().st_size / (1024 * 1024)
                LOGGER.info("File size: %.1f MB", size_mb)
            LOGGER.info(
                "\n✅ Video rendered successfully with background image and subtitles!"
            )
        else:
            LOGGER.warning("Video rendering failed")
            LOGGER.info(
                "Error details: %s",
                render_manifest.get("render_error", "Unknown error"),
            )

        # Save render manifest summary
        render_file = out_dir / "test_stage_4_render_manifest.json"
        render_file.write_text(
            json.dumps(render_manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        LOGGER.info("✓ Render manifest saved to: %s", render_file)

    except Exception as e:
        LOGGER.error("❌ Video rendering failed: %s", str(e))
        raise


if __name__ == "__main__":
    main()