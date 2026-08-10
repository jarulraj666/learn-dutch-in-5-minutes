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


def _is_rate_limited(exc: Exception) -> bool:
    """Check if exception indicates Gemini rate limit."""
    msg = str(exc).upper()
    return "429" in msg or "RESOURCE_EXHAUSTED" in msg or "QUOTA" in msg


def _generate_multiple_images(
    *,
    topic_id: str,
    topic_title: str,
    output_root: Path,
    image_prompts: list[dict[str, str]],
    seed_image_path: Path | None = None,
) -> list[Path]:
    """Generate multiple scene images in parallel, all seeded from a reference image.
    
    Loads a static seed image (character reference) and fires all scene generation
    requests concurrently — one API call per scene, all running in parallel.
    Each request includes the seed image so Gemini maintains consistent character
    appearance across all generated scenes.
    
    Args:
        topic_id: Unique topic identifier
        topic_title: Topic title for logging
        output_root: Root directory for output files
        image_prompts: List of dicts with keys: scene, prompt, description
        seed_image_path: Path to reference image for character consistency
    
    Returns:
        List of paths to generated PNG image files (one per scene, in scene order)
    """
    if not image_prompts:
        raise ValueError("image_prompts list is empty")
    
    LOGGER.info(
        "image_generation.multi_start topic_id=%s num_images=%d seeded=%s",
        topic_id,
        len(image_prompts),
        seed_image_path is not None,
    )
    
    visuals_dir = output_root / "visuals" / f"episode_{topic_id}_{topic_title.lower().replace(' ', '_')}"
    visuals_dir.mkdir(parents=True, exist_ok=True)
    
    # Load seed image bytes once — reused in every parallel API call
    seed_image_bytes: bytes | None = None
    if seed_image_path and seed_image_path.exists():
        seed_image_bytes = seed_image_path.read_bytes()
        LOGGER.info("image_generation.seed_loaded path=%s bytes=%d", seed_image_path, len(seed_image_bytes))
    elif seed_image_path:
        LOGGER.warning("image_generation.seed_missing path=%s — generating without seed", seed_image_path)
    
    try:
        from google import genai
        from google.genai import types as genai_types
        import concurrent.futures
        
        if not settings.GEMINI_IMAGE_CREATION_API_KEYS:
            raise ValueError("No Gemini image API keys configured")
        
        def _generate_one_scene(prompt_item: dict, api_key: str) -> tuple[int, bytes]:
            """Generate a single scene image; returns (scene_num, image_bytes)."""
            scene_num = prompt_item.get("scene", 0)
            image_prompt = prompt_item.get("prompt", "")
            
            if seed_image_bytes:
                contents = [
                    genai_types.Part(
                        inline_data=genai_types.Blob(
                            data=seed_image_bytes,
                            mime_type="image/png",
                        )
                    ),
                    genai_types.Part(
                        text=(
                            f"This reference image shows two adults — one male and one female — "
                            f"who are the main characters in this Dutch language learning video. "
                            f"Generate ONE single unified 16:9 scene (NOT a split panel, NOT a "
                            f"side-by-side comparison, NOT a collage — one continuous illustration). "
                            f"Using these EXACT SAME two characters (identical faces, hairstyles, "
                            f"skin tones, and clothing for both), place the male character in the "
                            f"left 35-40% of the frame and the female character in the right 35-40%, "
                            f"both facing inward toward the center, with the center 20% kept open. "
                            f"Scene to illustrate: {image_prompt}"
                        )
                    ),
                ]
            else:
                contents = f"Generate a 16:9 image: {image_prompt}"
            
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model="gemini-3.1-flash-lite-image",
                contents=contents,
            )
            if response.candidates:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, "inline_data") and part.inline_data:
                        return scene_num, part.inline_data.data
            raise RuntimeError(f"No image data returned from Gemini for scene {scene_num}")
        
        # Assign one API key per scene (round-robin across available keys)
        available_keys = list(settings.GEMINI_IMAGE_KEY_ROTATOR.available_keys())
        if not available_keys:
            raise ValueError("No available Gemini image API keys")
        
        keyed_prompts = [
            (prompt_item, available_keys[i % len(available_keys)])
            for i, prompt_item in enumerate(image_prompts)
        ]
        
        # Fire all scene requests in parallel
        scene_results: dict[int, bytes] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(image_prompts)) as executor:
            futures = {
                executor.submit(_generate_one_scene, prompt_item, api_key): prompt_item.get("scene", i)
                for i, (prompt_item, api_key) in enumerate(keyed_prompts)
            }
            for future in concurrent.futures.as_completed(futures):
                try:
                    scene_num, image_bytes = future.result()
                    scene_results[scene_num] = image_bytes
                    LOGGER.info("image_generation.scene_done scene=%d", scene_num)
                except Exception as exc:
                    original_scene = futures[future]
                    raise RuntimeError(f"Scene {original_scene} generation failed: {exc}") from exc
        
        # Save images in original scene order
        image_files = []
        for prompt_item in image_prompts:
            scene_num = prompt_item.get("scene", 0)
            image_bytes = scene_results[scene_num]
            output_png = visuals_dir / f"episode_{topic_id}_scene{scene_num}.png"
            image = Image.open(BytesIO(image_bytes))
            image.save(output_png, format="PNG")
            image_files.append(output_png)
            LOGGER.info("image_generation.saved scene=%d output=%s", scene_num, output_png)
        
        LOGGER.info(
            "image_generation.multi_complete topic_id=%s num_images=%d",
            topic_id,
            len(image_files),
        )
        return image_files
        
    except Exception as e:
        LOGGER.error("image_generation.multi_failed topic_id=%s error=%s", topic_id, str(e))
        raise RuntimeError(
            f"Multi-image generation failed for topic {topic_id}: {str(e)}"
        ) from e


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

    started_at = time.perf_counter()
    visuals_dir = output_root / "visuals" / f"episode_{topic_id}_{topic_title.lower().replace(' ', '_')}"
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

        if not settings.GEMINI_IMAGE_CREATION_API_KEYS:
            raise ValueError("No Gemini image API keys configured. Set GEMINI_IMAGE_CREATION_API_KEYS in .env")

        image_bytes = None
        for api_key in settings.GEMINI_IMAGE_KEY_ROTATOR.available_keys():
            try:
                client = genai.Client(api_key=api_key)
                response = client.models.generate_content(
                    model="gemini-3.1-flash-lite-image",
                    contents=f"Generate a 16:9 image: {image_prompt}",
                )
                if response.candidates:
                    for part in response.candidates[0].content.parts:
                        if hasattr(part, "inline_data") and part.inline_data:
                            image_bytes = part.inline_data.data
                            break
                if image_bytes:
                    LOGGER.info("image_generation.success")
                    break
            except Exception as key_exc:
                msg = str(key_exc).upper()
                if "429" in msg or "RESOURCE_EXHAUSTED" in msg or "QUOTA" in msg:
                    LOGGER.warning("Gemini image 429 — rotating to next key")
                    settings.GEMINI_IMAGE_KEY_ROTATOR.mark_rate_limited(api_key, exc=key_exc)
                    continue
                raise  # non-quota error: propagate immediately

        if not image_bytes:
            raise RuntimeError("No image data returned from Gemini (all keys tried).")

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
        from pipeline.core.db import get_db
        
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


