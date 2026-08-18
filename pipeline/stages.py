"""Pure stage functions shared by run_pipeline.py and rerun_stage.py.

Each function takes explicit inputs and returns results.
No artifact I/O — callers are responsible for loading and saving artifacts.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pipeline.core.select_topic import TopicChoice

LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Level normalisation (shared constant)
# ---------------------------------------------------------------------------

LEVEL_MAP: dict[str, str] = {
    "A1": "A1A2",
    "A2": "A1A2",
}


def normalize_level(level: str) -> str:
    return LEVEL_MAP.get(level, level)


# ---------------------------------------------------------------------------
# Stage functions
# ---------------------------------------------------------------------------

def stage_script(topic: "TopicChoice", language: str, level: str) -> dict:
    """Generate a script for *topic*. Returns the script dict."""
    from pipeline.generate.generate_script import generate_script
    return generate_script(topic, language=language, level=level)


def stage_metadata(script: dict, category: str, level: str, topic_id: str = "") -> tuple[str, str, str, dict]:
    """Generate YouTube metadata.

    Returns:
        (playlist_name, playlist_description, playlist_id, metadata_dict)
    """
    from pipeline import settings
    from pipeline.generate.generate_metadata import generate_metadata

    by_level = settings.PLAYLISTS_CONFIG.get("playlists", {}).get(level, {})
    playlist = by_level.get(category)
    if not playlist:
        raise ValueError(f"No playlist configured for level={level!r} category={category!r}")
    playlist_name = playlist["name"] if isinstance(playlist, dict) else playlist
    playlist_description = playlist.get("description", "") if isinstance(playlist, dict) else ""
    playlist_id = playlist.get("id", "") if isinstance(playlist, dict) else ""

    metadata = generate_metadata(script, playlist_track=category, level=level, category=category, topic_id=topic_id)
    return playlist_name, playlist_description, playlist_id, metadata


def stage_voice(
    script: dict,
    output_root: str | Path,
    level: str,
    category: str,
    topic_id: str,
    title_slug: str,
) -> dict:
    """Generate TTS audio. Returns voice_plan dict."""
    from pipeline.generate.generate_voice import generate_voice_assets
    return generate_voice_assets(
        script,
        output_root=str(output_root),
        level=level,
        category=category,
        topic_id=topic_id,
        title_slug=title_slug,
    )


def stage_subtitles(
    audio_path: str | Path,
    output_root: str | Path,
    level: str,
    category: str,
    topic_id: str,
    title_slug: str,
    script_dialogue: list | None = None,
    dialogue_en: list | None = None,
) -> dict:
    """Generate ASS karaoke + SRT subtitles. Returns subtitle_plan dict."""
    from pipeline.generate.generate_subtitles import plan_subtitles
    return plan_subtitles(
        str(audio_path),
        output_root=str(output_root),
        level=level,
        category=category,
        topic_id=topic_id,
        title_slug=title_slug,
        script_dialogue=script_dialogue,
        dialogue_en=dialogue_en,
    )


def stage_image(
    topic_id: str,
    topic_title: str,
    image_prompt: str,
    image_prompts: list,
    level: str,
    category: str,
    output_root: str | Path,
    seed_image_used: str = "",
) -> tuple[str, list, str]:
    """Generate background image(s).

    Returns:
        (primary_image_file_str, generated_image_files_list, seed_image_used)
    """
    from pipeline.generate.generate_visual_image import generate_image_from_artifact
    artifact_dict: dict = {
        "topic_id": topic_id,
        "topic_title": topic_title,
        "image_prompt": image_prompt,
        "image_prompts": image_prompts,
        "level": level,
        "category": category,
        "seed_image_used": seed_image_used,
    }
    result = generate_image_from_artifact(artifact_dict, output_root=Path(output_root))
    primary = str(result) if result else ""
    all_files = artifact_dict.get("generated_image_files", [])
    seed_used = artifact_dict.get("seed_image_used", "")
    return primary, all_files, seed_used


def stage_render(artifact: dict) -> Path:
    """Render video from artifact dict. Returns path to rendered MP4."""
    from pipeline.publish.render_video import render_from_artifact
    return render_from_artifact(artifact)


def stage_upload(artifact: dict, video_path: str | Path) -> dict:
    """Upload to YouTube. Returns the youtube result dict."""
    from pipeline.publish.upload_youtube import upload_video
    return upload_video(artifact, Path(video_path))


def stage_upload_captions(artifact_path: str | Path | None, video_id: str, srt_path: str | Path) -> dict | None:
    """Upload English SRT captions. Returns the caption result or None."""
    from pipeline.publish.upload_youtube import upload_captions, _get_youtube_client
    youtube = _get_youtube_client()
    return upload_captions(youtube, video_id, Path(srt_path))


def stage_qa_audio(wav_path: str | Path, script_dialogue: list, language: str = "nl"):
    """Run audio QA. Returns QA report."""
    from pipeline.generate.qa_audio import run_audio_qa
    return run_audio_qa(wav_path=str(wav_path), script_dialogue=script_dialogue, language=language)


def stage_qa_subtitles(
    ass_file: str | None,
    srt_file: str | None,
    expected_count: int | None = None,
) -> tuple[object | None, object | None]:
    """Run subtitle QA. Returns (ass_report_or_None, srt_report_or_None)."""
    from pipeline.generate.qa_subtitles import run_ass_qa, run_srt_qa
    ass_report = run_ass_qa(ass_file, expected_count=expected_count) if ass_file and Path(ass_file).exists() else None
    srt_report = run_srt_qa(srt_file, expected_count=expected_count) if srt_file and Path(srt_file).exists() else None
    return ass_report, srt_report


def stage_generate_shorts_images(artifact: dict) -> list[dict]:
    """Generate native 9:16 portrait images for each scene's Short."""
    from pipeline.publish.generate_shorts import generate_shorts_images
    return generate_shorts_images(artifact)


def stage_generate_shorts(artifact: dict) -> list[dict]:
    """Generate vertical Short clips for every scene in the episode."""
    from pipeline.publish.generate_shorts import generate_scene_shorts
    return generate_scene_shorts(artifact)


def stage_upload_short(
    artifact: dict,
    scene_short: dict,
    full_video_id: str,
) -> dict:
    """Upload one rendered Short to YouTube."""
    from pipeline.publish.upload_shorts import upload_short
    return upload_short(artifact, scene_short, full_video_id)


def stage_upload_short_instagram(
    artifact: dict,
    scene_short: dict,
) -> dict:
    """Upload one rendered Short to Instagram as a Reel."""
    from pipeline.publish.upload_instagram import upload_short_instagram
    return upload_short_instagram(artifact, scene_short)


def stage_upload_short_tiktok(
    artifact: dict,
    scene_short: dict,
) -> dict:
    """Upload one rendered Short to TikTok."""
    from pipeline.publish.upload_tiktok import upload_short_tiktok
    return upload_short_tiktok(artifact, scene_short)


def stage_upload_short_facebook(
    artifact: dict,
    scene_short: dict,
) -> dict:
    """Upload one rendered Short to a Facebook Page as a Reel."""
    from pipeline.publish.upload_facebook import upload_short_facebook
    return upload_short_facebook(artifact, scene_short)
