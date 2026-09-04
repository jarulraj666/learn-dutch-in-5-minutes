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
from pipeline.core.db import init_db, mark_topic_generated, seed_topics_from_config
from pipeline.core.select_topic import choose_next_topic
from pipeline.core.store_content import (
    create_title_slug,
    ensure_output_dir,
    save_episode_artifact,
    store_canonical_script,
    store_publish_job,
    update_publish_job_artifacts,
)
from pipeline.publish.render_video import render_from_artifact
from pipeline.publish.upload_youtube import build_upload_payload, upload_video
from pipeline.stages import (
    normalize_level,
    stage_generate_shorts,
    stage_generate_shorts_images,
    stage_expression_tags,
    stage_image,
    stage_metadata,
    stage_qa_audio,
    stage_qa_subtitles,
    stage_quiz,
    stage_render,
    stage_script,
    stage_subtitles,
    stage_upload,
    stage_upload_captions,
    stage_upload_short,
    stage_upload_short_instagram,
    stage_upload_short_tiktok,
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


def _select_seed_image() -> str:
    """Pick a random seed image from visual_style.yaml and return its workspace-relative path.

    Returns an empty string if no seed images are configured or found.
    """
    import random as _random
    render_cfg = settings.load_yaml(settings.ROOT / "config/visual_style.yaml").get("render", {})
    seed_rels = render_cfg.get("dialogue_seed_images") or (
        [render_cfg["dialogue_seed_image"]] if render_cfg.get("dialogue_seed_image") else []
    )
    valid = [settings.ROOT / r for r in seed_rels if (settings.ROOT / r).exists()]
    if not valid:
        if seed_rels:
            LOGGER.warning("seed_image: none of the configured paths exist: %s", seed_rels)
        return ""
    chosen = _random.choice(valid)
    try:
        rel = str(chosen.relative_to(settings.ROOT))
    except ValueError:
        rel = str(chosen)
    LOGGER.info("seed_image.selected path=%s", rel)
    return rel



def run(language: str, level: str, category: str | None = None, upload: bool = True, resume_artifact: Path | None = None, topic_id: str | None = None) -> Path:
    run_start = time.perf_counter()
    LOGGER.info(
        "=== PIPELINE START language=%s level=%s category=%s topic_id=%s resume=%s ===",
        language, level, category or "auto", topic_id or "auto", resume_artifact or "none",
    )

    # --- Load existing artifact for resume ---
    _resume: dict = {}
    if resume_artifact and resume_artifact.exists():
        _resume = json.loads(resume_artifact.read_text(encoding="utf-8"))
        level = normalize_level(_resume.get("level", level))
        category = _resume.get("category", category)
        topic_id = _resume.get("topic_id", topic_id)
        LOGGER.info("artifact.loaded topic=%s for resume", _resume.get("topic_id"))

    with _stage("db_init"):
        init_db()
        seed_topics_from_config()
        LOGGER.info("✓ Database initialized")

    # --- Topic selection ---
    if _resume.get("topic_id"):
        from pipeline.core.select_topic import TopicChoice
        t = _resume.get("topic", {})
        topic = TopicChoice(
            topic_id=_resume["topic_id"],
            track=t.get("track", ""),
            title_hint=t.get("title_hint", _resume.get("title_slug", "")),
            level=normalize_level(_resume["level"]),
            category=_resume["category"],
            scenario=t.get("scenario"),
            speaker1_role=t.get("speaker1_role"),
            speaker2_role=t.get("speaker2_role"),
            speaker1_gender=t.get("speaker1_gender"),
            speaker2_gender=t.get("speaker2_gender"),
        )
        level = normalize_level(topic.level)
        category = topic.category
        LOGGER.info("artifact.skip topic_selection — using saved topic: %s", topic.topic_id)
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

    # --- Script generation ---
    if _resume.get("script"):
        script = _resume["script"]
        LOGGER.info("artifact.skip script_generation")
    else:
        with _stage("script_generation"):
            script = stage_script(topic, language=language, level=level)
            LOGGER.info("✓ Script generated: %d dialogue lines", len(script.get("dialogue", [])))

    # --- Quiz generation (must precede metadata: the description embeds quiz answers) ---
    from pipeline.generate.generate_quiz import quiz_is_complete

    if quiz_is_complete(script.get("quiz")):
        LOGGER.info("artifact.skip quiz_generation (%d questions)", len(script["quiz"]))
    else:
        with _stage("quiz_generation"):
            quiz = stage_quiz(script, level=level, category=category, topic_id=topic.topic_id)
            if quiz:
                script["quiz"] = quiz
                LOGGER.info("✓ Quiz generated: %d questions", len(quiz))
            else:
                LOGGER.warning("quiz generation produced nothing — continuing without a quiz")

    # --- Metadata generation ---
    if _resume.get("metadata"):
        playlist_name = _resume.get("playlist", "")
        playlist_description = _resume.get("playlist_description", "")
        playlist_id = _resume.get("playlist_id", "")
        metadata = _resume["metadata"]
        LOGGER.info("artifact.skip metadata_generation")
    else:
        with _stage("metadata_generation"):
            playlist_name, playlist_description, playlist_id, metadata = stage_metadata(
                script,
                category=category,
                level=level,
                topic_id=topic.topic_id,
            )
            LOGGER.info("✓ Metadata: title=%s | playlist=%s", metadata.get("title", ""), playlist_name)

    # Prepare hierarchical output directory structure: output/{level}/{category}/{type}/episode_{topic_id}_{title_slug}/
    title_slug = create_title_slug(topic.title_hint)
    out_dir = ensure_output_dir(level, category)
    ensure_output_dir(level, category, "audio")
    ensure_output_dir(level, category, "visuals")
    ensure_output_dir(level, category, "videos")
    ensure_output_dir(level, category, "subtitles")
    out_path = out_dir / f"episode_{topic.topic_id}_{title_slug}.json"
    LOGGER.info("output.dirs.ready level=%s category=%s slug=%s base=%s", level, category, title_slug, out_dir)

    # --- Artifact: load from DB or build initial version ---
    _topic_id = topic.topic_id
    try:
        from pipeline.core import artifact_store as _as
        artifact: dict = _as.load(_topic_id)
        _normalize(artifact)
        LOGGER.info("artifact.loaded_from_db topic=%s", _topic_id)
    except KeyError:
        artifact = {
            "level": level,
            "category": category,
            "topic_id": _topic_id,
            "title_slug": title_slug,
            "topic": {
                "id": _topic_id,
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
        }
        LOGGER.info("artifact.new topic=%s", _topic_id)

    artifact["playlist"] = playlist_name
    artifact["playlist_description"] = playlist_description
    artifact["playlist_id"] = playlist_id

    # Select (or restore) the seed image once for the entire episode so every
    # stage — long-video image generation and shorts generation — uses identical
    # character reference images.
    if not artifact.get("seed_image_used"):
        seed_rel = _select_seed_image()
        if seed_rel:
            artifact["seed_image_used"] = seed_rel

    # Persist seed selection immediately so every downstream stage sees it.
    _save_artifact(_topic_id, artifact)

    # --- Voice generation ---
    _existing_audio = artifact.get("audio_file") or (artifact.get("voice") or {}).get("dialogue_audio", "")
    if _existing_audio and Path(_existing_audio).exists():
        voice_plan = artifact.get("voice", {})
        LOGGER.info("artifact.skip voice_generation — audio: %s", _existing_audio)
    else:
        with _stage("expression_tag_generation"):
            tts_dialogue = stage_expression_tags(
                script.get("dialogue", []), settings.TTS_PROVIDER
            )
            artifact["tts_dialogue"] = tts_dialogue
            _save_artifact(_topic_id, artifact)
        with _stage("voice_generation"):
            voice_plan = stage_voice(
                script, output_root=out_dir, level=level, category=category,
                topic_id=topic.topic_id, title_slug=title_slug,
                tts_dialogue=tts_dialogue,
            )
            LOGGER.info("\u2713 Voice generated: %s", voice_plan.get("dialogue_audio", ""))
        artifact.update({
            "audio_file": voice_plan.get("dialogue_audio", ""),
            "audio_file_raw": voice_plan.get("dialogue_audio_raw", voice_plan.get("dialogue_audio", "")),
            "voice": voice_plan,
        })
        _save_artifact(_topic_id, artifact)

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
    _existing_karaoke = artifact.get("karaoke_file") or (artifact.get("subtitles") or {}).get("karaoke_file", "")
    if _existing_karaoke and Path(_existing_karaoke).exists():
        subtitle_plan = artifact.get("subtitles", {})
        LOGGER.info("artifact.skip subtitle_generation")
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
        artifact.update({
            "karaoke_file": subtitle_plan.get("karaoke_file", ""),
            "subtitles": subtitle_plan,
        })
        _save_artifact(_topic_id, artifact)

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
    _existing_imgs = artifact.get("generated_image_files") or []
    if _existing_imgs and Path(_existing_imgs[0]).exists():
        generated_image_file = artifact.get("generated_image_file", _existing_imgs[0])
        generated_image_files = _existing_imgs
        LOGGER.info("artifact.skip image_generation — %d images", len(generated_image_files))
    else:
        with _stage("image_generation"):
            generated_image_file, generated_image_files, seed_returned = stage_image(
                topic_id=topic.topic_id,
                topic_title=script.get("topic_title", topic.title_hint),
                image_prompt=script.get("image_prompt", ""),
                image_prompts=script.get("image_prompts", []),
                level=level,
                category=category,
                output_root=out_dir,
                seed_image_used=artifact.get("seed_image_used", ""),
            )
            if not generated_image_file:
                raise RuntimeError("Image generation returned no file path.")
            if seed_returned and not artifact.get("seed_image_used"):
                artifact["seed_image_used"] = seed_returned
            LOGGER.info("\u2713 Image generated: %s (%d scene images)", generated_image_file, len(generated_image_files))
        artifact.update({
            "generated_image_file": generated_image_file or "",
            "generated_image_files": generated_image_files or [],
        })
        _save_artifact(_topic_id, artifact)

    with _stage("db_store_script"):
        canonical_script_id = store_canonical_script(
            topic_id=topic.topic_id,
            language=language,
            title=metadata["title"],
            script=script,
        )

    artifact["canonical_script_id"] = canonical_script_id
    _save_artifact(_topic_id, artifact)

    with _stage("script_export"):
        script_exports = _save_script_exports(
            out_dir=out_dir,
            canonical_script_id=canonical_script_id,
            topic_id=topic.topic_id,
            script=script,
            metadata=metadata,
        )

    artifact.setdefault("storage", {})["script_exports"] = script_exports
    _save_artifact(_topic_id, artifact)

    # --- Render video ---
    with _stage("render_video"):
        render_manifest_path = stage_render(artifact)
        mark_topic_generated(topic.topic_id)
        LOGGER.info("topic.generated id=%s", topic.topic_id)
        render_manifest = json.loads(render_manifest_path.read_text(encoding="utf-8"))
        artifact["upload_payload_preview"] = build_upload_payload(artifact)
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

    _save_artifact(_topic_id, artifact)

    if upload:
        video_path_for_upload = Path(stable_video_path) if stable_video_path else None
        if not _qa_passed:
            LOGGER.warning("\u26a0 Upload skipped — audio QA did not pass 100%%. Fix the audio and re-run with --upload.")
        elif video_path_for_upload and video_path_for_upload.exists():
            with _stage("upload_youtube"):
                try:
                    result = stage_upload(artifact, video_path_for_upload)
                    artifact["youtube"] = result
                    _save_artifact(_topic_id, artifact)
                    LOGGER.info("\u2713 Uploaded to YouTube: video_id=%s playlist=%s",
                                result.get("video_id"), result.get("playlist_name"))
                    _check_and_mark_done(artifact)
                    LOGGER.info("topic status checked after YouTube upload id=%s", topic.topic_id)
                except Exception as exc:
                    LOGGER.warning("\u26a0 YouTube upload failed (video saved locally): %s", exc)

            # --- Step 9: Generate vertical images + Short clips ---
            # Only dialogue episodes have multi-scene structure needed for shorts.
            full_video_id: str = artifact.get("youtube", {}).get("video_id", "")
            if full_video_id and category == "dialogue":
                with _stage("generate_shorts_images"):
                    try:
                        shorts_images = stage_generate_shorts_images(artifact)
                        artifact["shorts_images"] = shorts_images
                        _save_artifact(_topic_id, artifact)
                        LOGGER.info("\u2713 Shorts images generated: %d scenes", len(shorts_images))
                    except Exception as exc:
                        LOGGER.warning("\u26a0 Shorts image generation failed (non-fatal): %s", exc)

                with _stage("generate_shorts"):
                    try:
                        shorts_list: list[dict] = stage_generate_shorts(artifact)
                        artifact["shorts"] = shorts_list
                        _save_artifact(_topic_id, artifact)
                        LOGGER.info("\u2713 Shorts rendered: %d scene clips", len(shorts_list))
                    except Exception as exc:
                        LOGGER.warning("\u26a0 Shorts generation failed (non-fatal): %s", exc)

                # --- Step 10: Upload Shorts ---
                shorts_list = artifact.get("shorts", [])
                if shorts_list:
                    with _stage("upload_shorts"):
                        for i, short in enumerate(shorts_list):
                            try:
                                short_result = stage_upload_short(
                                    artifact, short, full_video_id
                                )
                                artifact["shorts"][i]["youtube"] = short_result
                                _save_artifact(_topic_id, artifact)
                                LOGGER.info(
                                    "\u2713 Short uploaded scene=%d short_video_id=%s",
                                    short["scene"],
                                    short_result.get("short_video_id"),
                                )
                            except Exception as exc:
                                LOGGER.warning(
                                    "\u26a0 Short upload failed scene=%d (non-fatal): %s",
                                    short.get("scene"), exc,
                                )

                    # --- Step 10b: Upload Shorts to Instagram ---
                    if settings.UPLOAD_INSTAGRAM:
                        with _stage("upload_shorts_instagram"):
                            from pipeline.core.db import (
                                claim_instagram_reel_upload,
                                complete_instagram_reel_upload,
                                release_instagram_reel_upload_claim,
                            )
                            for i, short in enumerate(shorts_list):
                                scene = short.get("scene", i)
                                claimed = claim_instagram_reel_upload(_topic_id, scene)
                                if not claimed:
                                    LOGGER.info("Instagram Reel skipped scene=%d — already uploaded or in progress", scene)
                                    continue
                                claim_id, claimed_artifact, claimed_short = claimed
                                try:
                                    ig_result = stage_upload_short_instagram(
                                        claimed_artifact, claimed_short
                                    )
                                    if not complete_instagram_reel_upload(_topic_id, scene, claim_id, ig_result):
                                        LOGGER.warning("Instagram Reel result ignored scene=%d — upload claim was superseded", scene)
                                        continue
                                    LOGGER.info(
                                        "\u2713 Instagram Reel uploaded scene=%d reel_id=%s",
                                        scene,
                                        ig_result.get("reel_id"),
                                    )
                                except Exception as exc:
                                    release_instagram_reel_upload_claim(_topic_id, scene, claim_id)
                                    LOGGER.warning(
                                        "\u26a0 Instagram upload failed scene=%d (non-fatal): %s",
                                        scene, exc,
                                    )

                    # --- Step 10c: Upload Shorts to TikTok ---
                    if settings.UPLOAD_TIKTOK:
                        with _stage("upload_shorts_tiktok"):
                            for i, short in enumerate(shorts_list):
                                try:
                                    tt_result = stage_upload_short_tiktok(
                                        artifact, short
                                    )
                                    artifact["shorts"][i]["tiktok"] = tt_result
                                    _save_artifact(_topic_id, artifact)
                                    LOGGER.info(
                                        "\u2713 TikTok Short uploaded scene=%d publish_id=%s",
                                        short["scene"],
                                        tt_result.get("publish_id"),
                                    )
                                except Exception as exc:
                                    LOGGER.warning(
                                        "\u26a0 TikTok upload failed scene=%d (non-fatal): %s",
                                        short.get("scene"), exc,
                                    )

                    # --- Step 10d: Upload Shorts to Facebook ---
                    if settings.UPLOAD_FACEBOOK:
                        with _stage("upload_shorts_facebook"):
                            from pipeline.stages import stage_upload_short_facebook
                            from pipeline.core.db import (
                                claim_facebook_reel_upload,
                                complete_facebook_reel_upload,
                                release_facebook_reel_upload_claim,
                            )
                            for i, short in enumerate(shorts_list):
                                scene = short.get("scene", i)
                                claimed = claim_facebook_reel_upload(_topic_id, scene)
                                if not claimed:
                                    LOGGER.info("Facebook Reel skipped scene=%d — already uploaded or in progress", scene)
                                    continue
                                claim_id, claimed_artifact, claimed_short = claimed
                                try:
                                    fb_result = stage_upload_short_facebook(
                                        claimed_artifact, claimed_short
                                    )
                                    if not complete_facebook_reel_upload(_topic_id, scene, claim_id, fb_result):
                                        LOGGER.warning("Facebook Reel result ignored scene=%d — upload claim was superseded", scene)
                                        continue
                                    LOGGER.info(
                                        "\u2713 Facebook Reel uploaded scene=%d post_id=%s",
                                        scene,
                                        fb_result.get("post_id"),
                                    )
                                except Exception as exc:
                                    release_facebook_reel_upload_claim(_topic_id, scene, claim_id)
                                    LOGGER.warning(
                                        "\u26a0 Facebook upload failed scene=%d (non-fatal): %s",
                                        scene, exc,
                                    )
        else:
            LOGGER.warning("\u26a0 Upload skipped — no rendered video found at: %s", stable_video_path)

    LOGGER.info("pipeline.done episode=%s elapsed_sec=%.2f topic=%s",
                canonical_script_id, time.perf_counter() - run_start, _topic_id)

    return _topic_id



# =============================================================================
# Artifact-mode: stage runners + interactive menu (used with --artifact)
# =============================================================================

# ---------------------------------------------------------------------------
# Artifact helpers
# ---------------------------------------------------------------------------

def load_artifact(topic_id_or_path: str) -> dict:
    """Load artifact from DB by topic_id (preferred) or legacy path."""
    from pipeline.core import artifact_store
    # Try topic_id first (direct DB lookup)
    try:
        artifact = artifact_store.load(topic_id_or_path)
    except KeyError:
        # Fall back: extract topic_id from path and retry
        import re as _re
        m = _re.search(r"episode_([^/\\]+?)(?:_[^/_\\]+)?\.json$", topic_id_or_path)
        if m:
            try:
                artifact = artifact_store.load(m.group(1))
            except KeyError:
                raise FileNotFoundError(f"Artifact not found in DB for: {topic_id_or_path}")
        else:
            raise FileNotFoundError(f"Artifact not found in DB for: {topic_id_or_path}")
    _normalize(artifact)
    if not artifact.get("title_slug"):
        topic_meta = artifact.get("topic", {})
        title_hint = (
            topic_meta.get("title_hint")
            or artifact.get("topic_title")
            or artifact.get("topic_id", "")
        )
        artifact["title_slug"] = create_title_slug(title_hint)
    return artifact


def _check_and_mark_ready_to_publish(artifact: dict) -> None:
    """If both main video and at least one short video exist, mark topic ready_to_publish."""
    topic_id = artifact.get("topic_id")
    if not topic_id:
        return
    has_video = bool(artifact.get("video_file") and Path(artifact["video_file"]).exists())
    shorts = artifact.get("shorts") or []
    has_shorts = any(s.get("video_file") and Path(s["video_file"]).exists() for s in shorts)
    if has_video and has_shorts:
        try:
            from pipeline.core.db import mark_topic_ready_to_publish
            mark_topic_ready_to_publish(topic_id)
            print(f"✅ Status → ready_to_publish (video + shorts ready)")
        except Exception as exc:
            print(f"⚠️  Could not update status: {exc}")


def _check_and_mark_done(artifact: dict) -> None:
    """Mark topic 'done' only when ALL enabled upload platforms are complete.

    Rules:
    - YouTube main video must be uploaded (youtube.video_id present).
    - For each platform that is *enabled in settings*, ALL shorts with a
      video_file must be uploaded to that platform.
    - If shorts exist but none of the enabled platforms have finished all
      scenes, the topic stays at ready_to_publish.
    - If no shorts exist, done = YouTube main uploaded.
    """
    topic_id = artifact.get("topic_id")
    if not topic_id:
        return

    # YouTube main video is required
    if not (artifact.get("youtube") or {}).get("video_id"):
        return

    shorts = [s for s in (artifact.get("shorts") or []) if s.get("video_file")]

    if shorts:
        def _ig_done(s: dict) -> bool:
            return bool(s.get("reel_id") or (s.get("instagram") or {}).get("reel_id"))

        def _tt_done(s: dict) -> bool:
            return bool((s.get("tiktok") or {}).get("publish_id"))

        def _yt_done(s: dict) -> bool:
            return bool((s.get("youtube") or {}).get("short_video_id"))

        def _fb_done(s: dict) -> bool:
            return bool((s.get("facebook") or {}).get("post_id"))

        # Check each *enabled* platform — ALL shorts must be done on that platform
        # before the topic can be marked done.
        if settings.UPLOAD_INSTAGRAM and not all(_ig_done(s) for s in shorts):
            return
        if settings.UPLOAD_TIKTOK and not all(_tt_done(s) for s in shorts):
            return
        if settings.UPLOAD_FACEBOOK and not all(_fb_done(s) for s in shorts):
            return

        # YouTube Shorts: required if any short has already been uploaded to YT
        any_yt = any(_yt_done(s) for s in shorts)
        if any_yt and not all(_yt_done(s) for s in shorts):
            return

    try:
        from pipeline.core.db import mark_topic_done
        mark_topic_done(topic_id)
        print("\u2705 Status \u2192 done (all platform uploads complete)")
    except Exception as exc:
        print(f"\u26a0\ufe0f  Could not update status to done: {exc}")


def _save_artifact(topic_id: str, artifact: dict) -> None:
    """Persist artifact to DB. Non-fatal if no publish_job exists yet."""
    from pipeline.core import artifact_store
    try:
        artifact_store.save(topic_id, artifact)
    except KeyError:
        LOGGER.debug("_save_artifact: no publish_job yet for %s — will persist after DB record created", topic_id)


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

def _cleanup_artifact(artifact_path: str) -> None:
    """Delete all local files and directories associated with an artifact."""
    import shutil
    path = Path(artifact_path)
    if not path.exists():
        print(f"⚠️  Artifact not found: {artifact_path}")
        return

    artifact = json.loads(path.read_text(encoding="utf-8"))
    topic_id = artifact.get("topic_id", "")
    title_slug = artifact.get("title_slug", "")
    level = artifact.get("level", "")
    category = artifact.get("category", "")

    deleted: list[str] = []
    skipped: list[str] = []

    def _remove(p: Path) -> None:
        if not p.exists():
            return
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()
        deleted.append(str(p))

    root = settings.ROOT

    # Artifact JSON and any render manifests next to it
    for f in path.parent.glob(f"episode_{topic_id}_{title_slug}*.json"):
        _remove(f)

    # Audio directory
    audio_dir = artifact.get("voice", {}).get("audio_dir") or \
                str(root / "output" / level / category / "audio" / f"episode_{topic_id}_{title_slug}")
    _remove(root / audio_dir if not Path(audio_dir).is_absolute() else Path(audio_dir))

    # Subtitles directory
    subs_dir = root / "output" / level / category / "subtitles" / f"episode_{topic_id}_{title_slug}"
    _remove(subs_dir)

    # Visuals directories (may be named differently due to topic_title)
    visuals_root = root / "output" / level / category / "visuals"
    if visuals_root.exists():
        for d in visuals_root.iterdir():
            if d.is_dir() and d.name.startswith(f"episode_{topic_id}"):
                _remove(d)

    # Videos directory
    videos_dir = root / "output" / level / category / "videos" / f"episode_{topic_id}_{title_slug}"
    _remove(videos_dir)

    # Shorts directory
    shorts_dir = root / "output" / level / category / "shorts" / f"episode_{topic_id}_{title_slug}"
    _remove(shorts_dir)

    # Script exports
    script_exports = (artifact.get("storage") or {}).get("script_exports", {})
    for key in ("script_json", "script_markdown"):
        p = script_exports.get(key, "")
        if p:
            _remove(root / p if not Path(p).is_absolute() else Path(p))

    # Archived video
    archived = (artifact.get("storage") or {}).get("archived_video_file", "")
    if archived:
        _remove(Path(archived))

    # DB: reset topic to pending so it can be re-run
    if topic_id:
        try:
            from pipeline.core.db import init_db
            init_db()
            import sqlite3
            db_path = root / "db" / "content.db"
            conn = sqlite3.connect(str(db_path))
            conn.execute("UPDATE topics SET status = 'pending' WHERE id = ?", [topic_id])
            conn.commit()
            conn.close()
            print(f"  ↩️  Topic '{topic_id}' reset to pending in DB")
        except Exception as e:
            print(f"  ⚠️  DB reset failed (non-fatal): {e}")

    print(f"✅ Cleaned up {len(deleted)} item(s):")
    for d in deleted:
        print(f"   🗑  {d}")
    if skipped:
        print(f"⚠️  {len(skipped)} item(s) not found (already missing).")


def run_script(topic_id: str) -> None:
    artifact = load_artifact(topic_id)
    print(f"🎯 Re-generating script for: {artifact['title_slug']}")
    topic = _topic_from_artifact(artifact)
    script = stage_script(topic, language="nl", level=artifact["level"])
    artifact["script"] = script
    artifact["script_manually_edited"] = False
    artifact.pop("script_edit_source", None)
    artifact["topic_title"] = script.get("topic_title", artifact.get("topic_title"))
    artifact["image_prompt"] = script.get("image_prompt", "")

    # Persist updated script to the DB so the webapp Script tab reflects it
    from pipeline.core.store_content import (
        save_episode_artifact,
        store_canonical_script,
        store_publish_job,
        update_publish_job_artifacts,
    )
    from pipeline.core.schedule_publish import next_publish_slot

    canonical_script_id = store_canonical_script(
        topic_id=artifact["topic_id"],
        language="nl",
        title=artifact.get("metadata", {}).get("title") or artifact.get("title_slug", ""),
        script=script,
    )
    artifact["canonical_script_id"] = canonical_script_id

    # Re-use existing publish_job if it exists for this canonical_script_id,
    # otherwise create a new stub so artifact_path is tracked.
    from pipeline.core.db import get_connection
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM publish_jobs WHERE canonical_script_id = ? ORDER BY id DESC LIMIT 1",
            [canonical_script_id],
        ).fetchone()
    if row:
        publish_job_id = row["id"]
    else:
        publish_job_id = store_publish_job(
            canonical_script_id=canonical_script_id,
            playlist_track=artifact.get("topic", {}).get("track", artifact.get("topic_id", "")),
            scheduled_at_iso=next_publish_slot().isoformat(),
            playlist_name=artifact.get("playlist"),
        )
        update_publish_job_artifacts(
            publish_job_id=publish_job_id,
            artifact_path="",
            video_file_path="",
        )

    _save_artifact(topic_id, artifact)
    save_episode_artifact(
        publish_job_id=publish_job_id,
        artifact_json=artifact,
        artifact_file_path="",
    )
    print("✅ Script regenerated")


def run_audio(topic_id: str) -> str:
    artifact = load_artifact(topic_id)
    print(f"🎯 Re-generating audio for: {artifact['title_slug']}")
    with _stage("expression_tag_generation"):
        tts_dialogue = stage_expression_tags(
            artifact.get("script", {}).get("dialogue", []), settings.TTS_PROVIDER
        )
        artifact["tts_dialogue"] = tts_dialogue
    voice_plan = stage_voice(
        script=artifact.get("script", {}),
        output_root=settings.ROOT / "output" / artifact["level"] / artifact["category"],
        level=artifact["level"],
        category=artifact["category"],
        topic_id=artifact["topic_id"],
        title_slug=artifact["title_slug"],
        tts_dialogue=tts_dialogue,
    )
    artifact["voice"] = voice_plan
    artifact["audio_file"] = voice_plan.get("dialogue_audio", "")
    artifact["audio_file_raw"] = voice_plan.get("dialogue_audio_raw", voice_plan.get("dialogue_audio", ""))
    _save_artifact(topic_id, artifact)
    print("✅ Audio regenerated")
    return artifact["audio_file"]


def run_expression_tags(topic_id: str) -> None:
    artifact = load_artifact(topic_id)
    script = artifact.get("script", {})
    with _stage("expression_tag_generation"):
        artifact["tts_dialogue"] = stage_expression_tags(
            script.get("dialogue", []), settings.TTS_PROVIDER
        )
    artifact.pop("audio_file", None)
    artifact.pop("audio_file_raw", None)
    artifact.pop("voice", None)
    _save_artifact(topic_id, artifact)
    print("✅ Expression tags generated; regenerate audio to apply them")


def run_subtitles(topic_id: str, audio_path: Optional[str] = None) -> None:
    artifact = load_artifact(topic_id)
    audio_path = audio_path or artifact.get("audio_file")
    if not audio_path or not Path(audio_path).exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    print(f"🎯 Re-generating subtitles for: {artifact['title_slug']}")

    # Wipe the subtitle directory so stale .orig.srt and old ASS/SRT files
    # don't interfere with timing on re-renders.
    import shutil
    from pipeline import settings as _settings
    subtitle_dir = (
        _settings.ROOT
        / "output"
        / artifact["level"]
        / artifact["category"]
        / "subtitles"
        / f"episode_{artifact['topic_id']}_{artifact['title_slug']}"
    )
    if subtitle_dir.exists():
        shutil.rmtree(subtitle_dir)
        print(f"🗑  Cleared subtitle dir: {subtitle_dir.name}")

    subtitle_plan = stage_subtitles(
        audio_path=audio_path,
        output_root=settings.ROOT / "output" / artifact["level"] / artifact["category"],
        level=artifact["level"],
        category=artifact["category"],
        topic_id=artifact["topic_id"],
        title_slug=artifact["title_slug"],
        script_dialogue=artifact.get("script", {}).get("dialogue"),
        dialogue_en=artifact.get("script", {}).get("dialogue_en"),
    )
    artifact["subtitles"] = subtitle_plan
    artifact["karaoke_file"] = subtitle_plan.get("karaoke_file", "")
    _save_artifact(topic_id, artifact)
    print("✅ Subtitles regenerated")


def run_image(topic_id: str) -> None:
    artifact = load_artifact(topic_id)
    print(f"🎯 Re-generating image for: {artifact['title_slug']}")
    script = artifact.get("script", {})
    primary, all_files, seed_used = stage_image(
        topic_id=artifact["topic_id"],
        topic_title=artifact.get("topic_title") or artifact.get("script", {}).get("topic_title", ""),
        image_prompt=script.get("image_prompt") or artifact.get("image_prompt", ""),
        image_prompts=script.get("image_prompts") or artifact.get("image_prompts", []),
        level=artifact["level"],
        category=artifact["category"],
        output_root=settings.ROOT / "output" / artifact["level"] / artifact["category"],
    )
    artifact["generated_image_file"] = primary
    artifact["generated_image_files"] = all_files
    if seed_used:
        artifact["seed_image_used"] = seed_used
    _save_artifact(topic_id, artifact)
    print(f"✅ Image regenerated ({len(all_files) or 1} image(s))")


def run_render(topic_id: str) -> str:
    artifact = load_artifact(topic_id)
    print(f"🎯 Re-rendering video for: {artifact['title_slug']}")

    # Staleness check: block render if audio is newer than the ASS subtitle file.
    # Mismatched timestamps cause subtitles to race ahead of the audio.
    audio_file = artifact.get("audio_file") or artifact.get("audio_file_raw", "")
    ass_file = artifact.get("karaoke_file") or (artifact.get("srt_files") or {}).get("ass_karaoke", "")
    if audio_file and ass_file:
        audio_path = Path(audio_file) if Path(audio_file).is_absolute() else settings.ROOT / audio_file
        ass_path = Path(ass_file) if Path(ass_file).is_absolute() else settings.ROOT / ass_file
        if audio_path.exists() and ass_path.exists():
            audio_mtime = audio_path.stat().st_mtime
            ass_mtime = ass_path.stat().st_mtime
            if audio_mtime > ass_mtime:
                raise RuntimeError(
                    "Audio file is newer than the subtitle file — subtitles will be out of sync.\n"
                    "   Run stage 4 (Subtitles) before stage 7 (Render) to fix this."
                )

    manifest_path = stage_render(artifact)
    # Load and save manifest to artifact
    render_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifact["render"] = render_manifest
    video_file = render_manifest.get("planned_video_file", "")
    if video_file:
        artifact["video_file"] = video_file
    _save_artifact(topic_id, artifact)
    print(f"✅ Video re-rendered: {video_file}")
    _check_and_mark_ready_to_publish(artifact)
    return str(video_file)


def run_upload(topic_id: str, video_path: Optional[str] = None) -> None:
    artifact = load_artifact(topic_id)
    if not video_path:
        video_path = artifact.get("render", {}).get("planned_video_file") or artifact.get("video_file")
    if not video_path or not Path(video_path).exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")
    print(f"🎯 Uploading to YouTube: {artifact.get('title_slug', artifact.get('topic_id', 'Unknown'))}")
    result = stage_upload(artifact, video_path)
    artifact["youtube"] = result
    _save_artifact(topic_id, artifact)
    # Write youtube_video_id to publish_jobs; status -> ready_to_publish until all platforms done
    _topic_id = artifact.get("topic_id")
    _video_id = result.get("video_id")
    if _topic_id:
        from pipeline.core.db import mark_topic_ready_to_publish, get_connection
        mark_topic_ready_to_publish(_topic_id)
        if _video_id:
            canonical_script_id = artifact.get("canonical_script_id")
            if canonical_script_id:
                with get_connection() as conn:
                    conn.execute(
                        "UPDATE publish_jobs SET youtube_video_id = ? "
                        "WHERE id = (SELECT id FROM publish_jobs WHERE canonical_script_id = ? ORDER BY id DESC LIMIT 1)",
                        [_video_id, canonical_script_id],
                    )
    print(f"✅ Uploaded: video_id={_video_id}")
    _check_and_mark_done(artifact)


def run_captions(topic_id: str, video_id: Optional[str] = None) -> None:
    artifact = load_artifact(topic_id)
    video_id = video_id or artifact.get("youtube", {}).get("video_id", "")
    if not video_id:
        raise ValueError("No YouTube video_id found. Pass --video-id or upload first.")
    srt_path = (artifact.get("subtitles") or {}).get("srt_en", "")
    if not srt_path or not Path(srt_path).exists():
        raise FileNotFoundError(f"English SRT not found: {srt_path}")
    print(f"🎯 Uploading captions for video_id={video_id}")
    result = stage_upload_captions(None, video_id, srt_path)
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
        _save_artifact(topic_id, artifact)
        print(f"✅ Caption uploaded: id={caption_id}")
    else:
        print("⚠️  Caption upload returned no result (possibly already exists).")


def run_qa(topic_id: str) -> None:
    from pipeline.generate.qa_audio import log_qa_report
    artifact = load_artifact(topic_id)
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


def run_qa_subtitles(topic_id: str) -> None:
    from pipeline.generate.qa_subtitles import log_subtitle_qa_report
    artifact = load_artifact(topic_id)
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


def run_quiz(topic_id: str) -> None:
    """Regenerate the learner-facing quiz and persist it into the stored script."""
    from pipeline.core.store_content import store_canonical_script

    artifact = load_artifact(topic_id)
    script = artifact.get("script")
    if not script:
        print("⚠️  No script in artifact — run the Script stage first.")
        return

    print(f"🎯 Generating quiz for: {artifact['title_slug']}")
    quiz = stage_quiz(
        script,
        level=artifact["level"],
        category=artifact["category"],
        topic_id=artifact["topic_id"],
    )
    if not quiz:
        print("✗ Quiz generation produced no valid questions — artifact left unchanged.")
        return

    script["quiz"] = quiz
    artifact["script"] = script
    _save_artifact(topic_id, artifact)

    # Keep canonical_scripts in sync so the DB copy of the script carries the quiz too.
    store_canonical_script(
        topic_id=artifact["topic_id"],
        language=script.get("language", "nl"),
        title=artifact.get("metadata", {}).get("title") or artifact.get("title_slug", ""),
        script=script,
    )
    print(f"✅ Quiz generated: {len(quiz)} questions")


def run_export_image_prompts(topic_id: str) -> None:
    """Export formatted image prompts for all scenes to a text file.
    Use these prompts in the Gemini web app (aistudio.google.com) to generate
    images manually by uploading the seed image + pasting the prompt text.
    """
    artifact = load_artifact(topic_id)
    script = artifact.get("script", {})
    image_prompts = script.get("image_prompts", [])
    seed_image = artifact.get("seed_image_used", "")
    title_slug = artifact.get("title_slug", artifact.get("topic_id", "episode"))

    if not image_prompts:
        print("⚠️  No image_prompts found in artifact — run Script stage first.")
        return

    def _output_req(prompt: str, ratio: str = "16:9") -> str:
        if "SPLIT-SCREEN" in prompt:
            return (
                f"OUTPUT REQUIREMENT: SPLIT-SCREEN — two side-by-side panels in ONE {ratio} image. "
                f"Each panel shows a different character in their own environment. "
                f"Do NOT merge them into a single shared scene.\n"
                "ABSOLUTELY NO TEXT, NO WORDS, NO LABELS, NO SIGNS, NO CAPTIONS, "
                "NO WRITING OF ANY KIND anywhere in the generated image. "
                "Any props that would normally have writing must appear blank or decorative only."
            )
        return (
            f"OUTPUT REQUIREMENT: ONE single continuous {ratio} image. "
            "Split into panels only if necessary, NEVER tile, NEVER repeat, NEVER show the scene twice. One frame only.\n"
            "ABSOLUTELY NO TEXT, NO WORDS, NO LABELS, NO SIGNS, NO CAPTIONS, "
            "NO WRITING OF ANY KIND anywhere in the generated image. "
            "Any props that would normally have writing must appear blank or decorative only."
        )

    out_path = settings.ROOT / "output" / artifact["level"] / artifact["category"] / f"image_prompts_{title_slug}.txt"
    lines: list[str] = []
    lines.append(f"IMAGE PROMPTS — {title_slug}")
    lines.append("=" * 70)
    lines.append("")
    if seed_image:
        lines.append(f"📎 Upload this reference image in the Gemini web app:")
        lines.append(f"   {settings.ROOT / seed_image}")
    lines.append("")
    lines.append("Instructions: For each scene, upload the seed image above + paste the prompt below.")
    lines.append("Web app: https://aistudio.google.com  (use gemini-3.1-flash-image or similar)")
    lines.append("")

    for p in image_prompts:
        scene_n = p.get("scene", "?")
        description = p.get("description", "")
        trigger = p.get("trigger_sentence", "")
        scene_prompt = p.get("prompt", "")

        # Extract the compact scene-specific parts from the full prompt
        # (environment, scene focus, visual emphasis) if present
        env_line = ""
        focus_line = ""
        emphasis_line = ""
        for segment in scene_prompt.split(". "):
            s = segment.strip()
            if s.startswith("Environment:"):
                env_line = s
            elif s.startswith("Scene focus:"):
                focus_line = s
            elif s.startswith("Visual emphasis:"):
                emphasis_line = s

        lines.append("-" * 70)
        lines.append(f"SCENE {scene_n}: {description}")
        if trigger:
            lines.append(f"Trigger: \"{trigger}\"")
        lines.append("")
        lines.append("--- PROMPT (copy everything below this line) ---")
        lines.append("")
        # Build a focused prompt: scenario context first, then style/character constraints
        scenario_context = (
            f"SCENE SITUATION: {description}\n"
            f"The dialogue trigger is: \"{trigger}\"\n"
        )
        if env_line:
            scenario_context += f"{env_line}.\n"
        if focus_line:
            scenario_context += f"{focus_line}.\n"
        if emphasis_line:
            scenario_context += f"{emphasis_line}.\n"

        prompt_text = (
            f"{scenario_context}\n"
            f"Reference image 1: the two main characters — keep faces, hairstyles, "
            f"skin tones, and clothing IDENTICAL. "
            f"IGNORE the characters' poses, gestures, and any objects they are holding — "
            f"do NOT reproduce them. IGNORE any text visible in the reference image.\n"
            f"{_output_req(scene_prompt)}\n"
            f"Art style: {scene_prompt.split('Environment:')[0].strip() if 'Environment:' in scene_prompt else ''}"
        )
        lines.append(prompt_text)
        lines.append("")

    # ── SHORTS (9:16 PORTRAIT) PROMPTS ──────────────────────────────────────
    generated_16_9 = artifact.get("generated_image_files", [])
    scene_to_16_9: dict[int, str] = {}
    import re as _re
    for img_rel in generated_16_9:
        m = _re.search(r"scene(\d+)", Path(img_rel).name, _re.IGNORECASE)
        if m:
            scene_to_16_9[int(m.group(1))] = str(settings.ROOT / img_rel) if not Path(img_rel).is_absolute() else img_rel

    lines.append("")
    lines.append("=" * 70)
    lines.append("SHORTS — 9:16 PORTRAIT PROMPTS")
    lines.append("=" * 70)
    lines.append("")
    lines.append("Instructions: For each scene, upload BOTH reference images + paste the prompt.")
    lines.append("  Reference image 1: seed image (character reference) — path listed above")
    lines.append("  Reference image 2: the corresponding 16:9 scene image (style reference)")
    lines.append("")

    portrait_placement = (
        "FULL-BLEED 9:16 PORTRAIT — every pixel covered by scene background. "
        "NO white space, NO blank areas, NO borders anywhere. "
        "Place both characters naturally within the frame with full bodies visible, "
        "facing each other. "
        "The bottom portion must show the actual floor/ground surface — "
        "NOT a flat colour or gradient."
    )
    common_instructions_9_16 = _output_req("", "9:16 portrait")

    for p in image_prompts:
        scene_n = p.get("scene", "?")
        description = p.get("description", "")
        trigger = p.get("trigger_sentence", "")
        scene_prompt = p.get("prompt", "")

        env_line = focus_line = emphasis_line = ""
        for segment in scene_prompt.split(". "):
            s = segment.strip()
            if s.startswith("Environment:"):
                env_line = s
            elif s.startswith("Scene focus:"):
                focus_line = s
            elif s.startswith("Visual emphasis:"):
                emphasis_line = s

        ref2_path = scene_to_16_9.get(scene_n, "")

        lines.append("-" * 70)
        lines.append(f"SCENE {scene_n} (9:16): {description}")
        if trigger:
            lines.append(f"Trigger: \"{trigger}\"")
        if ref2_path:
            lines.append(f"📎 Reference image 2 (16:9 scene): {ref2_path}")
        lines.append("")
        lines.append("--- PROMPT ---")
        lines.append("")

        scenario_context_9_16 = f"SCENE SITUATION: {description}\n"
        if env_line:
            scenario_context_9_16 += f"{env_line}.\n"
        if focus_line:
            scenario_context_9_16 += f"{focus_line}.\n"
        if emphasis_line:
            scenario_context_9_16 += f"{emphasis_line}.\n"

        art_style_base = scene_prompt.split("Environment:")[0].strip() if "Environment:" in scene_prompt else ""
        # Replace aspect ratio references
        art_style_9_16 = art_style_base.replace("16:9", "9:16").replace("16:9 aspect ratio", "9:16 aspect ratio, portrait orientation")

        prompt_9_16 = (
            f"{scenario_context_9_16}\n"
            f"Reference image 1: the two main characters — keep faces, hairstyles, "
            f"skin tones, and clothing IDENTICAL. "
            f"IGNORE poses, gestures, and held objects from reference images — do NOT reproduce them. "
            f"IGNORE any text visible in reference images.\n"
            f"Reference image 2 is a style reference — match its lighting, colour palette, and art style. "
            f"DO NOT copy, tile, or repeat it. Generate a completely new 9:16 image.\n"
            f"{common_instructions_9_16}\n"
            f"{portrait_placement}\n"
            f"Art style: {art_style_9_16}"
        )
        lines.append(prompt_9_16)
        lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"✅ Prompts exported to: {out_path}")
    print(f"   {len(image_prompts)} × 16:9 scenes + {len(image_prompts)} × 9:16 shorts")