def _enrich_dialogue_image_prompt(
    artifact: dict[str, Any],
    level: str,
) -> str:
    """Enrich image prompt for dialogue category using speaker/scenario metadata.
    
    Loads dialogue.md template and substitutes placeholders from artifact.
    
    Args:
        artifact: Artifact dict containing scenario, speakers (list), and topic_title.
        level: CEFR level (A1, A2, B1, B2).
    
    Returns:
        Enriched image prompt string ready for Gemini image generation.
    """
    # Load dialogue image prompt template (dedicated image prompt, not the script prompt)
    prompt_path = settings.ROOT / "prompts" / level / "dialogue_image_prompt.md"
    if not prompt_path.exists():
        LOGGER.warning(
            "Dialogue image prompt template not found at %s; using artifact image_prompt",
            prompt_path,
        )
        return artifact.get("image_prompt", "")
    
    prompt_text = prompt_path.read_text(encoding="utf-8").strip()
    
    # Extract speaker metadata from artifact
    speakers = artifact.get("speakers", [])
    scenario = artifact.get("scenario", "cafe")
    
    speaker1_role = "Dutch teacher"
    speaker1_gender = "female"
    speaker2_role = "learner"
    speaker2_gender = "female"
    
    if speakers and len(speakers) >= 2:
        speaker1 = speakers[0]
        speaker2 = speakers[1] if len(speakers) > 1 else {}
        speaker1_role = speaker1.get("role", speaker1_role)
        speaker1_gender = speaker1.get("gender", speaker1_gender)
        speaker2_role = speaker2.get("role", speaker2_role)
        speaker2_gender = speaker2.get("gender", speaker2_gender)
    
    # Substitute placeholders
    enriched = prompt_text.replace("{scenario}", scenario)
    enriched = enriched.replace("{speaker1_role}", speaker1_role)
    enriched = enriched.replace("{speaker2_role}", speaker2_role)
    enriched = enriched.replace("{speaker1_gender}", speaker1_gender)
    enriched = enriched.replace("{speaker2_gender}", speaker2_gender)
    enriched = enriched.replace("{topic_title}", artifact.get("topic_title", ""))
    
    LOGGER.debug("dialogue_image_prompt loaded from %s", prompt_path)
    return enriched


