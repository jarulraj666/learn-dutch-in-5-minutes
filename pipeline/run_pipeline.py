from __future__ import annotations

import argparse
import json
import logging
import shutil
import time
from contextlib import contextmanager
from pathlib import Path

from pipeline import settings
from pipeline.db import init_db, mark_topic_done, seed_topics_from_config
from pipeline.generate_metadata import generate_metadata
from pipeline.generate_subtitles import plan_subtitles
from pipeline.generate_voice import generate_voice_assets
from pipeline.generate_script import generate_script
from pipeline.multi_agent import UploadPrepAgent, WorkflowTopic, run_multi_agent_content
from pipeline.ollama_client import call_ollama, extract_json_object
from pipeline.qa_checks import validate_description, validate_script_structure
from pipeline.render_video import render_from_artifact
from pipeline.schedule_publish import next_publish_slot
from pipeline.select_topic import choose_next_topic
from pipeline.store_content import (
    create_title_slug,
    ensure_output_dir,
    get_artifact_path,
    save_episode_artifact,
    store_canonical_script,
    store_publish_job,
    update_publish_job_artifacts,
    update_publish_job_status,
)
from pipeline.upload_youtube import build_upload_payload


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
    return playlist


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
    for turn in dialogue:
        words = max(1, len(str(turn.get("line", "")).split()))
        total += (words / words_per_second) + per_turn_pause_seconds
    return total * pacing_safety_multiplier


def _conversation_target_seconds() -> int:
    configured_target = int(settings.PEDAGOGY_CONFIG.get("conversation_target_seconds", 180))
    return max(180, configured_target)


def _normalize_line(text: str) -> str:
    return " ".join(text.lower().split())


def _build_unique_dialogue(dialogue: list[dict]) -> list[dict]:
    unique_dialogue: list[dict] = []
    seen: set[str] = set()
    for turn in dialogue:
        line = str(turn.get("line", "")).strip()
        if not line:
            continue
        key = _normalize_line(line)
        if key in seen:
            continue
        unique_dialogue.append({"speaker": turn.get("speaker", "Speaker1"), "line": line})
        seen.add(key)
    return unique_dialogue


