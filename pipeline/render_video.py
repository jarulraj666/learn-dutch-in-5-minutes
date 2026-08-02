from __future__ import annotations

import argparse
import json
import logging
import subprocess
import time
from pathlib import Path

from pipeline import settings
from pipeline.utils import command_exists

LOGGER = logging.getLogger(__name__)


def _format_subtitle_filter_path(path: Path) -> str:
    """FFmpeg subtitle/ass filters require escaped path characters."""
    return path.resolve().as_posix().replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def _supports_ass_filter() -> bool:
    """Checks if installed FFmpeg has the ass/subtitles filter available."""
    try:
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-filters"],
            capture_output=True,
            text=True,
        )
        output = (proc.stdout or "") + "\n" + (proc.stderr or "")
        return any(f" {name} " in output for name in ("ass", "subtitles"))
    except Exception:
        return False


def _build_video_with_karaoke(
    audio_path: Path,
    ass_path: Path,
    output_mp4: Path,
    burn_subtitles: bool,
    image_path: Path,
) -> tuple[bool, str]:
    if not audio_path.exists():
        return False, f"Missing audio file: {audio_path}"
    if burn_subtitles and not ass_path.exists():
        return False, f"Missing subtitle file: {ass_path}"
    if not image_path or not image_path.exists():
        return False, f"Missing image file: {image_path}"

    render_cfg = settings.load_yaml(settings.ROOT / "config/visual_style.yaml").get("render", {})
    width = int(render_cfg.get("width", 1920))
    height = int(render_cfg.get("height", 1080))
    fps = int(render_cfg.get("fps", 30))
    crf = int(render_cfg.get("crf", 19))
    preset = str(render_cfg.get("preset", "slow"))

    vf_chain = (
        f"scale={width}:{height},"
        "eq=saturation=1.12:contrast=1.06:brightness=0.01,"
        "unsharp=5:5:0.45:3:3:0.0"
    )
    input_args = ["-loop", "1", "-framerate", str(fps), "-i", str(image_path)]

    # Add single full WAV audio input
    input_args.extend(["-i", str(audio_path)])

    # Add Karaoke ASS Filter (Anchored top-middle to top-right flow)
    if burn_subtitles:
        formatted_ass_path = _format_subtitle_filter_path(ass_path)
        ass_filter = f"ass='{formatted_ass_path}'"
        vf_chain += f",{ass_filter}"

    cmd = [
        "ffmpeg",
        "-y",
        *input_args,
        "-map", "0:v",
        "-map", "1:a",
        "-vf",
        vf_chain,
        "-c:v",
        "libx264",
        "-preset",
        preset,
        "-crf",
        str(crf),
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "48000",   # Resample to 48kHz (standard for video)
        "-ac",
        "2",       # Upmix mono to stereo
        "-shortest",  # Sync video duration to audio file length
        str(output_mp4),
    ]

    LOGGER.info("ffmpeg.cmd %s", " ".join(cmd))
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        if result.stderr:
            LOGGER.debug("ffmpeg.stderr %s", result.stderr[-2000:])
        return True, ""
    except subprocess.CalledProcessError as exc:
        LOGGER.error("ffmpeg.failed stderr=%s", (exc.stderr or exc.stdout or "")[-2000:])
        return False, exc.stderr or exc.stdout or str(exc)
    except Exception as exc:
        return False, str(exc)


def render_from_artifact(artifact_path: Path) -> Path:
    render_start = time.perf_counter()
    LOGGER.info("render.start artifact=%s", artifact_path)
    data = json.loads(artifact_path.read_text(encoding="utf-8"))

    out_dir = settings.OUTPUT_DIR
    if not out_dir.is_absolute():
        out_dir = settings.ROOT / out_dir

    # Determine hierarchical video output path from artifact context
    topic_data = data.get("topic", {})
    level = data.get("level") or topic_data.get("level", "")
    category = data.get("category") or topic_data.get("category", "")
    topic_id = data.get("topic_id") or topic_data.get("id", "")
    title_slug = data.get("title_slug") or topic_data.get("title_slug", "")

    if not (level and category and topic_id and title_slug):
        raise ValueError(
            "Artifact must contain level, category, topic_id, and title_slug "
            f"(got level={level!r}, category={category!r}, topic_id={topic_id!r}, title_slug={title_slug!r})"
        )

    video_dir = out_dir / level / category / "videos"
    output_mp4 = video_dir / f"episode_{topic_id}_{title_slug}.mp4"
    video_dir.mkdir(parents=True, exist_ok=True)

    # Use audio_file from artifact as primary source
    audio_path = Path(data["audio_file"]) if data.get("audio_file") else None
    if not audio_path or not audio_path.exists():
        raise FileNotFoundError(
            f"Audio file not found: {audio_path}. Ensure voice generation has run."
        )

    # Retrieve karaoke ASS subtitle file
    ass_file = data.get("karaoke_file") or data.get("srt_files", {}).get("ass_karaoke")
    if not ass_file:
        raise ValueError("Artifact must contain 'karaoke_file' or 'srt_files.ass_karaoke'.")

    ass_path = Path(ass_file).resolve()
    if not ass_path.exists():
        candidate = (settings.ROOT / ass_file).resolve()
        if not candidate.exists():
            raise FileNotFoundError(f"Subtitle file not found: {ass_file}")
        ass_path = candidate

    ffmpeg_available = command_exists("ffmpeg")
    subtitles_filter_available = _supports_ass_filter() if ffmpeg_available else False

    # Require pre-generated background image in artifact
    image_file = data.get("generated_image_file")
    if not image_file:
        raise ValueError("Artifact must contain 'generated_image_file'. Run Stage 3b first.")

    ip = Path(image_file)
    if not ip.is_absolute():
        ip = (settings.ROOT / image_file).resolve()
    if not ip.exists():
        raise FileNotFoundError(f"Image file not found: {image_file}")
    image_path = ip

    assembled = False
    render_error = ""
    subtitle_burned_in = False

    if not ffmpeg_available:
        raise RuntimeError("ffmpeg is not installed or not on PATH.")

    assembled, render_error = _build_video_with_karaoke(
        audio_path=audio_path,
        ass_path=ass_path,
        output_mp4=output_mp4,
        burn_subtitles=subtitles_filter_available,
        image_path=image_path,
    )
    subtitle_burned_in = assembled and subtitles_filter_available
    if not assembled:
        raise RuntimeError(f"Video render failed: {render_error}")

    topic_data = data.get("topic", {})
    render_manifest = {
        "note": "FFmpeg Karaoke render completed",
        "topic": topic_data,
        "planned_video_file": str(output_mp4),
        "input_audio_file": str(audio_path),
        "ass_subtitle_file": str(ass_path) if ass_path else "",
        "ffmpeg_available": ffmpeg_available,
        "assembled": assembled,
        "subtitle_burned_in": subtitle_burned_in,
        "generated_image_file": str(image_path) if image_path else "",
        "render_error": render_error,
    }

    manifest_path = out_dir / level / category / f"episode_{topic_id}_{title_slug}_render_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(render_manifest, indent=2), encoding="utf-8")
    
    LOGGER.info(
        "render.done assembled=%s elapsed_sec=%.2f manifest=%s",
        assembled,
        time.perf_counter() - render_start,
        manifest_path,
    )
    return manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Render full dialogue video with karaoke subtitles")
    parser.add_argument("artifact", help="Path to episode artifact JSON")
    args = parser.parse_args()

    artifact_path = Path(args.artifact)
    result = render_from_artifact(artifact_path)
    print(f"Render manifest written: {result}")


if __name__ == "__main__":
    main()