def generate_image_from_artifact(
    artifact: dict[str, Any],
    output_root: Optional[Path] = None,
) -> Path:
    """Generate image(s) from an artifact dict (loaded from file or DB).
    
    For dialogue with multiple image_prompts: Generate 5-6 images using batch API.
    For dialogue with single image_prompt: Enrich and generate one image.
    For other categories: Use image_prompt directly.
    
    Args:
        artifact: Artifact dict containing topic_id, topic_title, level, category, image_prompt(s)
        output_root: Override output root directory (defaults to output/{level}/{category})
    
    Returns:
        Path to primary generated image file (for backward compatibility)
    """
    topic_id = artifact.get("topic_id", "unknown")
    topic_title = artifact.get("topic_title", "Untitled")
    level = artifact.get("level", "A1A2")
    category = artifact.get("category", "dialogue")
    image_prompts = artifact.get("image_prompts") or artifact.get("script", {}).get("image_prompts", [])
    image_prompt = artifact.get("image_prompt") or artifact.get("script", {}).get("image_prompt", "")
    
    # Default output root based on level/category
    if output_root is None:
        output_root = settings.OUTPUT_DIR / level / category
    
    # MULTI-IMAGE PATH: For dialogue with 5-6 scene prompts
    if image_prompts and len(image_prompts) > 1:
        LOGGER.info(
            "Multi-image generation detected: %d scene prompts for topic_id=%s",
            len(image_prompts),
            topic_id,
        )
        
        try:
            # Resolve seed image path from visual_style config
            render_cfg = settings.load_yaml(settings.ROOT / "config/visual_style.yaml").get("render", {})
            seed_image_rel = render_cfg.get("dialogue_seed_image", "")
            seed_image_path: Path | None = None
            if seed_image_rel:
                candidate = settings.ROOT / seed_image_rel
                if candidate.exists():
                    seed_image_path = candidate
                else:
                    LOGGER.warning("dialogue_seed_image not found: %s", candidate)
            
            image_files = _generate_multiple_images(
                topic_id=topic_id,
                topic_title=topic_title,
                output_root=output_root,
                image_prompts=image_prompts,
                seed_image_path=seed_image_path,
            )
            
            # Update artifact with generated image files list
            artifact["generated_image_files"] = [str(f) for f in image_files]
            
            # For backward compatibility, also set generated_image_file to first image
            if image_files:
                resolved = image_files[0].resolve()
                try:
                    artifact["generated_image_file"] = str(resolved.relative_to(settings.ROOT.resolve()))
                except ValueError:
                    artifact["generated_image_file"] = str(image_files[0])
            
            LOGGER.info(
                "Multi-image generation complete: %d images saved for topic_id=%s",
                len(image_files),
                topic_id,
            )
            
            return image_files[0] if image_files else Path()
            
        except Exception as e:
            LOGGER.error(
                "Multi-image generation failed for topic_id=%s: %s",
                topic_id,
                str(e),
            )
            raise RuntimeError(
                f"Multi-image generation failed for topic_id={topic_id}: {e}"
            ) from e
    
    # SINGLE-IMAGE PATH: For dialogue with single prompt or other categories
    # For dialogue category, enrich image_prompt from dialogue.md template
    if category == "dialogue" and not image_prompts:
        enriched_prompt = _enrich_dialogue_image_prompt(artifact, level)
        if enriched_prompt:
            image_prompt = enriched_prompt
            LOGGER.info(
                "Enriched dialogue image prompt for topic_id=%s from dialogue.md template",
                topic_id,
            )
    
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
    resolved = image_file.resolve()
    try:
        artifact["files"]["image"] = str(resolved.relative_to(settings.ROOT.resolve()))
    except ValueError:
        artifact["files"]["image"] = str(image_file)
    
    # For consistency, also set generated_image_file for render_video.py
    try:
        artifact["generated_image_file"] = str(resolved.relative_to(settings.ROOT.resolve()))
    except ValueError:
        artifact["generated_image_file"] = str(image_file)
    
    return resolved


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
            level = artifact.get("level", "A1A2")
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