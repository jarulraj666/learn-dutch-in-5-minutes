from __future__ import annotations

import argparse
import re
import sys
import json
import logging
import shutil
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from pipeline import settings
from pipeline.core.db import init_db, mark_topic_done, mark_topic_generated, seed_topics_from_config
from pipeline.core.select_topic import choose_next_topic
from pipeline.core.store_content import (
    create_title_slug,
    ensure_output_dir,
    store_canonical_script,
)
from pipeline.publish.render_video import render_from_artifact
from pipeline.publish.upload_youtube import build_upload_payload, upload_video
from pipeline.stages import (
    normalize_level,
    stage_image,
    stage_metadata,
    stage_qa_audio,
    stage_qa_subtitles,
    stage_render,
    stage_script,
    stage_subtitles,
    stage_upload,
    stage_upload_captions,
    stage_voice,
)
from pipeline.utils import iter_dialogue_turns


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


def _checkpoint_path(level: str, category: str, topic_id: str) -> Path:
    from pipeline.core.store_content import ensure_output_dir
    out_dir = ensure_output_dir(level, category)
    return out_dir / f".checkpoint_{topic_id}.json"


def _save_checkpoint(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    LOGGER.debug("checkpoint.saved %s", path)


def _load_checkpoint(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def run(language: str, level: str, category: str | None = None, upload: bool = True, resume_checkpoint: Path | None = None, topic_id: str | None = None) -> Path:
    run_start = time.perf_counter()
    LOGGER.info(
        "=== PIPELINE START language=%s level=%s category=%s topic_id=%s resume=%s ===",
        language, level, category or "auto", topic_id or "auto", resume_checkpoint or "none",
    )

    # --- Load checkpoint if resuming ---
    cp: dict = {}
    if resume_checkpoint and resume_checkpoint.exists():
        cp = _load_checkpoint(resume_checkpoint)
        level = cp.get("level", level)
        category = cp.get("category", category)
        LOGGER.info("checkpoint.loaded topic=%s completed_stages=%s", cp.get("topic_id"), cp.get("completed_stages", []))

    with _stage("db_init"):
        init_db()
        seed_topics_from_config()
        LOGGER.info("✓ Database initialized")

    completed_stages: list[str] = cp.get("completed_stages", [])

    # --- Topic selection ---
    if "topic_selection" in completed_stages:
        from pipeline.core.select_topic import TopicChoice
        td = cp["topic"]
        topic = TopicChoice(**td)
        level = normalize_level(topic.level)
        category = topic.category
        LOGGER.info("checkpoint.skip topic_selection — using saved topic: %s", topic.topic_id)
    else:
        with _stage("topic_selection"):
            if topic_id:
                from pipeline.core.db import get_topic_by_id
                from pipeline.core.select_topic import TopicChoice, _load_dialogue_metadata
                row = get_topic_by_id(topic_id)
                if row is None:
                    raise ValueError(f"Topic not found in database: {topic_id!r}")
                dialogue_metadata = _load_dialogue_metadata(row["id"])
                topic = TopicChoice(
                    topic_id=row["id"],
                    track=row["track"],
                    title_hint=row["title_hint"],
                    level=normalize_level(row["level"]),
                    category=row["category"],
                    scenario=dialogue_metadata.get("scenario"),
                    speaker1_role=dialogue_metadata.get("speaker1_role"),
                    speaker2_role=dialogue_metadata.get("speaker2_role"),
                    speaker1_gender=dialogue_metadata.get("speaker1_gender"),
                    speaker2_gender=dialogue_metadata.get("speaker2_gender"),
                )
            else:
                topic = choose_next_topic(level=level, category=category)
            level = normalize_level(topic.level)
            category = topic.category
            LOGGER.info(
                "✓ Topic selected: %s | level=%s category=%s track=%s",
                topic.title_hint, topic.level, topic.category, topic.track,
            )
        cp.update({"level": level, "category": category, "topic_id": topic.topic_id,
                   "topic": topic.__dict__, "language": language})
        completed_stages.append("topic_selection")
        cp["completed_stages"] = completed_stages
        chk = _checkpoint_path(level, category, topic.topic_id)
        _save_checkpoint(chk, cp)

    # --- Script generation ---
    if "script_generation" in completed_stages:
        script = cp["script"]
        LOGGER.info("checkpoint.skip script_generation")
    else:
        with _stage("script_generation"):
            script = stage_script(topic, language=language, level=level)
            LOGGER.info("✓ Script generated: %d dialogue lines", len(script.get("dialogue", [])))
        cp["script"] = script
        completed_stages.append("script_generation")
        cp["completed_stages"] = completed_stages
        _save_checkpoint(_checkpoint_path(level, category, topic.topic_id), cp)

    # --- Metadata generation ---
    if "metadata_generation" in completed_stages:
        playlist_name = cp["playlist_name"]
        playlist_description = cp["playlist_description"]
        playlist_id = cp.get("playlist_id", "")
        metadata = cp["metadata"]
        LOGGER.info("checkpoint.skip metadata_generation")
    else:
        with _stage("metadata_generation"):
            playlist_name, playlist_description, playlist_id, metadata = stage_metadata(
                script,
                category=category,
                level=level,
            )
            LOGGER.info("✓ Metadata: title=%s | playlist=%s", metadata.get("title", ""), playlist_name)
        cp.update(
            {
                "playlist_name": playlist_name,
                "playlist_description": playlist_description,
                "playlist_id": playlist_id,
                "metadata": metadata,
            }
        )
        completed_stages.append("metadata_generation")
        cp["completed_stages"] = completed_stages
        _save_checkpoint(_checkpoint_path(level, category, topic.topic_id), cp)

    # Prepare hierarchical output directory structure: output/{level}/{category}/{type}/episode_{topic_id}_{title_slug}/
    title_slug = create_title_slug(topic.title_hint)
    out_dir = ensure_output_dir(level, category)
    ensure_output_dir(level, category, "audio")
    ensure_output_dir(level, category, "visuals")
    ensure_output_dir(level, category, "videos")
    ensure_output_dir(level, category, "subtitles")
    out_path = out_dir / f"episode_{topic.topic_id}_{title_slug}.json"
    LOGGER.info("output.dirs.ready level=%s category=%s slug=%s base=%s", level, category, title_slug, out_dir)

    chk_path = _checkpoint_path(level, category, topic.topic_id)

    # --- Artifact: load existing or create initial version ---
    # Written after every stage so it always reflects the latest state.
    if out_path.exists():
        artifact: dict = json.loads(out_path.read_text(encoding="utf-8"))
        LOGGER.info("artifact.loaded %s", out_path)
    else:
        artifact = {
            "level": level,
            "category": category,
            "topic_id": topic.topic_id,
            "title_slug": title_slug,
            "topic": {
                "id": topic.topic_id,
                "level": level,
                "category": category,
                "track": topic.track,
                "title_slug": title_slug,
                "title_hint": topic.title_hint,
                "scenario": topic.scenario,
            },
            "workflow_mode": "single_agent",
            "playlist": playlist_name,
            "playlist_description": playlist_description,
            "playlist_id": playlist_id,
            "script": script,
            "metadata": metadata,
            "storage": {"artifact_file": str(out_path)},
        }
        out_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
        LOGGER.info("artifact.created %s", out_path)

    artifact["playlist"] = playlist_name
    artifact["playlist_description"] = playlist_description
    artifact["playlist_id"] = playlist_id

    def _write_artifact() -> None:
        artifact["storage"]["artifact_file"] = str(out_path)

        out_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")

    # --- Voice generation ---
    if "voice_generation" in completed_stages:
        voice_plan = cp["voice_plan"]
        LOGGER.info("checkpoint.skip voice_generation — audio: %s", voice_plan.get("dialogue_audio"))
    else:
        with _stage("voice_generation"):
            voice_plan = stage_voice(
                script, output_root=out_dir, level=level, category=category,
                topic_id=topic.topic_id, title_slug=title_slug,
            )
            LOGGER.info("\u2713 Voice generated: %s", voice_plan.get("dialogue_audio", ""))
        cp["voice_plan"] = voice_plan
        completed_stages.append("voice_generation")
        cp["completed_stages"] = completed_stages
        _save_checkpoint(chk_path, cp)

    artifact.update({
        "audio_file": voice_plan.get("dialogue_audio", ""),
        "audio_file_raw": voice_plan.get("dialogue_audio_raw", voice_plan.get("dialogue_audio", "")),
        "voice": voice_plan,
    })
    _write_artifact()

    # --- Audio QA (blocks upload if score < 100%) ---
    _qa_passed: bool = True
    if settings.QA_AUDIO_CHECK:
        try:
            from pipeline.generate.qa_audio import log_qa_report, run_audio_qa
            _qa_wav = voice_plan.get("dialogue_audio")
            if _qa_wav and Path(_qa_wav).exists():
                _qa_report = run_audio_qa(
                    wav_path=_qa_wav,
                    script_dialogue=script.get("dialogue", []),
                    language=script.get("language", "nl"),
                )
                log_qa_report(_qa_report, wav_name=Path(_qa_wav).name)
                _qa_passed = _qa_report.passed
                if not _qa_passed:
                    LOGGER.warning("qa_audio.upload_blocked — score %.1f/100 below threshold, upload will be skipped", _qa_report.score)
            else:
                LOGGER.debug("qa_audio.skip — no WAV path available")
        except Exception:
            LOGGER.warning("qa_audio.error — QA check failed (non-blocking)", exc_info=True)

    # --- Subtitle generation ---
    if "subtitle_generation" in completed_stages:
        subtitle_plan = cp["subtitle_plan"]
        LOGGER.info("checkpoint.skip subtitle_generation")
    else:
        with _stage("subtitle_generation"):
            dialogue_audio_path = voice_plan.get("dialogue_audio")
            if not dialogue_audio_path:
                raise RuntimeError("No dialogue audio path from voice generation")
            subtitle_plan = stage_subtitles(
                dialogue_audio_path, output_root=out_dir, level=level, category=category,
                topic_id=topic.topic_id, title_slug=title_slug,
                script_dialogue=script.get("dialogue"), dialogue_en=script.get("dialogue_en"),
            )
            LOGGER.info("\u2713 Subtitles generated: %s", subtitle_plan.get("srt_file", ""))
        cp["subtitle_plan"] = subtitle_plan
        completed_stages.append("subtitle_generation")
        cp["completed_stages"] = completed_stages
        _save_checkpoint(chk_path, cp)

    artifact.update({
        "karaoke_file": subtitle_plan.get("karaoke_file", ""),
        "subtitles": subtitle_plan,
    })
    _write_artifact()

    # --- Subtitle QA (non-blocking) ---
    if settings.QA_SUBTITLE_CHECK:
        try:
            from pipeline.generate.qa_subtitles import (
                log_subtitle_qa_report,
                run_ass_qa,
                run_srt_qa,
            )
            _script_dialogue = script.get("dialogue", [])
            _expected_lines = len(_script_dialogue) if _script_dialogue else None
            _ass_file = subtitle_plan.get("karaoke_file", "")
            if _ass_file and Path(_ass_file).exists():
                _ass_report = run_ass_qa(_ass_file, expected_count=_expected_lines)
                log_subtitle_qa_report(_ass_report)
                if not _ass_report.passed:
                    LOGGER.warning("qa_subtitles.ass.hard_failures — check karaoke timing")
            _srt_file = subtitle_plan.get("srt_en", "")
            if _srt_file and Path(_srt_file).exists():
                _srt_report = run_srt_qa(_srt_file, expected_count=_expected_lines)
                log_subtitle_qa_report(_srt_report)
                if not _srt_report.passed:
                    LOGGER.warning("qa_subtitles.srt.hard_failures — check SRT timing")
        except Exception:
            LOGGER.warning("qa_subtitles.error — subtitle QA failed (non-blocking)", exc_info=True)

    # --- Image generation ---
    if "image_generation" in completed_stages:
        generated_image_file = cp["generated_image_file"]
        generated_image_files = cp.get("generated_image_files", [])
        LOGGER.info("checkpoint.skip image_generation — %s", generated_image_file)
    else:
        with _stage("image_generation"):
            generated_image_file, generated_image_files = stage_image(
                topic_id=topic.topic_id,
                topic_title=script.get("topic_title", topic.title_hint),
                image_prompt=script.get("image_prompt", ""),
                image_prompts=script.get("image_prompts", []),
                level=level,
                category=category,
                output_root=out_dir,
            )
            if not generated_image_file:
                raise RuntimeError("Image generation returned no file path.")
            LOGGER.info("\u2713 Image generated: %s (%d scene images)", generated_image_file, len(generated_image_files))
        cp["generated_image_file"] = generated_image_file
        cp["generated_image_files"] = generated_image_files
        completed_stages.append("image_generation")
        cp["completed_stages"] = completed_stages
        _save_checkpoint(chk_path, cp)

    artifact.update({
        "generated_image_file": generated_image_file or "",
        "generated_image_files": generated_image_files or [],
    })
    _write_artifact()

    with _stage("db_store_script"):
        canonical_script_id = store_canonical_script(
            topic_id=topic.topic_id,
            language=language,
            title=metadata["title"],
            script=script,
        )

    artifact["canonical_script_id"] = canonical_script_id
    _write_artifact()

    with _stage("script_export"):
        script_exports = _save_script_exports(
            out_dir=out_dir,
            canonical_script_id=canonical_script_id,
            topic_id=topic.topic_id,
            script=script,
            metadata=metadata,
        )

    artifact.setdefault("storage", {})["script_exports"] = script_exports
    _write_artifact()

    # --- Render video ---
    with _stage("render_video"):
        render_manifest_path = stage_render(out_path)
        mark_topic_generated(topic.topic_id)
        LOGGER.info("topic.generated id=%s", topic.topic_id)
        render_manifest = json.loads(render_manifest_path.read_text(encoding="utf-8"))
        artifact["upload_payload_preview"] = build_upload_payload(out_path)
        artifact["render"] = render_manifest
        LOGGER.info("render.ready assembled=%s video=%s",
                    render_manifest.get("assembled"), render_manifest.get("planned_video_file", ""))

    planned_video_file = render_manifest.get("planned_video_file", "")
    stable_video_path = planned_video_file
    if render_manifest.get("assembled") and planned_video_file:
        video_path = Path(planned_video_file)
        if video_path.exists():
            with _stage("archive_video"):
                archived_path = _archive_video(video_path, canonical_script_id)
            stable_video_path = str(archived_path)
            artifact.setdefault("storage", {})["archived_video_file"] = str(archived_path)

    _write_artifact()

    if upload:
        video_path_for_upload = Path(stable_video_path) if stable_video_path else None
        if not _qa_passed:
            LOGGER.warning("\u26a0 Upload skipped — audio QA did not pass 100%%. Fix the audio and re-run with --upload.")
        elif video_path_for_upload and video_path_for_upload.exists():
            with _stage("upload_youtube"):
                try:
                    result = stage_upload(out_path, video_path_for_upload)
                    artifact["youtube"] = result
                    _write_artifact()
                    LOGGER.info("\u2713 Uploaded to YouTube: video_id=%s playlist=%s",
                                result.get("video_id"), result.get("playlist_name"))
                    mark_topic_done(topic.topic_id)
                    LOGGER.info("topic.done id=%s", topic.topic_id)
                except Exception as exc:
                    LOGGER.warning("\u26a0 YouTube upload failed (video saved locally): %s", exc)
        else:
            LOGGER.warning("\u26a0 Upload skipped — no rendered video found at: %s", stable_video_path)

    LOGGER.info("pipeline.done episode=%s elapsed_sec=%.2f artifact=%s",
                canonical_script_id, time.perf_counter() - run_start, out_path)

    # Clean up checkpoint on successful completion
    chk_path = _checkpoint_path(level, category, topic.topic_id)
    if chk_path.exists():
        chk_path.unlink()
        LOGGER.info("checkpoint.cleared %s", chk_path)

    return out_path



# =============================================================================
# Artifact-mode: stage runners + interactive menu (used with --artifact)
# =============================================================================

# ---------------------------------------------------------------------------
# Artifact helpers
# ---------------------------------------------------------------------------

def load_artifact(artifact_path: str) -> dict:
    path = Path(artifact_path)
    if not path.exists():
        raise FileNotFoundError(f"Artifact not found: {artifact_path}")
    artifact = json.loads(path.read_text(encoding="utf-8"))
    _normalize(artifact)
    return artifact


def _save_artifact(artifact_path: str, artifact: dict) -> None:
    Path(artifact_path).write_text(
        json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _normalize(artifact: dict) -> None:
    """Normalize level values in-place (A1/A2 → A1A2)."""
    artifact["level"] = normalize_level(artifact.get("level", ""))
    topic = artifact.get("topic", {})
    if topic:
        topic["level"] = normalize_level(topic.get("level", ""))


def _topic_from_artifact(artifact: dict):
    """Reconstruct a TopicChoice from an existing artifact."""
    from pipeline.core.select_topic import TopicChoice
    topic_meta = artifact.get("topic", {})
    script_meta = artifact.get("script", {})
    speakers = script_meta.get("speakers", [])
    s1 = next((s for s in speakers if s.get("id") == "Speaker1"), {})
    s2 = next((s for s in speakers if s.get("id") == "Speaker2"), {})

    if not s1 and artifact["category"] == "dialogue":
        try:
            from pipeline.core.select_topic import _load_dialogue_metadata
            backlog = _load_dialogue_metadata(artifact["topic_id"])
            s1 = {"role": backlog.get("speaker1_role"), "gender": backlog.get("speaker1_gender")}
            s2 = {"role": backlog.get("speaker2_role"), "gender": backlog.get("speaker2_gender")}
            scenario = topic_meta.get("scenario") or script_meta.get("scenario") or backlog.get("scenario")
        except Exception:
            scenario = topic_meta.get("scenario") or script_meta.get("scenario")
    else:
        scenario = topic_meta.get("scenario") or script_meta.get("scenario")

    return TopicChoice(
        topic_id=artifact["topic_id"],
        track=topic_meta.get("track", ""),
        title_hint=topic_meta.get("title_hint", artifact.get("topic_title", "")),
        level=artifact["level"],
        category=artifact["category"],
        scenario=scenario,
        speaker1_role=s1.get("role"),
        speaker1_gender=s1.get("gender"),
        speaker2_role=s2.get("role"),
        speaker2_gender=s2.get("gender"),
    )


# ---------------------------------------------------------------------------
# Stage runners — thin wrappers: load artifact → call stage → save artifact
# ---------------------------------------------------------------------------

def run_script(artifact_path: str) -> None:
    artifact = load_artifact(artifact_path)
    print(f"🎯 Re-generating script for: {artifact['title_slug']}")
    topic = _topic_from_artifact(artifact)
    script = stage_script(topic, language="nl", level=artifact["level"])
    artifact["script"] = script
    artifact["topic_title"] = script.get("topic_title", artifact.get("topic_title"))
    artifact["image_prompt"] = script.get("image_prompt", "")
    _save_artifact(artifact_path, artifact)
    print("✅ Script regenerated")


def run_audio(artifact_path: str) -> str:
    artifact = load_artifact(artifact_path)
    print(f"🎯 Re-generating audio for: {artifact['title_slug']}")
    voice_plan = stage_voice(
        script=artifact.get("script", {}),
        output_root=Path(artifact_path).parent,
        level=artifact["level"],
        category=artifact["category"],
        topic_id=artifact["topic_id"],
        title_slug=artifact["title_slug"],
    )
    artifact["voice"] = voice_plan
    artifact["audio_file"] = voice_plan.get("dialogue_audio", "")
    artifact["audio_file_raw"] = voice_plan.get("dialogue_audio_raw", voice_plan.get("dialogue_audio", ""))
    _save_artifact(artifact_path, artifact)
    print("✅ Audio regenerated")
    return artifact["audio_file"]


def run_subtitles(artifact_path: str, audio_path: Optional[str] = None) -> None:
    artifact = load_artifact(artifact_path)
    audio_path = audio_path or artifact.get("audio_file")
    if not audio_path or not Path(audio_path).exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    print(f"🎯 Re-generating subtitles for: {artifact['title_slug']}")
    subtitle_plan = stage_subtitles(
        audio_path=audio_path,
        output_root=Path(artifact_path).parent,
        level=artifact["level"],
        category=artifact["category"],
        topic_id=artifact["topic_id"],
        title_slug=artifact["title_slug"],
        script_dialogue=artifact.get("script", {}).get("dialogue"),
        dialogue_en=artifact.get("script", {}).get("dialogue_en"),
    )
    artifact["subtitles"] = subtitle_plan
    artifact["karaoke_file"] = subtitle_plan.get("karaoke_file", "")
    _save_artifact(artifact_path, artifact)
    print("✅ Subtitles regenerated")


def run_image(artifact_path: str) -> None:
    artifact = load_artifact(artifact_path)
    print(f"🎯 Re-generating image for: {artifact['title_slug']}")
    script = artifact.get("script", {})
    primary, all_files = stage_image(
        topic_id=artifact["topic_id"],
        topic_title=artifact.get("topic_title", ""),
        image_prompt=script.get("image_prompt") or artifact.get("image_prompt", ""),
        image_prompts=script.get("image_prompts") or artifact.get("image_prompts", []),
        level=artifact["level"],
        category=artifact["category"],
        output_root=Path(artifact_path).parent,
    )
    artifact["generated_image_file"] = primary
    artifact["generated_image_files"] = all_files
    _save_artifact(artifact_path, artifact)
    print(f"✅ Image regenerated ({len(all_files) or 1} image(s))")


def run_render(artifact_path: str) -> str:
    artifact = load_artifact(artifact_path)
    print(f"🎯 Re-rendering video for: {artifact['title_slug']}")
    manifest_path = stage_render(artifact_path)
    # Load and save manifest to artifact
    render_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifact["render"] = render_manifest
    _save_artifact(artifact_path, artifact)
    video_file = render_manifest.get("planned_video_file", "")
    print(f"✅ Video re-rendered: {video_file}")
    return str(video_file)


def run_upload(artifact_path: str, video_path: Optional[str] = None) -> None:
    artifact = load_artifact(artifact_path)
    if not video_path:
        video_path = artifact.get("render", {}).get("planned_video_file") or artifact.get("video_file")
    if not video_path or not Path(video_path).exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")
    print(f"🎯 Uploading to YouTube: {artifact['title_slug']}")
    result = stage_upload(artifact_path, video_path)
    artifact["youtube"] = result
    _save_artifact(artifact_path, artifact)
    # Mark topic done in DB now that upload succeeded
    _topic_id = artifact.get("topic_id")
    if _topic_id:
        from pipeline.core.db import mark_topic_done
        mark_topic_done(_topic_id)
    print(f"✅ Uploaded: video_id={result.get('video_id')}")


def run_captions(artifact_path: str, video_id: Optional[str] = None) -> None:
    artifact = load_artifact(artifact_path)
    video_id = video_id or artifact.get("youtube", {}).get("video_id", "")
    if not video_id:
        raise ValueError("No YouTube video_id found. Pass --video-id or upload first.")
    srt_path = (artifact.get("subtitles") or {}).get("srt_en", "")
    if not srt_path or not Path(srt_path).exists():
        raise FileNotFoundError(f"English SRT not found: {srt_path}")
    print(f"🎯 Uploading captions for video_id={video_id}")
    result = stage_upload_captions(artifact_path, video_id, srt_path)
    if result:
        caption_id = result.get("id")
        language = result.get("snippet", {}).get("language", "en")
        artifact.setdefault("youtube", {}).setdefault("captions_uploaded", [])
        if caption_id not in {c.get("caption_id") for c in artifact["youtube"]["captions_uploaded"]}:
            artifact["youtube"]["captions_uploaded"].append({
                "caption_id": caption_id, "language": language,
                "name": result.get("snippet", {}).get("name", "English"),
                "srt_file": str(srt_path),
            })
        _save_artifact(artifact_path, artifact)
        print(f"✅ Caption uploaded: id={caption_id}")
    else:
        print("⚠️  Caption upload returned no result (possibly already exists).")


def run_qa(artifact_path: str) -> None:
    from pipeline.generate.qa_audio import log_qa_report
    artifact = load_artifact(artifact_path)
    audio_path = artifact.get("audio_file_raw") or artifact.get("audio_file") or \
                 artifact.get("voice", {}).get("dialogue_audio", "")
    if not audio_path or not Path(audio_path).exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    dialogue = artifact.get("script", {}).get("dialogue")
    if not dialogue:
        raise ValueError("No script.dialogue found in artifact")
    print(f"🎯 Running audio QA for: {artifact['title_slug']}")
    report = stage_qa_audio(audio_path, dialogue, language=artifact.get("script", {}).get("language", "nl"))
    log_qa_report(report, wav_name=Path(audio_path).name)
    
    # Calculate audio QA score
    score = 100.0
    issue_counts = {}
    for issue in report.issues:
        issue_type = issue.issue_type
        issue_counts[issue_type] = issue_counts.get(issue_type, 0) + 1
    
    # Deduct points for each issue type
    if "MISSING" in issue_counts:
        deduction = issue_counts["MISSING"] * 15  # -15 per missing sentence
        score -= deduction
        print(f"  ❌ Missing: {issue_counts['MISSING']} sentence(s) → -{deduction} points")
    
    if "TRUNCATED" in issue_counts:
        deduction = issue_counts["TRUNCATED"] * 8  # -8 per truncated
        score -= deduction
        print(f"  ⚠️  Truncated: {issue_counts['TRUNCATED']} sentence(s) → -{deduction} points")
    
    if "WRONG_ORDER" in issue_counts:
        deduction = issue_counts["WRONG_ORDER"] * 5  # -5 per wrong order
        score -= deduction
        print(f"  ⚠️  Wrong order: {issue_counts['WRONG_ORDER']} sentence(s) → -{deduction} points")
    
    score = max(0, score)  # Don't go below 0
    print(f"\n🎯 Audio QA Score: {score:.1f}/100")
    
    if score < 100:
        raise ValueError(f"❌ Audio QA failed with score {score:.1f}/100. Fix audio issues before proceeding.")


def run_qa_subtitles(artifact_path: str) -> None:
    from pipeline.generate.qa_subtitles import log_subtitle_qa_report
    artifact = load_artifact(artifact_path)
    subs = artifact.get("subtitles") or {}
    ass_file = artifact.get("karaoke_file") or subs.get("karaoke_file")
    srt_file = subs.get("srt_en") or subs.get("srt_files", {}).get("en")
    expected = len(artifact.get("script", {}).get("dialogue") or []) or None
    print(f"🎯 Running subtitle QA for: {artifact['title_slug']}")
    ass_report, srt_report = stage_qa_subtitles(ass_file, srt_file, expected)
    
    total_score = 100.0
    ran_any = False
    any_failed = False
    
    if ass_report:
        log_subtitle_qa_report(ass_report)
        ran_any = True
        
        # Calculate ASS score
        ass_score = 100.0
        issue_counts = {}
        for issue in ass_report.issues:
            issue_type = issue.issue_type
            issue_counts[issue_type] = issue_counts.get(issue_type, 0) + 1
        
        # Hard issues: -20 each (critical failures)
        hard_issues = ass_report.hard_issues
        if hard_issues:
            deduction = len(hard_issues) * 20
            ass_score -= deduction
            print(f"  ❌ Hard issues in ASS: {len(hard_issues)} → -{deduction} points")
            any_failed = True
        
        # Soft issues: -3 each (warnings)
        soft_issues = [i for i in ass_report.issues if i not in hard_issues]
        if soft_issues:
            deduction = len(soft_issues) * 3
            ass_score -= deduction
            print(f"  ⚠️  Warnings in ASS: {len(soft_issues)} → -{deduction} points")
        
        ass_score = max(0, ass_score)
        print(f"  📝 ASS Subtitle Score: {ass_score:.1f}/100")
        total_score = min(total_score, ass_score)
    else:
        print("⚠️  No ASS subtitle file found (skipping ASS QA)")
    
    if srt_report:
        log_subtitle_qa_report(srt_report)
        ran_any = True
        
        # Calculate SRT score
        srt_score = 100.0
        
        # Hard issues: -20 each
        hard_issues = srt_report.hard_issues
        if hard_issues:
            deduction = len(hard_issues) * 20
            srt_score -= deduction
            print(f"  ❌ Hard issues in SRT: {len(hard_issues)} → -{deduction} points")
            any_failed = True
        
        # Soft issues: -3 each
        soft_issues = [i for i in srt_report.issues if i not in hard_issues]
        if soft_issues:
            deduction = len(soft_issues) * 3
            srt_score -= deduction
            print(f"  ⚠️  Warnings in SRT: {len(soft_issues)} → -{deduction} points")
        
        srt_score = max(0, srt_score)
        print(f"  📝 SRT Subtitle Score: {srt_score:.1f}/100")
        total_score = min(total_score, srt_score)
    else:
        print("ℹ️  No SRT subtitle file found (skipping SRT QA)")
    
    if not ran_any:
        print("⚠️  No subtitle files found — run --subtitles first")
        return
    
    print(f"\n🎯 Subtitle QA Final Score: {total_score:.1f}/100")
    
    if total_score < 100:
        raise ValueError(f"❌ Subtitle QA failed with score {total_score:.1f}/100. Fix subtitle issues before proceeding.")


# ---------------------------------------------------------------------------
# Interactive stage menu (used with --artifact)
# ---------------------------------------------------------------------------

_STAGES = [
    ("Script",          run_script),
    ("Image",           run_image),
    ("Audio",           run_audio),
    ("Subtitles",       run_subtitles),
    ("Audio QA",        run_qa),
    ("Subtitle QA",     run_qa_subtitles),
    ("Render video",    run_render),
    ("Upload YouTube",  run_upload),
    ("Upload captions", run_captions),
]


def _parse_selection(raw: str, max_n: int) -> list[int]:
    """Parse a stage selection string like '1 3 7' or '2,4' into 0-based indices."""
    tokens = re.split(r"[\s,]+", raw.strip())
    indices = []
    for tok in tokens:
        if not tok:
            continue
        try:
            n = int(tok)
        except ValueError:
            print(f"  ⚠  '{tok}' is not a number — ignored")
            continue
        if n < 0 or n > max_n:
            print(f"  ⚠  {n} is out of range — ignored")
            continue
        indices.append(n - 1)   # convert to 0-based
    return indices


def interactive_menu(artifact_path: str) -> None:
    artifact = load_artifact(artifact_path)
    title = artifact.get("title_slug", artifact.get("topic_id", "unknown"))
    level = artifact.get("level", "")
    category = artifact.get("category", "")

    print(f"\n📺  {title}")
    print(f"    Level: {level} | Category: {category}\n")

    for i, (name, _) in enumerate(_STAGES, 1):
        print(f"  {i:2d}) {name}")

    print(
        "\nSelect stages to run — space or comma separated (e.g. '3 4 7')\n"
        "Type 'all' to run every stage, or '0' to exit.\n"
    )

    raw = input("> ").strip()
    if raw == "0" or raw.lower() == "exit":
        print("Exiting.")
        return
    if raw.lower() == "all":
        selected = list(range(len(_STAGES)))
    else:
        selected = _parse_selection(raw, len(_STAGES))

    if not selected:
        print("No valid stages selected.")
        return

    for idx in selected:
        name, fn = _STAGES[idx]
        print(f"\n▶  Running: {name}")
        try:
            fn(artifact_path)
        except Exception as exc:
            print(f"  ❌ {name} failed: {exc}")
            LOGGER.exception("interactive_menu.stage_failed stage=%s", name)
            raise


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Dutch video content pipeline, or re-run stages on an existing artifact",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full pipeline — auto-select next pending topic
  python -m pipeline.run_pipeline --level A1A2 --category dialogue

  # Full pipeline — pinned topic
  python -m pipeline.run_pipeline --topic-id weather_chat --no-upload

  # Interactive stage re-run on existing artifact
  python -m pipeline.run_pipeline --artifact output/A1A2/dialogue/episode_xxx.json

  # Batch mode
  python -m pipeline.run_pipeline --level A1A2 --category dialogue --count 5
        """,
    )
    parser.add_argument("--artifact", metavar="PATH",
                        help="Path to an existing artifact JSON. Shows interactive stage menu instead of running the full pipeline.")
    parser.add_argument("--language", default="nl", help="Target language code (default: nl)")
    parser.add_argument("--level", default="A1A2", choices=["A1A2", "B1", "B2"], help="CEFR level")
    parser.add_argument(
        "--category",
        choices=["common_words", "grammar", "vocabulary", "dialogue"],
        default=None,
        help="Filter by category. Runs all pending videos unless --single or --count is also set.",
    )
    parser.add_argument("--single", action="store_true", help="Generate only one video (next pending) even when --category is set")
    parser.add_argument("--count", type=int, default=None, help="Generate a specific number of videos in batch mode (e.g., --count 5)")
    parser.add_argument("--log-level", default="INFO", help="DEBUG, INFO, WARNING, ERROR")
    parser.add_argument("--no-upload", action="store_true", help="Skip YouTube upload after rendering")
    parser.add_argument("--topic-id", metavar="TOPIC_ID", help="Run pipeline for a specific topic ID instead of auto-selecting the next pending topic")
    parser.add_argument("--script-only", action="store_true", help="Generate only the script and create/update artifact (skip all other stages)")
    parser.add_argument("--resume", metavar="CHECKPOINT", help="Resume from a checkpoint file (output/{level}/{category}/.checkpoint_{topic_id}.json)")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    # ── ARTIFACT MODE: interactive stage re-run on existing episode ──────────
    if args.artifact:
        try:
            interactive_menu(args.artifact)
        except Exception as e:
            LOGGER.exception("artifact_mode.failed")
            print(f"\u274c Error: {e}", file=sys.stderr)
            sys.exit(1)
        return

    # ── SCRIPT-ONLY MODE: generate script, create/update artifact ─────────────
    if args.script_only:
        if not args.topic_id:
            print("✗ --script-only requires --topic-id", file=sys.stderr)
            sys.exit(1)
        try:
            from pipeline.core.select_topic import TopicChoice, _load_dialogue_metadata
            from pipeline.core.db import get_topic_by_id, init_db, seed_topics_from_config
            init_db()
            seed_topics_from_config()
            
            row = get_topic_by_id(args.topic_id)
            if row is None:
                raise ValueError(f"Topic not found: {args.topic_id}")
            
            dialogue_metadata = _load_dialogue_metadata(row["id"])
            topic = TopicChoice(
                topic_id=row["id"],
                track=row["track"],
                title_hint=row["title_hint"],
                level=normalize_level(row["level"]),
                category=row["category"],
                scenario=dialogue_metadata.get("scenario"),
                speaker1_role=dialogue_metadata.get("speaker1_role"),
                speaker2_role=dialogue_metadata.get("speaker2_role"),
                speaker1_gender=dialogue_metadata.get("speaker1_gender"),
                speaker2_gender=dialogue_metadata.get("speaker2_gender"),
            )
            
            level = normalize_level(row["level"])
            category = row["category"]
            title_slug = create_title_slug(topic.title_hint)
            out_dir = ensure_output_dir(level, category)
            out_path = out_dir / f"episode_{args.topic_id}_{title_slug}.json"
            
            # Generate script and metadata
            script = stage_script(topic, language="nl", level=level)
            playlist_name, playlist_description, playlist_id, metadata = stage_metadata(
                script,
                category=category,
                level=level,
            )
            
            # Create or load artifact
            if out_path.exists():
                artifact = load_artifact(str(out_path))
                LOGGER.info("artifact.loaded %s", out_path)
            else:
                artifact = {
                    "level": level,
                    "category": category,
                    "topic_id": args.topic_id,
                    "title_slug": title_slug,
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
                    "playlist_id": playlist_id,
                    "storage": {"artifact_file": str(out_path)},
                }
                LOGGER.info("artifact.created %s", out_path)
            
            # Update with script and metadata
            artifact.update(
                {
                    "playlist": playlist_name,
                    "playlist_description": playlist_description,
                    "playlist_id": playlist_id,
                    "script": script,
                    "metadata": metadata,
                }
            )
            _save_artifact(str(out_path), artifact)
            
            print(f"\u2713 Script-only complete. Artifact: {out_path}")
            return
        except Exception as e:
            LOGGER.exception("script_only.failed")
            print(f"\u274c Error: {e}", file=sys.stderr)
            sys.exit(1)

    if args.resume:
        # Resume mode: load checkpoint and run from where it left off
        resume_path = Path(args.resume)
        if not resume_path.exists():
            print(f"✗ Checkpoint not found: {args.resume}")
            return
        cp = json.loads(resume_path.read_text(encoding="utf-8"))
        out_path = run(
            language=cp.get("language", args.language),
            level=cp.get("level", args.level),
            category=cp.get("category", args.category),
            upload=not args.no_upload,
            resume_checkpoint=resume_path,
            topic_id=getattr(args, "topic_id", None),
        )
        print(f"\n✓ Pipeline resumed and completed. Artifact: {out_path}")
        return

    # Determine how many videos to generate (batch vs single)
    # Priority: --count > --single > default behavior
    video_count = None
    if args.count is not None:
        video_count = args.count
    elif args.single:
        video_count = 1
    elif args.category:
        # Batch mode: generate all pending topics
        video_count = float('inf')
    else:
        # No category, no single, no count: default to single
        video_count = 1

    if video_count > 1 or video_count == float('inf'):
        # Batch mode: generate multiple videos
        completed = []
        failed = []
        video_num = 1
        max_videos = video_count if video_count != float('inf') else float('inf')
        
        while video_num <= max_videos:
            LOGGER.info(
                "\n=== VIDEO %d / %s | category=%s ===", 
                video_num, 
                "unlimited" if max_videos == float('inf') else int(max_videos),
                args.category
            )
            try:
                out_path = run(language=args.language, level=args.level, category=args.category, upload=not args.no_upload, topic_id=getattr(args, "topic_id", None))
                completed.append(str(out_path))
                LOGGER.info("✓ Video %d done: %s", video_num, out_path)
                video_num += 1
            except (RuntimeError, Exception) as exc:
                if "No pending or selected topics" in str(exc):
                    LOGGER.info("✓ All topics are done.")
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
        # Single mode: one video, optionally filtered by category or pinned to a topic_id
        out_path = run(language=args.language, level=args.level, category=args.category, upload=not args.no_upload, topic_id=getattr(args, "topic_id", None))
        print(f"\n✓ Pipeline completed. Artifact: {out_path}")


if __name__ == "__main__":
    main()
