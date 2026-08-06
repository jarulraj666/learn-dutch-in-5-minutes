#!/usr/bin/env python3
"""
Easy-to-use script to re-run specific stages for an existing episode.
Handles: subtitles, image, video render, YouTube upload.
"""

import json
import sys
import os
import logging
from pathlib import Path
from typing import Optional
import argparse

# Ensure we're in the project root directory
script_dir = Path(__file__).parent
os.chdir(script_dir)
sys.path.insert(0, str(script_dir))


def load_artifact(artifact_path: str) -> dict:
    """Load and validate artifact file."""
    path = Path(artifact_path)
    if not path.exists():
        raise FileNotFoundError(f"Artifact not found: {artifact_path}")
    return json.loads(path.read_text())


def run_subtitles(artifact_path: str, audio_path: Optional[str] = None) -> None:
    """Re-generate subtitles only."""
    from pipeline.generate.generate_subtitles import plan_subtitles
    
    artifact = load_artifact(artifact_path)
    
    # Use provided audio_path or get from artifact
    if not audio_path:
        audio_path = artifact.get("audio_file")
    
    if not audio_path:
        raise FileNotFoundError("Audio file path not provided and not found in artifact")
    
    if not Path(audio_path).exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    
    print(f"🎯 Re-generating subtitles for: {artifact['title_slug']}")
    
    plan_subtitles(
        audio_path,
        output_root=str(Path(artifact_path).parent),
        level=artifact["level"],
        category=artifact["category"],
        topic_id=artifact["topic_id"],
        title_slug=artifact["title_slug"],
        script_dialogue=artifact.get("script", {}).get("dialogue"),
        dialogue_en=artifact.get("script", {}).get("dialogue_en"),
    )
    print("✅ Subtitles regenerated")


def run_script(artifact_path: str) -> None:
    """Re-generate script only."""
    from pipeline.generate.generate_script import generate_script
    from pipeline.core.select_topic import TopicChoice
    
    artifact = load_artifact(artifact_path)
    print(f"🎯 Re-generating script for: {artifact['title_slug']}")
    
    # Create TopicChoice from artifact data — include dialogue speaker/scenario fields
    # so prompt placeholders get substituted correctly.
    topic_meta = artifact.get("topic", {})
    script_meta = artifact.get("script", {})
    speakers = script_meta.get("speakers", [])
    s1 = next((s for s in speakers if s.get("id") == "Speaker1"), {})
    s2 = next((s for s in speakers if s.get("id") == "Speaker2"), {})

    # If the artifact has no speaker/scenario data, load from topic_backlog.yaml
    if not s1 and artifact["category"] == "dialogue":
        from pipeline.core.select_topic import _load_dialogue_metadata
        backlog = _load_dialogue_metadata(artifact["topic_id"])
        s1 = {"role": backlog.get("speaker1_role"), "gender": backlog.get("speaker1_gender")}
        s2 = {"role": backlog.get("speaker2_role"), "gender": backlog.get("speaker2_gender")}
        scenario = topic_meta.get("scenario") or script_meta.get("scenario") or backlog.get("scenario")
    else:
        scenario = topic_meta.get("scenario") or script_meta.get("scenario")

    topic = TopicChoice(
        topic_id=artifact["topic_id"],
        track=topic_meta.get("track", artifact.get("topic_title", "")),
        title_hint=topic_meta.get("title_hint", artifact.get("topic_title", "")),
        level=artifact["level"],
        category=artifact["category"],
        scenario=scenario,
        speaker1_role=s1.get("role"),
        speaker1_gender=s1.get("gender"),
        speaker2_role=s2.get("role"),
        speaker2_gender=s2.get("gender"),
    )
    
    # Generate new script
    script = generate_script(topic, language="nl", level=artifact["level"])
    
    # Update artifact with new script and related fields
    artifact["script"] = script
    artifact["topic_title"] = script.get("topic_title", artifact.get("topic_title"))
    artifact["image_prompt"] = script.get("image_prompt", artifact.get("image_prompt", ""))
    
    # Save updated artifact
    artifact_file = Path(artifact_path)
    artifact_file.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    
    print("✅ Script regenerated")


