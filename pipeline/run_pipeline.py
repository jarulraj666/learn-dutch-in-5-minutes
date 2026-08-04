from __future__ import annotations

import argparse
import json
import logging
import shutil
import time
from contextlib import contextmanager
from pathlib import Path

from pipeline import settings
from pipeline.core.db import init_db, mark_topic_done, seed_topics_from_config
from pipeline.generate.generate_metadata import generate_metadata
from pipeline.generate.generate_subtitles import plan_subtitles
from pipeline.generate.generate_voice import generate_voice_assets
from pipeline.generate.generate_visual_image import generate_image_from_artifact
from pipeline.generate.generate_script import generate_script
from pipeline.publish.render_video import render_from_artifact
from pipeline.core.select_topic import choose_next_topic
from pipeline.core.store_content import (
    create_title_slug,
    ensure_output_dir,
    get_artifact_path,
    store_canonical_script,
)
from pipeline.publish.upload_youtube import build_upload_payload, upload_video
from pipeline.utils import iter_dialogue_turns, to_compact_dialogue


LOGGER = logging.getLogger(__name__)


@contextmanager
def _stage(name: str):
    start = time.perf_counter()
    LOGGER.info("stage.start %s", name)
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        LOGGER.info("stage.done %s elapsed_sec=%.2f", name, elapsed)


def _playlist_name(level: str, track: str) -> str:
    by_level = settings.PLAYLISTS_CONFIG.get("playlists", {}).get(level, {})
    playlist = by_level.get(track)
    if not playlist:
        raise ValueError(f"No playlist configured for level={level} track={track}")
    return playlist["name"] if isinstance(playlist, dict) else playlist


def _playlist_description(level: str, track: str) -> str:
    by_level = settings.PLAYLISTS_CONFIG.get("playlists", {}).get(level, {})
    playlist = by_level.get(track)
    if isinstance(playlist, dict):
        return playlist.get("description", "")
    return ""


def _estimate_dialogue_seconds(dialogue: list[dict]) -> float:
    # Estimate timing with TTS pace when available to better match rendered speech.
    speech_cfg = settings.PEDAGOGY_CONFIG.get("speech", {})
    words_per_second = float(speech_cfg.get("estimated_words_per_second", 1.6))
    tts_rate_wpm = speech_cfg.get("tts_rate_wpm")
    if tts_rate_wpm:
        words_per_second = max(0.6, float(tts_rate_wpm) / 60.0)

    per_turn_pause_seconds = float(speech_cfg.get("per_turn_pause_seconds", 0.6))
    pacing_safety_multiplier = float(speech_cfg.get("pacing_safety_multiplier", 1.08))

    total = 0.0
    for _, line in iter_dialogue_turns(dialogue):
        words = max(1, len(line.split()))
        total += (words / words_per_second) + per_turn_pause_seconds
    return total * pacing_safety_multiplier


def _archive_video(video_path: Path, canonical_script_id: int) -> Path:
    archive_dir = settings.VIDEO_ARCHIVE_DIR
    if not archive_dir.is_absolute():
        archive_dir = settings.ROOT / archive_dir
    archive_dir.mkdir(parents=True, exist_ok=True)

    archived_path = archive_dir / f"episode_{canonical_script_id}.mp4"
    shutil.copy2(video_path, archived_path)
    return archived_path


def _save_script_exports(
    *,
    out_dir: Path,
    canonical_script_id: int,
    topic_id: str,
    script: dict,
    metadata: dict,
) -> dict[str, str]:
    scripts_dir = out_dir / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)

    json_path = scripts_dir / f"episode_{canonical_script_id}_script.json"
    md_path = scripts_dir / f"episode_{canonical_script_id}_script.md"

    json_path.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")

    lines: list[str] = []
    lines.append(f"# {metadata.get('title', f'Episode {canonical_script_id}')}")
    lines.append("")
    lines.append(f"- Episode: {canonical_script_id}")
    lines.append(f"- Topic: {topic_id}")
    lines.append(f"- Language: {script.get('language', 'nl')}")
    lines.append(f"- Estimated Conversation Seconds: {round(_estimate_dialogue_seconds(script.get('dialogue', [])), 2)}")
    lines.append("")
    lines.append("## Conversation")
    lines.append("")
    for turn in script.get("dialogue", []):
        parsed_turns = iter_dialogue_turns([turn])
        if not parsed_turns:
            continue
        speaker, line = parsed_turns[0]
        lines.append(f"- {speaker}: {line}")

    key_phrases = script.get("key_phrases", [])
    if key_phrases:
        lines.append("")
        lines.append("## Key Phrases")
        lines.append("")
        for phrase in key_phrases:
            lines.append(f"- {phrase}")

    vocabulary = script.get("vocabulary", [])
    if vocabulary:
        lines.append("")
        lines.append("## Vocabulary")
        lines.append("")
        for item in vocabulary:
            nl = item.get("nl", "")
            en = item.get("en", "")
            lines.append(f"- {nl} -> {en}")

    quiz = script.get("quiz", [])
    if quiz:
        lines.append("")
        lines.append("## Quiz")
        lines.append("")
        for i, q in enumerate(quiz, start=1):
            lines.append(f"{i}. {q.get('question', '')}")
            answer = q.get("answer", "")
            if answer:
                lines.append(f"   Answer: {answer}")

    grammar_notes = script.get("grammar_notes", [])
    if grammar_notes:
        lines.append("")
        lines.append("## Grammar Notes")
        lines.append("")
        for note in grammar_notes:
            title = note.get("title", "Note")
            explanation = note.get("explanation", "")
            lines.append(f"- {title}: {explanation}")

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {
        "script_json": str(json_path),
        "script_markdown": str(md_path),
    }