def run_generate_shorts_images(topic_id: str) -> None:
    artifact = load_artifact(topic_id)
    print(f"\U0001f3af Generating vertical (9:16) Short images for: {artifact['title_slug']}")
    results = stage_generate_shorts_images(artifact)
    artifact["shorts_images"] = results
    _save_artifact(topic_id, artifact)
    print(f"\u2705 Generated {len(results)} vertical scene image(s)")


def run_generate_shorts(topic_id: str) -> None:
    artifact = load_artifact(topic_id)
    print(f"\U0001f3af Generating Shorts for: {artifact['title_slug']}")
    shorts_list = stage_generate_shorts(artifact)
    artifact["shorts"] = shorts_list
    _save_artifact(topic_id, artifact)
    print(f"\u2705 Generated {len(shorts_list)} Short clip(s)")
    _check_and_mark_ready_to_publish(artifact)


def run_upload_shorts(topic_id: str) -> None:
    artifact = load_artifact(topic_id)
    full_video_id: str = artifact.get("youtube", {}).get("video_id", "")
    if not full_video_id:
        raise ValueError("No YouTube video_id found in artifact. Upload the full video first.")
    shorts_list: list[dict] = artifact.get("shorts", [])
    if not shorts_list:
        raise ValueError("No shorts found in artifact. Run 'Generate Shorts' first.")
    print(f"\U0001f3af Uploading {len(shorts_list)} Short(s) for: {artifact['title_slug']}")
    for i, short in enumerate(shorts_list):
        try:
            short_result = stage_upload_short(artifact, short, full_video_id)
            artifact["shorts"][i]["youtube"] = short_result
            _save_artifact(topic_id, artifact)
            print(f"  \u2705 Scene {short['scene']} uploaded: short_video_id={short_result.get('short_video_id')}")
        except Exception as exc:
            print(f"  \u26a0\ufe0f  Scene {short['scene']} upload failed: {exc}")
    print("\u2705 Shorts upload complete")
    _check_and_mark_done(artifact)