def run_audio(artifact_path: str) -> str:
    """Re-generate audio only. Returns path to generated audio file."""
    from pipeline.generate.generate_voice import generate_voice_assets
    
    artifact = load_artifact(artifact_path)
    print(f"🎯 Re-generating audio for: {artifact['title_slug']}")
    
    result = generate_voice_assets(
        script=artifact.get("script", {}),
        output_root=str(Path(artifact_path).parent),
        level=artifact["level"],
        category=artifact["category"],
        topic_id=artifact["topic_id"],
        title_slug=artifact["title_slug"],
    )
    audio_path = result.get("dialogue_audio")

    # Persist latest audio paths so subsequent stages can auto-detect correctly.
    if audio_path:
        artifact["audio_file"] = audio_path
    raw_audio_path = result.get("dialogue_audio_raw")
    if raw_audio_path:
        artifact["audio_file_raw"] = raw_audio_path
    artifact_file = Path(artifact_path)
    artifact_file.write_text(json.dumps(artifact, indent=2), encoding="utf-8")

    print("✅ Audio regenerated")
    return audio_path


def run_image(artifact_path: str) -> None:
    """Re-generate background image only."""
    from pipeline.generate.generate_visual_image import generate_image_from_artifact
    
    artifact = load_artifact(artifact_path)
    print(f"🎯 Re-generating image for: {artifact['title_slug']}")
    
    generate_image_from_artifact(artifact)
    print("✅ Image regenerated")


def run_render(artifact_path: str) -> str:
    """Re-render video (after subtitles or image fixes). Returns path to generated video file."""
    from pipeline.publish.render_video import render_from_artifact
    from pathlib import Path
    
    artifact = load_artifact(artifact_path)
    print(f"🎯 Re-rendering video for: {artifact['title_slug']}")
    
    video_path = render_from_artifact(Path(artifact_path))
    print("✅ Video re-rendered")
    return str(video_path)


def run_upload(artifact_path: str, video_path: Optional[str] = None) -> None:
    """Upload to YouTube (after render)."""
    from pipeline.publish.upload_youtube import upload_video
    
    artifact = load_artifact(artifact_path)
    
    # Use provided video_path or look for render manifest
    if not video_path:
        # Try to get from render manifest first
        manifest_path = Path(artifact_path).with_stem(Path(artifact_path).stem + "_render_manifest")
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())
            video_path = manifest.get("planned_video_file")
        
        # Fallback to artifact field
        if not video_path:
            video_path = artifact.get("video_file")
    
    if not video_path:
        raise ValueError("Video file path not provided, not in artifact, and render manifest not found")
    
    if not Path(video_path).exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")
    
    print(f"🎯 Uploading to YouTube: {artifact['title_slug']}")
    
    result = upload_video(Path(artifact_path), Path(video_path))

    # Persist youtube result (video_id, captions_uploaded, etc.) back into artifact
    artifact["youtube"] = result
    Path(artifact_path).write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"✅ Video uploaded: video_id={result.get('video_id')}")


def run_qa(artifact_path: str) -> None:
    """Run audio QA check: compare WAV against script sentences."""
    from pipeline.generate.qa_audio import log_qa_report, run_audio_qa

    artifact = load_artifact(artifact_path)
    print(f"🎯 Running audio QA for: {artifact['title_slug']}")

    audio_path = artifact.get("audio_file_raw") or artifact.get("audio_file") or \
                 artifact.get("voice", {}).get("dialogue_audio", "")
    if not audio_path:
        raise FileNotFoundError("No audio_file path found in artifact")
    if not Path(audio_path).exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    dialogue = artifact.get("script", {}).get("dialogue")
    if not dialogue:
        raise ValueError("No script.dialogue found in artifact")

    language = artifact.get("script", {}).get("language", "nl")
    report = run_audio_qa(wav_path=audio_path, script_dialogue=dialogue, language=language)
    log_qa_report(report, wav_name=Path(audio_path).name)

    hard_failures = [i for i in report.issues if i.issue_type == "MISSING"]
    if hard_failures:
        print(f"⚠️  QA found {len(hard_failures)} missing sentence(s) — see WARNING logs above")
    else:
        print(f"✅ QA passed — {report.found_count}/{report.total_script_sentences} sentences found")


