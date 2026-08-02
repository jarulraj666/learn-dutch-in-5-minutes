#!/usr/bin/env python3
"""Test Stage 1: Script Generation (Dialogue Creation)

Run: python -m pipeline.test_stage_1_script_generation
"""
import json
import logging
from pathlib import Path

from pipeline import settings
from pipeline.db import init_db, seed_topics_from_config
from pipeline.generate_script import generate_script
from pipeline.select_topic import choose_next_topic
from pipeline.store_content import create_title_slug

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
LOGGER = logging.getLogger(__name__)


def main():
    LOGGER.info("=== TEST STAGE 1: Script Generation ===")
    LOGGER.info("This stage generates the initial dialogue in the target language")
    
    # Initialize database
    init_db()
    seed_topics_from_config()
    LOGGER.info("✓ Database initialized")

    # Select a topic
    topic = choose_next_topic()
    LOGGER.info("✓ Selected topic: %s (%s)", topic.title_hint, topic.topic_id)

    # Generate script in Dutch
    language = "nl"
    LOGGER.info("Generating script in language: %s", language)
    script = generate_script(topic, language=language)
    LOGGER.info("✓ Script generated successfully")

    # Enrich script with pipeline context for downstream stages
    title_slug = create_title_slug(script.get("topic_title", topic.title_hint))
    script["_pipeline_context"] = {
        "topic_id": topic.topic_id,
        "level": topic.level,
        "category": topic.category,
        "title_slug": title_slug,
    }

    # Show results
    LOGGER.info("\n=== GENERATED SCRIPT ===")
    LOGGER.info("Language: %s", script.get("language"))
    LOGGER.info("Topic: %s", script.get("topic_title"))
    LOGGER.info("Level: %s | Category: %s | Slug: %s", topic.level, topic.category, title_slug)
    dialogue = script.get("dialogue", [])
    LOGGER.info("Dialogue lines: %d", len(dialogue))
    
    LOGGER.info("\nDialogue content:")
    for i, turn in enumerate(dialogue, 1):
        LOGGER.info("  %d. [%s] %s", i, turn.get("speaker"), turn.get("line"))

    # Save for next stage
    out_dir = Path(settings.OUTPUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    script_file = out_dir / "test_stage_1_script.json"
    script_file.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
    LOGGER.info("\n✓ Script saved to: %s", script_file)
    LOGGER.info("\n📝 For next stage, run: python -m pipeline.test_stage_2_voice_generation")


if __name__ == "__main__":
    main()