def run_upload_shorts_instagram(topic_id: str) -> None:
    from pipeline.core.db import (
        claim_instagram_reel_upload,
        complete_instagram_reel_upload,
        release_instagram_reel_upload_claim,
    )
    artifact = load_artifact(topic_id)
    shorts_list: list[dict] = artifact.get("shorts", [])
    if not shorts_list:
        raise ValueError("No shorts found in artifact. Run 'Generate Shorts' first.")
    pending = [
        (i, s) for i, s in enumerate(shorts_list)
        if not s.get("instagram", {}).get("reel_id")
    ]
    if not pending:
        print("\u2705 All scenes already uploaded to Instagram — nothing to do.")
        return
    print(f"\U0001f4f8 Uploading {len(pending)} Reel(s) to Instagram (skipping {len(shorts_list) - len(pending)} already done) for: {artifact['title_slug']}")
    for i, short in pending:
        scene = short.get("scene", i)
        claimed = claim_instagram_reel_upload(topic_id, scene)
        if not claimed:
            print(f"  \u2139\ufe0f  Scene {scene} skipped: already uploaded or in progress")
            continue
        claim_id, claimed_artifact, claimed_short = claimed
        try:
            ig_result = stage_upload_short_instagram(claimed_artifact, claimed_short)
            if complete_instagram_reel_upload(topic_id, scene, claim_id, ig_result):
                print(f"  \u2705 Scene {scene} uploaded: reel_id={ig_result.get('reel_id')}")
            else:
                print(f"  \u2139\ufe0f  Scene {scene} result ignored: upload claim was superseded")
        except Exception as exc:
            release_instagram_reel_upload_claim(topic_id, scene, claim_id)
            print(f"  \u26a0\ufe0f  Scene {scene} Instagram upload failed: {exc}")
    print("\u2705 Instagram Reels upload complete")
    _check_and_mark_done(artifact)