def run(language: str, level: str, category: str | None = None, upload: bool = True) -> Path:
    run_start = time.perf_counter()
    LOGGER.info(
        "=== PIPELINE START language=%s level=%s category=%s ===",
        language, level, category or "auto",
    )

    with _stage("db_init"):
        init_db()
        seed_topics_from_config()
        LOGGER.info("✓ Database initialized")

    with _stage("topic_selection"):
        topic = choose_next_topic(level=level, category=category)
        level = topic.level
        category = topic.category
        LOGGER.info(
            "✓ Topic selected: %s | level=%s category=%s track=%s",
            topic.title_hint, topic.level, topic.category, topic.track,
        )

    with _stage("script_generation"):
        script = generate_script(topic, language=language, level=topic.level)
        LOGGER.info("✓ Script generated: %d dialogue lines", len(script.get("dialogue", [])))

    with _stage("metadata_generation"):
        playlist_name = _playlist_name(level, topic.category)
        playlist_description = _playlist_description(level, topic.category)
        metadata = generate_metadata(script, playlist_track=topic.category, level=level, category=category)
        LOGGER.info("✓ Metadata: title=%s | playlist=%s", metadata.get("title", ""), playlist_name)

    # Prepare hierarchical output directory structure: output/{level}/{category}/{type}/
    title_slug = create_title_slug(topic.title_hint)
    
    out_dir = ensure_output_dir(level, category)
    
    # Also ensure subdirectories for different file types
    audio_dir = ensure_output_dir(level, category, "audio")
    visuals_dir = ensure_output_dir(level, category, "visuals")
    videos_dir = ensure_output_dir(level, category, "videos")
    subtitles_dir = ensure_output_dir(level, category, "subtitles")
    
    LOGGER.info(
        "output.dirs.ready level=%s category=%s slug=%s base=%s",
        level, category, title_slug, out_dir
    )

    with _stage("voice_generation"):
        voice_plan = generate_voice_assets(
            script,
            output_root=str(out_dir),
            level=level,
            category=category,
            topic_id=topic.topic_id,
            title_slug=title_slug,
        )
        LOGGER.info("✓ Voice generated: %s", voice_plan.get("dialogue_audio", ""))

    with _stage("subtitle_generation"):
        dialogue_audio_path = voice_plan.get("dialogue_audio")
        if not dialogue_audio_path:
            raise RuntimeError("No dialogue audio path from voice generation")
        subtitle_plan = plan_subtitles(
            dialogue_audio_path,
            output_root=str(out_dir),
            level=level,
            category=category,
            topic_id=topic.topic_id,
            title_slug=title_slug,
            script_dialogue=script.get("dialogue"),
        )
        LOGGER.info("✓ Subtitles generated: %s", subtitle_plan.get("srt_file", ""))

    with _stage("image_generation"):
        image_prompt = script.get("image_prompt", "")
        result = generate_image_from_artifact(
            {
                "topic_id": topic.topic_id,
                "topic_title": script.get("topic_title", topic.title_hint),
                "image_prompt": image_prompt,
                "level": level,
                "category": category,
            },
            output_root=out_dir,
        )
        generated_image_file = str(result) if result else ""
        if not generated_image_file:
            raise RuntimeError("Image generation returned no file path.")
        LOGGER.info("✓ Image generated: %s", generated_image_file)

    with _stage("db_store_script"):
        canonical_script_id = store_canonical_script(
            topic_id=topic.topic_id,
            language=language,
            title=metadata["title"],
            script=script,
        )

    with _stage("script_export"):
        script_exports = _save_script_exports(
            out_dir=out_dir,
            canonical_script_id=canonical_script_id,
            topic_id=topic.topic_id,
            script=script,
            metadata=metadata,
        )

    artifact = {
        # Flat fields expected by render_video and upload_youtube
        "level": level,
        "category": category,
        "topic_id": topic.topic_id,
        "title_slug": title_slug,
        "audio_file": voice_plan.get("dialogue_audio", ""),
        "karaoke_file": subtitle_plan.get("karaoke_file", ""),
        "generated_image_file": generated_image_file or "",
        # Nested context
        "topic": {
            "id": topic.topic_id,
            "level": level,
            "category": category,
            "track": topic.track,
            "title_slug": title_slug,
            "title_hint": topic.title_hint,
        },
        "workflow_mode": "single_agent",
        "playlist": playlist_name,
        "playlist_description": playlist_description,
        "canonical_script_id": canonical_script_id,
        "script": script,
        "metadata": metadata,
        "voice": voice_plan,
        "subtitles": subtitle_plan,
        "timing": {
            "estimated_conversation_seconds": round(_estimate_dialogue_seconds(script.get("dialogue", [])), 2),
            "target_video_seconds": int(settings.PEDAGOGY_CONFIG.get("target_duration_seconds", 300)),
        },
        "storage": {
            "script_exports": script_exports,
        },
    }

    # Generate artifact path using new naming convention: episode_{topic_id}_{slug}.json
    # (title_slug was already calculated in output.dirs.ready stage)
    out_path = out_dir / f"episode_{topic.topic_id}_{title_slug}.json"
    artifact["storage"]["artifact_file"] = str(out_path)
    
    with _stage("artifact_write_initial"):
        out_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")

    # Prepare render and upload dry-run outputs as part of the orchestration chain.
    with _stage("render_video"):
        render_manifest_path = render_from_artifact(out_path)
        render_manifest = json.loads(render_manifest_path.read_text(encoding="utf-8"))
        artifact["upload_payload_preview"] = build_upload_payload(out_path)
        artifact["render"] = render_manifest
        LOGGER.info(
            "render.ready assembled=%s video=%s",
            render_manifest.get("assembled"),
            render_manifest.get("planned_video_file", ""),
        )

    planned_video_file = render_manifest.get("planned_video_file", "")
    stable_video_path = planned_video_file
    if render_manifest.get("assembled") and planned_video_file:
        video_path = Path(planned_video_file)
        if video_path.exists():
            with _stage("archive_video"):
                archived_path = _archive_video(video_path, canonical_script_id)
            stable_video_path = str(archived_path)
            artifact.setdefault("storage", {})["archived_video_file"] = str(archived_path)

    with _stage("artifact_write_final"):
        out_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")

    if upload:
        video_path_for_upload = Path(stable_video_path) if stable_video_path else None
        if video_path_for_upload and video_path_for_upload.exists():
            with _stage("upload_youtube"):
                try:
                    result = upload_video(out_path, video_path_for_upload)
                    artifact["youtube"] = result
                    out_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
                    LOGGER.info("✓ Uploaded to YouTube: video_id=%s playlist=%s",
                                result.get("video_id"), result.get("playlist_name"))
                except Exception as exc:
                    LOGGER.warning("⚠ YouTube upload failed (video saved locally): %s", exc)
        else:
            LOGGER.warning("⚠ Upload skipped — no rendered video found at: %s", stable_video_path)

    LOGGER.info(
        "pipeline.done episode=%s elapsed_sec=%.2f artifact=%s",
        canonical_script_id,
        time.perf_counter() - run_start,
        out_path,
    )

    mark_topic_done(topic.topic_id)
    LOGGER.info("topic.done id=%s", topic.topic_id)

    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Dutch video content pipeline")
    parser.add_argument("--language", default="nl", help="Target language code (default: nl)")
    parser.add_argument("--level", default="A1", choices=["A1", "A2", "B1", "B2"], help="CEFR level")
    parser.add_argument(
        "--category",
        choices=["common_words", "grammar", "vocabulary", "dialogue"],
        default=None,
        help="Generate all videos for a specific category, or one video if omitted",
    )
    parser.add_argument("--log-level", default="INFO", help="DEBUG, INFO, WARNING, ERROR")
    parser.add_argument("--no-upload", action="store_true", help="Skip YouTube upload after rendering")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    if args.category:
        # Batch mode: generate all pending topics in the category
        completed = []
        failed = []
        video_num = 1
        while True:
            LOGGER.info(
                "\n=== VIDEO %d | category=%s ===", video_num, args.category
            )
            try:
                out_path = run(language=args.language, level=args.level, category=args.category, upload=not args.no_upload)
                completed.append(str(out_path))
                LOGGER.info("✓ Video %d done: %s", video_num, out_path)
                video_num += 1
            except (RuntimeError, Exception) as exc:
                if "No pending or selected topics" in str(exc):
                    LOGGER.info("✓ All topics in category '%s' are done.", args.category)
                    break
                failed.append(str(exc))
                LOGGER.error("✗ Video %d failed: %s", video_num, exc)
                video_num += 1

        print(f"\n=== BATCH COMPLETE ===")
        print(f"✓ Generated: {len(completed)} video(s)")
        if failed:
            print(f"✗ Failed:    {len(failed)} video(s)")
        for path in completed:
            print(f"  - {path}")
    else:
        # Single mode: generate next pending topic across all categories
        out_path = run(language=args.language, level=args.level, category=None, upload=not args.no_upload)
        print(f"\n✓ Pipeline completed. Artifact: {out_path}")


if __name__ == "__main__":
    main()
