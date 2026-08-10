#!/usr/bin/env python3
"""Orchestrator for re-running individual pipeline stages on an existing episode,
or running stages from scratch without a pre-existing artifact.

All computation is delegated to pipeline.stages — this file handles only:
  - artifact I/O (load, save)
  - extracting stage inputs from artifact fields
  - routing CLI args to the right stage(s)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

# Ensure we're in the project root directory
script_dir = Path(__file__).parent
os.chdir(script_dir)
sys.path.insert(0, str(script_dir))

from pipeline.stages import (
    normalize_level,
    stage_image,
    stage_qa_audio,
    stage_qa_subtitles,
    stage_render,
    stage_script,
    stage_subtitles,
    stage_upload,
    stage_upload_captions,
    stage_voice,
)

LOGGER = logging.getLogger(__name__)

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
    video_path = stage_render(artifact_path)
    print("✅ Video re-rendered")
    return str(video_path)


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
    missing = [i for i in report.issues if i.issue_type == "MISSING"]
    if missing:
        print(f"⚠️  QA found {len(missing)} missing sentence(s)")
    else:
        print(f"✅ QA passed — {report.found_count}/{report.total_script_sentences} sentences found")


def run_qa_subtitles(artifact_path: str) -> None:
    from pipeline.generate.qa_subtitles import log_subtitle_qa_report
    artifact = load_artifact(artifact_path)
    subs = artifact.get("subtitles") or {}
    ass_file = artifact.get("karaoke_file") or subs.get("karaoke_file")
    srt_file = subs.get("srt_en") or subs.get("srt_files", {}).get("en")
    expected = len(artifact.get("script", {}).get("dialogue") or []) or None
    print(f"🎯 Running subtitle QA for: {artifact['title_slug']}")
    ass_report, srt_report = stage_qa_subtitles(ass_file, srt_file, expected)
    ran_any = False
    any_hard = False
    if ass_report:
        log_subtitle_qa_report(ass_report)
        ran_any = True
        if not ass_report.passed:
            any_hard = True
    else:
        print("⚠️  No ASS subtitle file found (skipping ASS QA)")
    if srt_report:
        log_subtitle_qa_report(srt_report)
        ran_any = True
        if not srt_report.passed:
            any_hard = True
    else:
        print("ℹ️  No SRT subtitle file found (skipping SRT QA)")
    if not ran_any:
        print("⚠️  No subtitle files found — run --subtitles first")
        return
    print("⚠️  Subtitle QA found hard issues" if any_hard else "✅ Subtitle QA passed")


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# From-scratch helpers
# ---------------------------------------------------------------------------

_SCRATCH_DIR = Path("output/scratch")


def _scratch_path(topic_id: str) -> Path:
    _SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    return _SCRATCH_DIR / f"scratch_{topic_id}.json"


def run_scratch_script(level: str, category: Optional[str], topic_id: Optional[str], language: str = "nl") -> str:
    from pipeline.core.db import init_db, seed_topics_from_config, get_topic_by_id
    from pipeline.core.select_topic import TopicChoice, choose_next_topic
    from pipeline.core.store_content import create_title_slug
    init_db()
    seed_topics_from_config()

    if topic_id:
        # Fetch the pinned topic directly — ignore auto-selection
        row = get_topic_by_id(topic_id)
        if row is None:
            raise ValueError(f"Topic not found in database: {topic_id!r}")
        topic = TopicChoice(
            topic_id=row["id"],
            track=row["track"],
            title_hint=row["title_hint"],
            level=normalize_level(row["level"]),
            category=row["category"],
        )
    else:
        topic = choose_next_topic(level=level, category=category)

    # Always start clean — delete any existing scratch artifact for this topic
    existing = _scratch_path(topic.topic_id)
    if existing.exists():
        existing.unlink()
        print(f"🗑  Deleted existing scratch artifact: {existing}")

    print(f"🎯 Selected topic: {topic.title_hint} ({topic.topic_id})")
    script = stage_script(topic, language=language, level=level)
    title_slug = create_title_slug(script.get("topic_title", topic.title_hint))
    artifact: dict = {
        "level": level, "category": topic.category, "topic_id": topic.topic_id,
        "title_slug": title_slug, "topic_title": script.get("topic_title", topic.title_hint),
        "image_prompt": script.get("image_prompt", ""),
        "topic": {"id": topic.topic_id, "level": level, "category": topic.category,
                  "track": topic.track, "title_slug": title_slug, "title_hint": topic.title_hint,
                  "scenario": getattr(topic, "scenario", None)},
        "script": script,
    }
    out_path = _scratch_path(topic.topic_id)
    _save_artifact(str(out_path), artifact)
    print(f"✅ Script generated → {out_path}")
    return str(out_path)


def _find_scratch(level: str, category: Optional[str], topic_id: Optional[str]) -> str:
    if topic_id:
        p = _scratch_path(topic_id)
        if not p.exists():
            raise FileNotFoundError(f"No scratch artifact for topic_id={topic_id!r}. Run interactively and pick Script first.")
        return str(p)
    candidates = sorted(_SCRATCH_DIR.glob("scratch_*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    for c in candidates:
        try:
            a = json.loads(c.read_text(encoding="utf-8"))
            if a.get("level") == level and (not category or a.get("category") == category):
                return str(c)
        except Exception:
            continue
    raise FileNotFoundError(f"No scratch artifact for level={level!r} category={category!r}. Select Script first.")


# ---------------------------------------------------------------------------
# Interactive multi-stage menu
# ---------------------------------------------------------------------------

_STAGES = [
    ("Script",          run_script),
    ("Image",           run_image),
    ("Audio",           run_audio),
    ("Subtitles",       lambda ap: run_subtitles(ap)),
    ("Audio QA",        run_qa),
    ("Subtitle QA",     run_qa_subtitles),
    ("Render video",    run_render),
    ("Upload YouTube",  run_upload),
    ("Upload captions", run_captions),
]


def _parse_selection(raw: str, max_n: int) -> list[int]:
    """Parse '1 3 5', '1,3,5', 'all', or '0' into a sorted list of 1-based indices."""
    raw = raw.strip().lower()
    if raw in ("all", "a"):
        return list(range(1, max_n + 1))
    indices = []
    for token in raw.replace(",", " ").split():
        try:
            n = int(token)
            if 1 <= n <= max_n:
                indices.append(n)
        except ValueError:
            pass
    return sorted(set(indices))


def interactive_menu(artifact_path: str) -> None:
    artifact = load_artifact(artifact_path)
    print(f"\n📺  {artifact['title_slug']}")
    print(f"    Level: {artifact['level']} | Category: {artifact['category']}\n")

    for i, (name, _) in enumerate(_STAGES, 1):
        print(f"  {i:2}) {name}")
    print()
    print("Select stages to run — space or comma separated (e.g. '3 4 7')")
    print("Type 'all' to run every stage, or '0' to exit.")

    raw = input("\n> ").strip()
    if raw == "0":
        return

    chosen = _parse_selection(raw, len(_STAGES))
    if not chosen:
        print("No valid selection.")
        return

    print()
    for idx in chosen:
        name, fn = _STAGES[idx - 1]
        print(f"── {name} ──────────────────────────")
        fn(artifact_path)
    print("\n✅ Done.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Interactive stage runner for existing episodes or from-scratch testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive menu for an existing episode
  python rerun_stage.py output/A1A2/dialogue/episode_xxx.json

  # From scratch — auto-select next pending topic
  python rerun_stage.py --level A1A2 --category dialogue

  # From scratch — pin a specific topic
  python rerun_stage.py --topic-id weather_chat
        """,
    )
    parser.add_argument("artifact", nargs="?", help="Path to an existing artifact JSON")
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument("--level", default="A1A2", choices=["A1A2", "B1", "B2"])
    parser.add_argument("--category", default=None, choices=["common_words", "grammar", "vocabulary", "dialogue"])
    parser.add_argument("--topic-id", metavar="TOPIC_ID")
    parser.add_argument("--language", default="nl")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    try:
        if args.artifact:
            # Existing episode mode
            interactive_menu(args.artifact)
        else:
            # From-scratch mode — find or create a scratch artifact, then show menu
            scratch_path: Optional[str] = None
            try:
                scratch_path = _find_scratch(args.level, args.category, args.topic_id)
                print(f"📂 Using existing scratch artifact: {scratch_path}")
            except FileNotFoundError:
                # No scratch artifact yet — run script generation first
                print("No scratch artifact found — generating script first...\n")
                scratch_path = run_scratch_script(args.level, args.category, args.topic_id, args.language)

            interactive_menu(scratch_path)

    except Exception as e:
        LOGGER.exception("rerun_stage.failed")
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