def run_upload_shorts_tiktok(topic_id: str) -> None:
    artifact = load_artifact(topic_id)
    shorts_list: list[dict] = artifact.get("shorts", [])
    if not shorts_list:
        raise ValueError("No shorts found in artifact. Run 'Generate Shorts' first.")
    pending = [
        (i, s) for i, s in enumerate(shorts_list)
        if not s.get("tiktok", {}).get("publish_id")
    ]
    if not pending:
        print("\u2705 All scenes already uploaded to TikTok — nothing to do.")
        return
    print(f"\U0001f3b5 Uploading {len(pending)} Short(s) to TikTok (skipping {len(shorts_list) - len(pending)} already done) for: {artifact['title_slug']}")
    for i, short in pending:
        try:
            tt_result = stage_upload_short_tiktok(artifact, short)
            artifact["shorts"][i]["tiktok"] = tt_result
            _save_artifact(topic_id, artifact)
            print(f"  \u2705 Scene {short['scene']} uploaded: publish_id={tt_result.get('publish_id')}")
        except Exception as exc:
            print(f"  \u26a0\ufe0f  Scene {short['scene']} TikTok upload failed: {exc}")
    print("\u2705 TikTok Shorts upload complete")
    _check_and_mark_done(artifact)


def run_upload_shorts_facebook(topic_id: str) -> None:
    from pipeline.stages import stage_upload_short_facebook
    from pipeline.core.db import (
        claim_facebook_reel_upload,
        complete_facebook_reel_upload,
        release_facebook_reel_upload_claim,
    )
    artifact = load_artifact(topic_id)
    shorts_list: list[dict] = artifact.get("shorts", [])
    if not shorts_list:
        raise ValueError("No shorts found in artifact. Run 'Generate Shorts' first.")
    pending = [
        (i, s) for i, s in enumerate(shorts_list)
        if not s.get("facebook", {}).get("post_id")
    ]
    if not pending:
        print("\u2705 All scenes already uploaded to Facebook \u2014 nothing to do.")
        return
    print(f"\U0001f4d8 Uploading {len(pending)} Reel(s) to Facebook for: {artifact['title_slug']}")
    for i, short in pending:
        scene = short.get("scene", i)
        claimed = claim_facebook_reel_upload(topic_id, scene)
        if not claimed:
            print(f"  \u2139\ufe0f  Scene {scene} skipped: already uploaded or in progress")
            continue
        claim_id, claimed_artifact, claimed_short = claimed
        try:
            fb_result = stage_upload_short_facebook(claimed_artifact, claimed_short)
            if complete_facebook_reel_upload(topic_id, scene, claim_id, fb_result):
                print(f"  \u2705 Scene {scene} uploaded: post_id={fb_result.get('post_id')}")
            else:
                print(f"  \u2139\ufe0f  Scene {scene} result ignored: upload claim was superseded")
        except Exception as exc:
            release_facebook_reel_upload_claim(topic_id, scene, claim_id)
            print(f"  \u26a0\ufe0f  Scene {scene} Facebook upload failed: {exc}")
    print("\u2705 Facebook Reels upload complete")
    _check_and_mark_done(artifact)