def _generate_dialogue_extension(script: dict, current_dialogue: list[dict], shortfall_seconds: float) -> list[dict]:
    language = script.get("language", "nl")
    topic_title = script.get("topic_title", "Dutch beginner conversation")
    key_phrases = script.get("key_phrases", [])[:6]
    recent_dialogue = current_dialogue[-8:]

    min_turns = max(10, int(shortfall_seconds // 9))
    max_turns = min(24, min_turns + 6)

    prompt = (
        "You are creating CEFR A1 beginner dialogue in Dutch. "
        "Continue the SAME conversation naturally with NEW ideas and no repeated lines.\n"
        f"Language: {language}\n"
        f"Topic: {topic_title}\n"
        f"Needed speaking time shortfall (seconds): {round(shortfall_seconds, 1)}\n"
        f"Generate between {min_turns} and {max_turns} new turns.\n"
        "Rules:\n"
        "- Output ONLY JSON object with key dialogue.\n"
        "- JSON format: {\"dialogue\": [{\"speaker\": \"Speaker1|Speaker2\", \"line\": \"...\"}]}\n"
        "- Every line must be unique and short (max 10 words).\n"
        "- No filler instructions like 'repeat after me'.\n"
        "- Keep pace slow and beginner-friendly.\n"
        "- Alternate speakers naturally.\n"
        f"Use these phrases naturally when useful: {json.dumps(key_phrases, ensure_ascii=False)}\n"
        f"Recent dialogue context: {json.dumps(recent_dialogue, ensure_ascii=False)}\n"
    )

    response_text = call_ollama(prompt)
    parsed = extract_json_object(response_text)
    extension = parsed.get("dialogue", [])
    if isinstance(extension, list):
        result = [item for item in extension if isinstance(item, dict)]
        if not result:
            raise ValueError("Dialogue extension returned empty list despite successful parsing")
        return result
    else:
        raise ValueError("Expected 'dialogue' key with list value in response")





def _expand_script_to_target_duration(script: dict, target_seconds: int) -> dict:
    dialogue = _build_unique_dialogue(list(script.get("dialogue", [])))
    if not dialogue:
        return script

    used_lines = {_normalize_line(str(t.get("line", ""))) for t in dialogue}
    rounds = 0
    successful_extensions = 0
    min_successful_extensions = 1  # Accept after just 1 successful extension
    max_rounds = 3  # Try at most 3 times (was 10, too aggressive)
    
    while successful_extensions < min_successful_extensions and rounds < max_rounds:
        rounds += 1
        shortfall = target_seconds - _estimate_dialogue_seconds(dialogue)
        
        # If we're close enough to target, accept what we have
        if shortfall < 30:
            LOGGER.info("expansion.close_enough rounds=%d shortfall=%f seconds", rounds, shortfall)
            break
        
        try:
            extension = _generate_dialogue_extension(script, dialogue, shortfall_seconds=shortfall)
        except Exception as e:
            LOGGER.warning("expansion.parse_failed round=%d error=%s, accepting current dialogue", rounds, str(e))
            break
        
        if not extension:
            LOGGER.warning("expansion.empty_response round=%d, accepting current dialogue", rounds)
            break

        added = 0
        for item in extension:
            speaker = item.get("speaker", "Speaker1")
            line = str(item.get("line", "")).strip()
            if not line:
                continue
            normalized = _normalize_line(line)
            if normalized in used_lines:
                continue
            dialogue.append({"speaker": speaker, "line": line})
            used_lines.add(normalized)
            added += 1

        if added > 0:
            successful_extensions += 1
            LOGGER.info("expansion.success round=%d added=%d total_lines=%d", rounds, added, len(dialogue))
        else:
            LOGGER.warning("expansion.no_new_lines round=%d, accepting current dialogue", rounds)
            break

    script["dialogue"] = dialogue
    final_seconds = _estimate_dialogue_seconds(dialogue)
    LOGGER.info("expansion.complete successful_extensions=%d final_seconds=%f target_seconds=%d", successful_extensions, final_seconds, target_seconds)
    return script


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
        speaker = turn.get("speaker", "Speaker")
        line = str(turn.get("line", "")).strip()
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


def run(language: str, level: str, use_multi_agent: bool = True) -> Path:
    run_start = time.perf_counter()
    LOGGER.info(
        "pipeline.start language=%s level=%s mode=%s",
        language,
        level,
        "multi_agent" if use_multi_agent else "single_agent",
    )

    with _stage("db_init"):
        init_db()
        seed_topics_from_config()

    with _stage("topic_selection"):
        topic = choose_next_topic(level=level)
        LOGGER.info(
            "topic.selected id=%s level=%s category=%s track=%s title=%s",
            topic.topic_id, topic.level, topic.category, topic.track, topic.title_hint,
        )

    with _stage("script_generation"):
        if use_multi_agent:
            script = run_multi_agent_content(
                WorkflowTopic(
                    topic_id=topic.topic_id,
                    topic_title=topic.title_hint,
                    track=topic.track,
                    language=language,
                )
            )
        else:
            script = generate_script(topic, language=language, level=topic.level)

    with _stage("script_expansion"):
        conversation_target_seconds = _conversation_target_seconds()
        script = _expand_script_to_target_duration(script, target_seconds=conversation_target_seconds)
        LOGGER.info(
            "script.expanded turns=%d est_seconds=%.2f target_seconds=%d",
            len(script.get("dialogue", [])),
            _estimate_dialogue_seconds(script.get("dialogue", [])),
            conversation_target_seconds,
        )

    with _stage("script_validation"):
        script_errors = validate_script_structure(script)
    if script_errors:
        raise ValueError(f"Script validation failed: {script_errors}")

    with _stage("metadata_generation"):
        playlist_name = _playlist_name(level, topic.track)
        if use_multi_agent:
            metadata = UploadPrepAgent().run(script, playlist_track=topic.track).get("upload_metadata", {})
            if not metadata:
                metadata = generate_metadata(script, playlist_track=topic.track)
        else:
            metadata = generate_metadata(script, playlist_track=topic.track)
        LOGGER.info("metadata.ready title=%s playlist=%s", metadata.get("title", ""), playlist_name)

    with _stage("description_validation"):
        description_errors = validate_description(metadata["description"])
    if description_errors:
        raise ValueError(f"Description validation failed: {description_errors}")

    # Prepare hierarchical output directory structure: output/{level}/{category}/{type}/
    level = topic.level
    category = topic.category
    title_slug = create_title_slug(metadata.get("title", topic.title_hint))
    
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
        LOGGER.info("voice.ready segments=%d", len(voice_plan.get("voice_segments", [])))

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
        LOGGER.info("subtitles.ready file=%s", subtitle_plan.get("srt_file", ""))

    with _stage("db_store_script"):
        canonical_script_id = store_canonical_script(
            topic_id=topic.topic_id,
            language=language,
            title=metadata["title"],
            script=script,
        )

    with _stage("db_store_publish_job"):
        scheduled_dt = next_publish_slot()
        publish_job_id = store_publish_job(
            canonical_script_id=canonical_script_id,
            playlist_track=topic.track,
            scheduled_at_iso=scheduled_dt.isoformat(),
            playlist_name=playlist_name,
        )
        LOGGER.info("publish.job.created id=%s schedule=%s", publish_job_id, scheduled_dt.isoformat())

    with _stage("script_export"):
        script_exports = _save_script_exports(
            out_dir=out_dir,
            canonical_script_id=canonical_script_id,
            topic_id=topic.topic_id,
            script=script,
            metadata=metadata,
        )

    artifact = {
        "topic": {
            "id": topic.topic_id,
            "track": topic.track,
            "title_hint": topic.title_hint,
        },
        "workflow_mode": "multi_agent" if use_multi_agent else "single_agent",
        "playlist": playlist_name,
        "canonical_script_id": canonical_script_id,
        "publish_job_id": publish_job_id,
        "scheduled_at": scheduled_dt.isoformat(),
        "script": script,
        "metadata": metadata,
        "voice": voice_plan,
        "subtitles": subtitle_plan,
        "timing": {
            "conversation_target_seconds": conversation_target_seconds,
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

    with _stage("db_save_artifact"):
        # Persist artifact JSON and path to database for later publishing
        save_episode_artifact(
            publish_job_id=publish_job_id,
            artifact_json=artifact,
            artifact_file_path=str(out_path),
        )
        LOGGER.info("artifact.persisted job_id=%s path=%s", publish_job_id, out_path)

    with _stage("db_update_artifacts"):
        update_publish_job_artifacts(
            publish_job_id=publish_job_id,
            artifact_path=str(out_path),
            video_file_path=stable_video_path,
        )

    with _stage("db_update_status"):
        if render_manifest.get("assembled"):
            update_publish_job_status(
                publish_job_id=publish_job_id,
                status="ready_for_upload",
                status_detail="Render complete. Ready for publish queue.",
            )
        else:
            update_publish_job_status(
                publish_job_id=publish_job_id,
                status="render_incomplete",
                status_detail=render_manifest.get("render_error", "Render incomplete"),
            )

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
    parser = argparse.ArgumentParser(description="Run Dutch video content MVP pipeline")
    parser.add_argument("--language", default="nl")
    parser.add_argument("--level", default="A1", choices=["A1", "A2", "B1", "B2"])
    parser.add_argument("--single-agent", action="store_true", help="Use original one-shot generation")
    parser.add_argument("--log-level", default="INFO", help="DEBUG, INFO, WARNING, ERROR")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    out_path = run(language=args.language, level=args.level, use_multi_agent=not args.single_agent)
    print(f"Pipeline completed. Artifact: {out_path}")


if __name__ == "__main__":
    main()
