#!/usr/bin/env python3
"""Test Stage 3b: Background Image Generation (Gemini 2.5 Flash Image)

Run after Stage 1 (script generation). Can run in parallel with Stage 2 & 3.
Run: python -m pipeline.test_stage_3b_image_generation
"""
import json
import logging
from pathlib import Path

from pipeline import settings
from pipeline.generate.generate_visual_image import generate_topic_image

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
LOGGER = logging.getLogger(__name__)


def main():
    LOGGER.info("=== TEST STAGE 3b: Background Image Generation ===")
    LOGGER.info("Generates the classroom background image using Gemini 2.5 Flash Image")

    out_dir = Path(settings.OUTPUT_DIR)
    script_file = out_dir / "test_stage_1_script.json"

    if not script_file.exists():
        LOGGER.error("Script file not found: %s", script_file)
        LOGGER.error("Please run Stage 1 first: python -m pipeline.test_stage_1_script_generation")
        return

    script_data = json.loads(script_file.read_text(encoding="utf-8"))

    # Extract pipeline context
    ctx = script_data.get("_pipeline_context", {})
    topic_id = ctx.get("topic_id", "test")
    level = ctx.get("level", "A1A2")
    category = ctx.get("category", "dialogue")
    title_slug = ctx.get("title_slug", "lesson")
    topic_title = script_data.get("topic_title", "Dutch Lesson")
    image_prompt = script_data.get("image_prompt", "")

    LOGGER.info(
        "Context: level=%s category=%s topic_id=%s slug=%s",
        level, category, topic_id, title_slug,
    )

    if not image_prompt:
        LOGGER.error("No 'image_prompt' found in script JSON.")
        LOGGER.error("Re-run Stage 1 to regenerate the script with an image prompt.")
        return

    LOGGER.info("Image prompt: %s", image_prompt[:120] + ("..." if len(image_prompt) > 120 else ""))

    # Generate image into output/{level}/{category}/visuals/
    output_root = out_dir / level / category
    LOGGER.info("\nGenerating background image via Gemini 2.5 Flash Image...")
    try:
        image_path = generate_topic_image(
            topic_id=topic_id,
            topic_title=topic_title,
            output_root=output_root,
            image_prompt=image_prompt,
            file_naming_context={"id": topic_id, "slug": title_slug},
        )

        LOGGER.info("\n=== IMAGE GENERATION RESULTS ===")
        LOGGER.info("Image saved to: %s", image_path)
        size_kb = image_path.stat().st_size / 1024
        LOGGER.info("File size: %.1f KB", size_kb)
        LOGGER.info("\n✅ Background image generated successfully!")
        LOGGER.info("📝 Next stage: python -m pipeline.test_stage_4_video_rendering")

    except Exception as e:
        LOGGER.error("❌ Image generation failed: %s", e)
        LOGGER.error("\nTroubleshooting:")
        LOGGER.error("- Verify GEMINI_IMAGE_CREATION_API_KEYS is set in .env")
        LOGGER.error("- Check network connection for Google Gemini API access")
        raise


if __name__ == "__main__":
    main()
