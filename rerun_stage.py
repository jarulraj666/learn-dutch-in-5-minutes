#!/usr/bin/env python3
"""
Easy-to-use script to re-run specific stages for an existing episode.
Handles: subtitles, image, video render, YouTube upload.
"""

import json
import sys
import os
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
    )
    print("✅ Subtitles regenerated")


def run_script(artifact_path: str) -> None:
    """Re-generate script only."""
    from pipeline.generate.generate_script import generate_script
    from pipeline.core.select_topic import TopicChoice
    
    artifact = load_artifact(artifact_path)
    print(f"🎯 Re-generating script for: {artifact['title_slug']}")
    
    # Create TopicChoice from artifact data
    topic = TopicChoice(
        topic_id=artifact["topic_id"],
        track=artifact.get("topic_title", ""),
        title_hint=artifact.get("topic_title", ""),
        level=artifact["level"],
        category=artifact["category"],
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
    
    upload_video(Path(artifact_path), Path(video_path))
    print("✅ Video uploaded")


def interactive_menu(artifact_path: str, audio_path: Optional[str] = None, video_path: Optional[str] = None) -> None:
    """Interactive menu for selecting stages to re-run."""
    artifact = load_artifact(artifact_path)
    print(f"\n📺 Episode: {artifact['title_slug']}")
    print(f"   Level: {artifact['level']} | Category: {artifact['category']}")
    print("\nAvailable operations:")
    print("  1) Re-generate script")
    print("  2) Re-generate audio")
    print("  3) Re-generate subtitles (auto-detects audio from artifact)")
    print("  4) Re-generate background image")
    print("  5) Re-render video")
    print("  6) Upload to YouTube (auto-detects video from render manifest)")
    print("  7) Run all stages (complete end-to-end pipeline)")
    print("  0) Exit")
    
    choice = input("\nSelect operation (0-7): ").strip()
    
    if choice == "1":
        run_script(artifact_path)
    elif choice == "2":
        run_audio(artifact_path)
    elif choice == "3":
        run_subtitles(artifact_path, None)
    elif choice == "4":
        run_image(artifact_path)
    elif choice == "5":
        run_render(artifact_path)
    elif choice == "6":
        run_upload(artifact_path, None)
    elif choice == "7":
        print("\n🚀 Running all stages...\n")
        run_script(artifact_path)
        audio_file = run_audio(artifact_path)
        run_subtitles(artifact_path, audio_file)
        run_image(artifact_path)
        video_file = run_render(artifact_path)
        run_upload(artifact_path, video_file)
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
    parser.add_argument("--script", action="store_true", help="Re-generate script")
    parser.add_argument("--audio-gen", action="store_true", help="Re-generate audio")
    parser.add_argument("--subtitles", metavar="AUDIO_FILE", nargs="?", const="auto", help="Re-generate subtitles (optional audio file, auto-detects from artifact if omitted)")
    parser.add_argument("--image", action="store_true", help="Re-generate background image")
    parser.add_argument("--render", action="store_true", help="Re-render video")
    parser.add_argument("--upload", metavar="VIDEO_FILE", nargs="?", const="auto", help="Upload to YouTube (optional video file, auto-detects from render manifest if omitted)")
    parser.add_argument("--all", action="store_true", help="Run all stages (script → audio → subtitles → image → render → upload)")
    
    args = parser.parse_args()
    
    try:
        # If no specific operation, show interactive menu
        if not (args.script or args.audio_gen or args.subtitles or args.image or args.render or args.upload or args.all):
            interactive_menu(args.artifact, None, None)
            return
        
        # Run specific operations
        if args.script:
            run_script(args.artifact)
        
        if args.audio_gen:
            run_audio(args.artifact)
        
        if args.subtitles:
            # Handle optional audio file (None or "auto" triggers auto-detection)
            audio_file = None if args.subtitles == "auto" else args.subtitles
            run_subtitles(args.artifact, audio_file)
        
        if args.image:
            run_image(args.artifact)
        
        if args.render:
            run_render(args.artifact)
        
        if args.upload:
            # Handle optional video file (None or "auto" triggers auto-detection)
            video_file = None if args.upload == "auto" else args.upload
            run_upload(args.artifact, video_file)
        
        if args.all:
            print("\n🚀 Running all stages...\n")
            run_script(args.artifact)
            audio_file = run_audio(args.artifact)
            run_subtitles(args.artifact, audio_file)
            run_image(args.artifact)
            video_file = run_render(args.artifact)
            run_upload(args.artifact, video_file)
            print("\n🎉 All stages completed!")
    
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