# ---------------------------------------------------------------------------
# Interactive stage menu (used with --artifact)
# ---------------------------------------------------------------------------

_STAGES = [
    ("Script",           run_script),
    ("Generate Expression Tags", run_expression_tags),
    ("Image",            run_image),
    ("Audio",            run_audio),
    ("Subtitles",        run_subtitles),
    ("Audio QA",         run_qa),
    ("Subtitle QA",      run_qa_subtitles),
    ("Render video",     run_render),
    ("Upload YouTube",       run_upload),
    ("Generate Short Images", run_generate_shorts_images),
    ("Generate Shorts",      run_generate_shorts),
    ("Upload Shorts",        run_upload_shorts),
    ("Upload Shorts Instagram", run_upload_shorts_instagram),
    ("Upload Shorts TikTok", run_upload_shorts_tiktok),
    ("Upload Shorts Facebook", run_upload_shorts_facebook),
    ("Upload captions",      run_captions),
    ("Export image prompts", run_export_image_prompts),
    ("Generate Quiz",        run_quiz),
]


def _parse_selection(raw: str, max_n: int) -> list[int]:
    """Parse a stage selection string like '1 3 7' or '2,4' into 0-based indices.

    Always returns indices sorted in ascending order so stages run in the
    canonical pipeline sequence regardless of input order.
    """
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
    return sorted(set(indices))  # deduplicate and sort


