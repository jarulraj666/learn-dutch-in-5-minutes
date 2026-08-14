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
    aspect_ratio: str = "16:9",
    output_dir: Path | None = None,
    scene_background_seeds: dict[int, bytes] | None = None,
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
        aspect_ratio: Gemini ImageConfig aspect ratio string, e.g. "16:9" or "9:16"
    
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
        
        def _generate_one_scene(
            prompt_item: dict,
            api_key: str,
            background_seed_bytes: bytes | None = None,
        ) -> tuple[int, bytes]:
            """Generate a single scene image; returns (scene_num, image_bytes)."""
            scene_num = prompt_item.get("scene", 0)
            image_prompt = prompt_item.get("prompt", "")

            if seed_image_bytes:
                if aspect_ratio == "9:16":
                    placement = (
                        "FULL-BLEED 9:16 PORTRAIT — every single pixel of the canvas must be "
                        "covered by the scene background. NO white space, NO blank areas, NO empty "
                        "borders, NO padding, NO margins anywhere in the image — not at the top, "
                        "bottom, left, right, or any corner. The environment/background illustration "
                        "must extend all the way to every edge and fill the entire canvas. "
                        "Place both characters naturally within the frame with full bodies visible, "
                        "facing each other. Background scenery fills every part of the frame "
                        "behind and around the characters. "
                        "The bottom portion of the image must show the actual floor, ground, or "
                        "surface of the environment (e.g. floor tiles, carpet, pavement, grass) — "
                        "NOT a flat colour, NOT a gradient, NOT a plain coloured block. It must be "
                        "a detailed, textured part of the same scene that continues naturally from "
                        "the rest of the image. "
                        "STRICTLY FORBIDDEN: no text, no captions, no labels, no sentences, no "
                        "dialogue bubbles, no speech bubbles, no subtitles, no watermarks, and "
                        "absolutely no white rectangle, white box, white panel, or any solid-coloured "
                        "block anywhere in the lower half or anywhere else in the image."
                    )
                else:
                    placement = (
                        "Place the male character in the left 35-40% of the frame and the female "
                        "character in the right 35-40%, both facing inward toward the center, "
                        "with the center 20% kept open."
                    )

                parts: list = [
                    genai_types.Part(
                        inline_data=genai_types.Blob(
                            data=seed_image_bytes,
                            mime_type="image/png",
                        )
                    ),
                ]

                if background_seed_bytes:
                    parts.append(
                        genai_types.Part(
                            inline_data=genai_types.Blob(
                                data=background_seed_bytes,
                                mime_type="image/png",
                            )
                        )
                    )
                    bg_instruction = (
                        "Reference image 2 is a style reference only — use it to match the "
                        "lighting style, colour palette, art style, and prop/object design. "
                        "The scene content and character action and background should be generated fresh based on "
                        "the scene description below. "
                        "CRITICAL: DO NOT copy, tile, repeat, split, or stack this reference image. "
                        "DO NOT show two panels or two versions of the scene. "
                        "Create ONE completely new, original single-frame {aspect_ratio} image.\n"
                    ).replace("{aspect_ratio}", aspect_ratio)
                else:
                    bg_instruction = ""

                parts.append(
                    genai_types.Part(
                        text=(
                            f"Reference image 1: the two main characters — keep faces, hairstyles, "
                            f"skin tones. "
                            f"IGNORE the characters' poses, gestures, and any objects they are holding "
                            f"in the reference images — do NOT reproduce them. "
                            f"IGNORE any text, words, labels, or signs visible in reference images — "
                            f"do NOT reproduce them.\n"
                            f"{bg_instruction}"
                            f"OUTPUT REQUIREMENT: ONE single continuous {aspect_ratio} image. "
                            f"NEVER split into panels, NEVER tile, NEVER repeat, "
                            f"NEVER show the scene twice. One frame only.\n"
                            f"ABSOLUTELY NO TEXT, NO WORDS, NO LABELS, NO SIGNS, NO CAPTIONS, "
                            f"NO WRITING OF ANY KIND anywhere in the generated image. "
                            f"Any props that would normally have writing (menus, signs, nameplates, "
                            f"cards, screens) must appear as blank or decorative only.\n"
                            f"Using these EXACT SAME two characters, {placement} "
                            f"Scene to illustrate: {image_prompt}"
                        )
                    )
                )
                contents = parts
            else:
                contents = f"Generate a {aspect_ratio} image: {image_prompt}"

            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model="gemini-3.1-flash-image",
                contents=contents,
                config=genai_types.GenerateContentConfig(
                    response_modalities=["IMAGE"],
                    image_config=genai_types.ImageConfig(
                        aspect_ratio=aspect_ratio,
                    ),
                ),
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

        scene_results: dict[int, bytes] = {}

        # If per-scene background seeds are provided, all scenes run fully in parallel.
        if scene_background_seeds:
            LOGGER.info(
                "image_generation.per_scene_bg_seeds scenes=%s — all scenes parallel",
                sorted(scene_background_seeds.keys()),
            )
            keyed_all = [
                (prompt_item, available_keys[i % len(available_keys)])
                for i, prompt_item in enumerate(image_prompts)
            ]
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(image_prompts)) as executor:
                futures = {
                    executor.submit(
                        _generate_one_scene,
                        prompt_item,
                        api_key,
                        scene_background_seeds.get(prompt_item.get("scene", 0)) if scene_background_seeds else None,
                    ): prompt_item.get("scene", i)
                    for i, (prompt_item, api_key) in enumerate(keyed_all)
                }
                for future in concurrent.futures.as_completed(futures):
                    try:
                        scene_num, image_bytes = future.result()
                        scene_results[scene_num] = image_bytes
                        LOGGER.info("image_generation.scene_done scene=%d", scene_num)
                    except Exception as exc:
                        original_scene = futures[future]
                        raise RuntimeError(f"Scene {original_scene} generation failed: {exc}") from exc
        else:
            # Step 1: Generate scene 1 first (blocking) to establish the background reference.
            # All remaining scenes receive scene 1's output as a second seed image so Gemini
            # preserves the colour palette, lighting, and environment across the episode.
            LOGGER.info("image_generation.scene1_start — generating background reference")
            first_scene_num, first_scene_bytes = _generate_one_scene(
                image_prompts[0], available_keys[0]
            )
            scene_results[first_scene_num] = first_scene_bytes
            LOGGER.info("image_generation.scene1_done scene=%d — using as background seed", first_scene_num)
            _background_seed = first_scene_bytes

            # Step 2: Generate remaining scenes in parallel, each seeded with scene 1 as background.
            remaining = image_prompts[1:]
            if remaining:
                keyed_remaining = [
                    (prompt_item, available_keys[i % len(available_keys)])
                    for i, prompt_item in enumerate(remaining, start=1)
                ]
                with concurrent.futures.ThreadPoolExecutor(max_workers=len(remaining)) as executor:
                    futures = {
                        executor.submit(
                            _generate_one_scene, prompt_item, api_key, _background_seed
                        ): prompt_item.get("scene", i)
                        for i, (prompt_item, api_key) in enumerate(keyed_remaining)
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
        from google.genai import types as genai_types

        if not settings.GEMINI_IMAGE_CREATION_API_KEYS:
            raise ValueError("No Gemini image API keys configured. Set GEMINI_IMAGE_CREATION_API_KEYS in .env")

        image_bytes = None
        for api_key in settings.GEMINI_IMAGE_KEY_ROTATOR.available_keys():
            try:
                client = genai.Client(api_key=api_key)
                response = client.models.generate_content(
                    model="gemini-3.1-flash-image",
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
    portrait: bool = False,
) -> str:
    """Enrich image prompt for dialogue category using speaker/scenario metadata.

    Loads the level-specific ``dialogue_image_prompt.md`` template, substitutes
    all speaker/scenario placeholders, and fills in the orientation-specific
    placeholders (``{frame_label}``, ``{aspect_ratio}``, ``{char_position_1}``,
    ``{char_position_2}``, ``{char_center}``, ``{subtitle_zone}``) for either
    landscape (16:9, default) or portrait (9:16, when *portrait* is True).
    """
    _LANDSCAPE = {
        "frame_label":    "16:9",
        "aspect_ratio":   "16:9 aspect ratio",
        "char_position_1": "left 35\u201340% of the frame",
        "char_position_2": "right 35\u201340% of the frame",
        "char_center":    "center 20% \u2014 open space between them, no characters, no obstructions",
        "subtitle_zone":  "",
    }
    _PORTRAIT = {
        "frame_label":    "9:16 vertical",
        "aspect_ratio":   "9:16 aspect ratio, portrait orientation",
        "char_position_1": "upper-left area",
        "char_position_2": "upper-right area",
        "char_center":    "characters fill the frame naturally with full bodies visible",
        "subtitle_zone":  (
            " The background environment must fill the ENTIRE frame from top edge to bottom edge"
            " — no blank space, no white borders, no letterboxing, no empty areas at any edge."
            " The scene background extends fully to all four corners of the frame."
            " The bottom 20% of the frame must show only background scenery — no characters or people"
            " in that strip, so subtitle text can be overlaid there."
            " NO TEXT, NO CAPTIONS, NO LABELS, NO WATERMARKS anywhere in the image."
        ),
    }
    orientation = _PORTRAIT if portrait else _LANDSCAPE

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

    # Substitute content placeholders
    enriched = prompt_text.replace("{scenario}", scenario)
    enriched = enriched.replace("{speaker1_role}", speaker1_role)
    enriched = enriched.replace("{speaker2_role}", speaker2_role)
    enriched = enriched.replace("{speaker1_gender}", speaker1_gender)
    enriched = enriched.replace("{speaker2_gender}", speaker2_gender)
    enriched = enriched.replace("{topic_title}", artifact.get("topic_title", ""))

    # Substitute orientation placeholders
    for key, value in orientation.items():
        enriched = enriched.replace(f"{{{key}}}", value)

    LOGGER.debug("dialogue_image_prompt loaded from %s portrait=%s", prompt_path, portrait)
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
    topic_title = artifact.get("topic_title") or artifact.get("script", {}).get("topic_title", "Untitled")
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
            # Use seed already stored in artifact (selected once at pipeline start).
            # Fall back to random pick only if absent.
            import random as _random  # noqa: PLC0415
            render_cfg = settings.load_yaml(settings.ROOT / "config/visual_style.yaml").get("render", {})
            seed_image_rels = render_cfg.get("dialogue_seed_images") or ([render_cfg["dialogue_seed_image"]] if render_cfg.get("dialogue_seed_image") else [])
            seed_image_path: Path | None = None
            prior_seed = artifact.get("seed_image_used", "")
            if prior_seed:
                candidate = settings.ROOT / prior_seed
                if candidate.exists():
                    seed_image_path = candidate
                    LOGGER.info("image_generation.seed_reused path=%s", seed_image_path)
                else:
                    LOGGER.warning("image_generation.seed_missing stored=%s — falling back to random", prior_seed)
            if seed_image_path is None:
                valid_seeds = [settings.ROOT / r for r in seed_image_rels if (settings.ROOT / r).exists()]
                if valid_seeds:
                    seed_image_path = _random.choice(valid_seeds)
                    LOGGER.info("image_generation.seed_selected path=%s", seed_image_path)
                    # Store chosen seed back into artifact
                    try:
                        artifact["seed_image_used"] = str(seed_image_path.relative_to(settings.ROOT))
                    except ValueError:
                        artifact["seed_image_used"] = str(seed_image_path)
                elif seed_image_rels:
                    LOGGER.warning("dialogue_seed_images: none of the configured paths exist: %s", seed_image_rels)
            
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