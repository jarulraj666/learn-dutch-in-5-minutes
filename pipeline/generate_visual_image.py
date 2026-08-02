from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from io import BytesIO
from pathlib import Path
from typing import Any, Optional

from PIL import Image

from pipeline import settings

LOGGER = logging.getLogger(__name__)


def generate_topic_image(
    *,
    topic_id: str,
    topic_title: str,
    output_root: Path,
    image_prompt: str,
    file_naming_context: dict[str, str] | None = None,
) -> Path:
    """Generate and save a visual image for a topic using Gemini 2.5 Flash Image.
    
    Args:
        topic_id: Unique topic identifier
        topic_title: Topic title for logging
        output_root: Root directory for output files (e.g., output/A1/common_words)
        image_prompt: Full image generation prompt with {topic_title} already substituted
        file_naming_context: Dict with 'id' and 'slug' keys for output filename
    
    Returns:
        Path to generated PNG image file
    """
    if not image_prompt or not image_prompt.strip():
        raise ValueError(
            f"Image generation failed for topic {topic_id}: 'image_prompt' is empty"
        )

    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set in settings/environment.")

    started_at = time.perf_counter()
    visuals_dir = output_root / "visuals"
    visuals_dir.mkdir(parents=True, exist_ok=True)
    
    # Use naming context if provided, otherwise use topic_id
    if file_naming_context and "id" in file_naming_context and "slug" in file_naming_context:
        episode_id = file_naming_context["id"]
        title_slug = file_naming_context["slug"]
        output_png = visuals_dir / f"episode_{episode_id}_{title_slug}.png"
    else:
        output_png = visuals_dir / f"episode_{topic_id}_visual.png"

    LOGGER.info(
        "image_generation.request topic_id=%s topic_title=%s output=%s",
        topic_id,
        topic_title,
        output_png,
    )

    try:
        from google import genai

        client = genai.Client(api_key=settings.GEMINI_IMAGE_CREATION_API_KEY)

        # Using Gemini 2.5 Flash Image
        response = client.models.generate_content(
            model="gemini-2.5-flash-image",
            contents=f"Generate a 16:9 image: {image_prompt}",
        )

        image_bytes = None
        if response.candidates:
            for part in response.candidates[0].content.parts:
                if hasattr(part, "inline_data") and part.inline_data:
                    image_bytes = part.inline_data.data
                    break

        if not image_bytes:
            raise RuntimeError("No image data returned from Gemini 2.5 Flash Image.")

        image = Image.open(BytesIO(image_bytes))
        image.save(output_png, format="PNG")

    except Exception as e:
        LOGGER.error(
            "image_generation.failed topic_id=%s error=%s",
            topic_id,
            str(e),
        )
        raise RuntimeError(
            f"Image generation failed for topic {topic_id}: {str(e)}"
        ) from e

    LOGGER.info(
        "image_generation.done topic_id=%s output=%s elapsed_sec=%.2f",
        topic_id,
        output_png,
        time.perf_counter() - started_at,
    )

    return output_png


def load_artifact_from_file(artifact_path: Path) -> dict[str, Any]:
    """Load artifact JSON from file."""
    if not artifact_path.exists():
        raise FileNotFoundError(f"Artifact file not found: {artifact_path}")
    
    with open(artifact_path, "r", encoding="utf-8") as f:
        artifact = json.load(f)
    
    LOGGER.info("Loaded artifact from file: %s", artifact_path)
    return artifact


def load_artifact_from_database(topic_id: str) -> dict[str, Any]:
    """Load artifact JSON from database canonical_scripts table."""
    try:
        from pipeline.db import get_db
        
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "SELECT script_json FROM canonical_scripts WHERE topic_id = ?",
            (topic_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"No script found for topic_id: {topic_id}")
        
        script_json = json.loads(row[0])
        LOGGER.info("Loaded artifact from database for topic_id: %s", topic_id)
        return script_json
    except ImportError:
        raise RuntimeError("Database not available; cannot load artifact from DB")


def generate_image_from_artifact(
    artifact: dict[str, Any],
    output_root: Optional[Path] = None,
) -> Path:
    """Generate image from an artifact dict (loaded from file or DB).
    
    Args:
        artifact: Artifact dict containing topic_id, topic_title, level, category, image_prompt
        output_root: Override output root directory (defaults to output/{level}/{category})
    
    Returns:
        Path to generated image file
    """
    topic_id = artifact.get("topic_id", "unknown")
    topic_title = artifact.get("topic_title", "Untitled")
    level = artifact.get("level", "A1")
    category = artifact.get("category", "dialogue")
    image_prompt = artifact.get("image_prompt", "")
    
    # Default output root based on level/category
    if output_root is None:
        output_root = settings.OUTPUT_DIR / level / category
    
    # File naming context from artifact
    file_naming_context = None
    if "files" in artifact and "image" in artifact["files"]:
        # Extract id and slug from image path (e.g., episode_123_common_words.png)
        image_path = artifact["files"]["image"]
        image_name = Path(image_path).stem
        if image_name.startswith("episode_"):
            parts = image_name.replace("episode_", "").rsplit("_", 1)
            if len(parts) == 2:
                file_naming_context = {"id": parts[0], "slug": parts[1]}
    
    image_file = generate_topic_image(
        topic_id=topic_id,
        topic_title=topic_title,
        output_root=output_root,
        image_prompt=image_prompt,
        file_naming_context=file_naming_context,
    )
    
    # Update artifact with generated image path
    if "files" not in artifact:
        artifact["files"] = {}
    artifact["files"]["image"] = str(image_file.relative_to(settings.ROOT))
    
    return image_file


def main():
    """CLI entry point for standalone image generation."""
    parser = argparse.ArgumentParser(
        description="Generate visual image from artifact (file or database)"
    )
    parser.add_argument(
        "--artifact-file",
        type=Path,
        help="Path to artifact JSON file (e.g., output/A1/common_words/episode_123_common_words.json)"
    )
    parser.add_argument(
        "--topic-id",
        type=str,
        help="Topic ID to load artifact from database"
    )
    parser.add_argument(
        "--db",
        action="store_true",
        help="Load artifact from database (requires --topic-id)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    
    try:
        # Load artifact
        if args.artifact_file:
            artifact = load_artifact_from_file(args.artifact_file)
            output_root = args.artifact_file.parent
        elif args.db and args.topic_id:
            artifact = load_artifact_from_database(args.topic_id)
            level = artifact.get("level", "A1")
            category = artifact.get("category", "dialogue")
            output_root = settings.OUTPUT_DIR / level / category
        else:
            parser.print_help()
            sys.exit(1)
        
        # Generate image
        image_file = generate_image_from_artifact(artifact, output_root=output_root)
        print(f"✓ Image generated: {image_file}")
        
        # Optionally save updated artifact
        if args.artifact_file:
            artifact_path = Path(args.artifact_file)
            with open(artifact_path, "w", encoding="utf-8") as f:
                json.dump(artifact, f, indent=2, ensure_ascii=False)
            print(f"✓ Artifact updated: {artifact_path}")
        
    except Exception as e:
        LOGGER.error("Image generation failed: %s", str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()