def interactive_menu(topic_id: str) -> None:
    artifact = load_artifact(topic_id)
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
            fn(topic_id)
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
        choices=["course_intro", "common_words", "grammar", "vocabulary", "dialogue"],
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
    parser.add_argument("--cleanup", metavar="ARTIFACT", help="Delete all local files and directories associated with an artifact (audio, subtitles, images, video, shorts, scripts). Does not affect YouTube uploads.")
    parser.add_argument("--stages", metavar="STAGES", help="Comma-separated list of stage numbers to run non-interactively when used with --artifact (e.g. --stages 3,4,7)")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    # ── CLEANUP MODE: delete all local files for an artifact ─────────────────
    if args.cleanup:
        _cleanup_artifact(args.cleanup)
        return

    # ── ARTIFACT MODE (legacy): resolve topic_id from path, run stages ───────
    if args.artifact:
        try:
            # Resolve topic_id from the artifact path via DB
            topic_id = load_artifact(args.artifact).get("topic_id") if args.artifact else None
            if not topic_id:
                print(f"✗ Could not resolve topic_id from: {args.artifact}", file=sys.stderr)
                sys.exit(1)
            if args.stages:
                selected = _parse_selection(args.stages, len(_STAGES))
                if not selected:
                    print("✗ No valid stages in --stages", file=sys.stderr)
                    sys.exit(1)
                for idx in selected:
                    name, fn = _STAGES[idx]
                    print(f"\n▶  Running: {name}")
                    fn(topic_id)
            else:
                interactive_menu(topic_id)
        except Exception as e:
            LOGGER.exception("artifact_mode.failed")
            print(f"\u274c Error: {e}", file=sys.stderr)
            sys.exit(1)
        return

    # ── TOPIC-ID + STAGES MODE: DB-primary stage re-run ──────────────────────
    if args.topic_id and args.stages:
        try:
            from pipeline.core.db import init_db, seed_topics_from_config
            init_db()
            seed_topics_from_config()
            selected = _parse_selection(args.stages, len(_STAGES))
            if not selected:
                print("✗ No valid stages in --stages", file=sys.stderr)
                sys.exit(1)
            for idx in selected:
                name, fn = _STAGES[idx]
                print(f"\n▶  Running: {name}")
                fn(args.topic_id)
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

            # Generate script and metadata
            script = stage_script(topic, language="nl", level=level)
            playlist_name, playlist_description, playlist_id, metadata = stage_metadata(
                script,
                category=category,
                level=level,
                topic_id=args.topic_id,
            )

            # Persist script to DB
            canonical_script_id = store_canonical_script(
                topic_id=args.topic_id,
                language="nl",
                title=metadata["title"],
                script=script,
            )

            # Create or update publish_job and artifact in DB
            from pipeline.core.schedule_publish import next_publish_slot
            publish_job_id = store_publish_job(
                canonical_script_id=canonical_script_id,
                playlist_track=topic.track,
                scheduled_at_iso=next_publish_slot().isoformat(),
                playlist_name=playlist_name,
            )

            # Try to load existing artifact from DB; build fresh if not found
            try:
                from pipeline.core import artifact_store as _as
                artifact = _as.load(args.topic_id)
                _normalize(artifact)
            except KeyError:
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
                }

            artifact.update({
                "playlist": playlist_name,
                "playlist_description": playlist_description,
                "playlist_id": playlist_id,
                "script": script,
                "metadata": metadata,
                "canonical_script_id": canonical_script_id,
                "title_slug": title_slug,
            })

            save_episode_artifact(
                publish_job_id=publish_job_id,
                artifact_json=artifact,
                artifact_file_path="",
            )
            _save_artifact(args.topic_id, artifact)
            print(f"\u2713 Script-only complete. topic_id={args.topic_id}")
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
    # Priority: --topic-id (always single) > --count > --single > default behavior
    if getattr(args, "topic_id", None):
        # A specific topic was requested — run exactly once then exit.
        out_path = run(language=args.language, level=args.level, category=args.category, upload=not args.no_upload, topic_id=args.topic_id)
        print(f"\n✓ Pipeline completed. Artifact: {out_path}")
        return

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