def run_captions(artifact_path: str, video_id: str | None = None) -> None:
    """Upload English SRT caption to an already-uploaded YouTube video."""
    from pipeline.publish.upload_youtube import upload_captions, _get_youtube_client

    artifact = load_artifact(artifact_path)

    if not video_id:
        video_id = artifact.get("youtube", {}).get("video_id", "")
    if not video_id:
        raise ValueError(
            "No YouTube video_id found. Pass --video-id <ID> or upload the video first."
        )

    srt_en_raw = artifact.get("subtitles", {}).get("srt_en", "")
    if not srt_en_raw:
        raise ValueError("No srt_en path found in artifact subtitles.")

    srt_path = Path(srt_en_raw)
    if not srt_path.is_absolute():
        srt_path = Path(artifact_path).parent.parent.parent.parent / srt_en_raw

    if not srt_path.exists():
        raise FileNotFoundError(f"English SRT file not found: {srt_path}")

    print(f"🎯 Uploading caption for video_id={video_id}: {srt_path.name}")

    youtube = _get_youtube_client()
    result = upload_captions(youtube, video_id, srt_path)

    if result:
        caption_id = result.get("id")
        language = result.get("snippet", {}).get("language", "en")
        print(f"✅ Caption uploaded: id={caption_id} language={language}")

        # Persist caption info into artifact
        artifact.setdefault("youtube", {}).setdefault("captions_uploaded", [])
        existing_ids = {c.get("caption_id") for c in artifact["youtube"]["captions_uploaded"]}
        if caption_id not in existing_ids:
            artifact["youtube"]["captions_uploaded"].append({
                "caption_id": caption_id,
                "language": language,
                "name": result.get("snippet", {}).get("name", "English"),
                "srt_file": str(srt_path),
            })
            Path(artifact_path).write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        print("⚠️  Caption upload returned no result (possibly already exists).")


def interactive_menu(artifact_path: str, audio_path: Optional[str] = None, video_path: Optional[str] = None) -> None:
    """Interactive menu for selecting stages to re-run."""
    artifact = load_artifact(artifact_path)
    print(f"\n📺 Episode: {artifact['title_slug']}")
    print(f"   Level: {artifact['level']} | Category: {artifact['category']}")
    print("\nAvailable operations:")
    print("  1) Re-generate script")
    print("  2) Re-generate background image  (needs script)")
    print("  3) Re-generate audio")
    print("  4) Re-generate subtitles         (auto-detects audio from artifact)")
    print("  5) Run audio QA check            (compare WAV against script)")
    print("  6) Re-render video")
    print("  7) Upload to YouTube             (auto-detects video from render manifest)")
    print("  8) Upload captions to YouTube    (requires video already uploaded)")
    print("  9) Run all stages                (complete end-to-end pipeline)")
    print("  0) Exit")
    
    choice = input("\nSelect operation (0-9): ").strip()
    
    if choice == "1":
        run_script(artifact_path)
    elif choice == "2":
        run_image(artifact_path)
    elif choice == "3":
        run_audio(artifact_path)
    elif choice == "4":
        run_subtitles(artifact_path, None)
    elif choice == "5":
        run_qa(artifact_path)
    elif choice == "6":
        run_render(artifact_path)
    elif choice == "7":
        run_upload(artifact_path, None)
    elif choice == "8":
        run_captions(artifact_path)
    elif choice == "9":
        print("\n🚀 Running all stages...\n")
        run_script(artifact_path)
        run_image(artifact_path)
        audio_file = run_audio(artifact_path)
        run_subtitles(artifact_path, audio_file)
        run_qa(artifact_path)
        video_file = run_render(artifact_path)
        run_upload(artifact_path, video_file)
        run_captions(artifact_path)
        print("\n🎉 All stages completed!")
    elif choice == "0":
        print("Exiting...")
        sys.exit(0)
    else:
        print("Invalid choice")


def main():
    parser = argparse.ArgumentParser(
        description="Re-run specific stages for an existing episode",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive menu
  python rerun_stage.py output/A1/common_words/episode_cw_days.json

  # Re-generate script
  python rerun_stage.py output/A1/common_words/episode_cw_days.json --script

  # Re-generate audio
  python rerun_stage.py output/A1/common_words/episode_cw_days.json --audio-gen

  # Re-generate subtitles (auto-detects audio from artifact)
  python rerun_stage.py output/A1/common_words/episode_cw_days.json --subtitles

  # Re-render and upload (auto-detects video from render manifest)
  python rerun_stage.py output/A1/common_words/episode_cw_days.json --render --upload

  # Run all stages (complete end-to-end)
  python rerun_stage.py output/A1/common_words/episode_cw_days.json --all
        """,
    )
    
    parser.add_argument("artifact", help="Path to artifact JSON file")
    parser.add_argument("--log-level", default="INFO", help="DEBUG, INFO, WARNING, ERROR")
    parser.add_argument("--script", action="store_true", help="Re-generate script")
    parser.add_argument("--audio-gen", action="store_true", help="Re-generate audio")
    parser.add_argument("--subtitles", metavar="AUDIO_FILE", nargs="?", const="auto", help="Re-generate subtitles (optional audio file, auto-detects from artifact if omitted)")
    parser.add_argument("--image", action="store_true", help="Re-generate background image")
    parser.add_argument("--render", action="store_true", help="Re-render video")
    parser.add_argument("--upload", metavar="VIDEO_FILE", nargs="?", const="auto", help="Upload to YouTube (optional video file, auto-detects from render manifest if omitted)")
    parser.add_argument("--captions", action="store_true", help="Upload English SRT caption to YouTube (requires video already uploaded)")
    parser.add_argument("--video-id", metavar="VIDEO_ID", help="YouTube video ID override for --captions (use when artifact has no youtube.video_id)")
    parser.add_argument("--all", action="store_true", help="Run all stages (script → audio → subtitles → image → render → upload → captions)")
    parser.add_argument("--qa", action="store_true", help="Run audio QA check: compare WAV against script sentences")
    
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    
    try:
        # If no specific operation, show interactive menu
        if not (args.script or args.audio_gen or args.subtitles or args.image or args.render or args.upload or args.captions or args.all or args.qa):
            interactive_menu(args.artifact, None, None)
            return
        
        # Run specific operations
        if args.script:
            run_script(args.artifact)
        
        audio_file_from_stage = None

        if args.audio_gen:
            audio_file_from_stage = run_audio(args.artifact)
        
        if args.subtitles:
            # Handle optional audio file (None or "auto" triggers auto-detection)
            if args.subtitles == "auto":
                audio_file = audio_file_from_stage
            else:
                audio_file = args.subtitles
            run_subtitles(args.artifact, audio_file)
        
        if args.image:
            run_image(args.artifact)
        
        if args.render:
            run_render(args.artifact)
        
        if args.upload:
            # Handle optional video file (None or "auto" triggers auto-detection)
            video_file = None if args.upload == "auto" else args.upload
            run_upload(args.artifact, video_file)
        
        if args.captions:
            run_captions(args.artifact, video_id=getattr(args, "video_id", None))

        if args.qa:
            run_qa(args.artifact)
        
        if args.all:
            print("\n🚀 Running all stages...\n")
            run_script(args.artifact)
            run_image(args.artifact)
            audio_file = run_audio(args.artifact)
            run_subtitles(args.artifact, audio_file)
            run_qa(args.artifact)
            video_file = run_render(args.artifact)
            run_upload(args.artifact, video_file)
            run_captions(args.artifact)
            print("\n🎉 All stages completed!")
    
    except Exception as e:
        logging.getLogger(__name__).exception("rerun_stage.failed")
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
