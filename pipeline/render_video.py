from __future__ import annotations

import argparse
import json
import logging
import subprocess
import time
from pathlib import Path

from pipeline.generate_visual_image import generate_topic_image
from pipeline import settings
from pipeline.utils import command_exists


LOGGER = logging.getLogger(__name__)


def _format_subtitle_filter_path(path: Path) -> str:
    # ffmpeg subtitles filter uses colon-separated options; escape characters accordingly.
    return path.resolve().as_posix().replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def _supports_subtitles_filter() -> bool:
    try:
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-filters"],
            check=True,
            capture_output=True,
            text=True,
        )
        filters_text = (proc.stdout or "") + "\n" + (proc.stderr or "")
        return " subtitles " in filters_text
    except Exception:
        return False


def _concat_audio(segment_paths: list[str], output_audio: Path) -> tuple[bool, str]:
    if not segment_paths:
        return False, "No audio segments provided"

    list_file = output_audio.parent / "concat_list.txt"
    lines = [f"file '{Path(p).resolve().as_posix()}'" for p in segment_paths if Path(p).exists()]
    if not lines:
        return False, "No existing audio files for concat"
    list_file.write_text("\n".join(lines), encoding="utf-8")

    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_file),
        "-ar",
        "44100",
        "-ac",
        "1",
        str(output_audio),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return True, ""
    except Exception as exc:
        return False, str(exc)


def _build_video(
    audio_path: Path,
    srt_path: Path,
    output_mp4: Path,
    burn_subtitles: bool,
    image_path: Path | None = None,
) -> tuple[bool, str]:
    if not audio_path.exists() or not srt_path.exists():
        return False, "Missing audio or subtitle file"

    render_cfg = settings.load_yaml(settings.ROOT / "config/visual_style.yaml").get("render", {})
    width = int(render_cfg.get("width", 1920))
    height = int(render_cfg.get("height", 1080))
    fps = int(render_cfg.get("fps", 30))
    crf = int(render_cfg.get("crf", 19))
    preset = str(render_cfg.get("preset", "slow"))
    target_duration = int(settings.PEDAGOGY_CONFIG.get("target_duration_seconds", 300))

    # Cartoon/paint style fallback scene built from simple vector-like shapes.
    base_visual_filter = (
        "drawbox=x=0:y=0:w=1920:h=1080:color=#F4F0E6:t=fill,"
        "drawbox=x=0:y=0:w=1920:h=420:color=#CFE8F6:t=fill,"
        "drawbox=x=0:y=760:w=1920:h=320:color=#DCECCB:t=fill,"
        "drawbox=x=220:y=380:w=560:h=360:color=#F2D0A4:t=fill,"
        "drawbox=x=190:y=320:w=620:h=80:color=#C94747:t=fill,"
        "drawbox=x=390:y=500:w=140:h=240:color=#8B5A2B:t=fill,"
        "drawbox=x=980:y=430:w=210:h=300:color=#8CB3D9:t=fill,"
        "drawbox=x=1260:y=470:w=260:h=260:color=#F6B26B:t=fill,"
        "drawbox=x=1180:y=420:w=420:h=40:color=#2E4A7D:t=fill"
    )

    use_image_source = bool(image_path and image_path.exists())
    if use_image_source:
        base_filter = (
            f"scale={width}:{height},"
            "eq=saturation=1.12:contrast=1.06:brightness=0.01,"
            "unsharp=5:5:0.45:3:3:0.0"
        )
        cmd = [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-framerate",
            str(fps),
            "-i",
            str(image_path),
            "-i",
            str(audio_path),
            "-af",
            f"apad=pad_dur={target_duration}",
            "-vf",
            base_filter,
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
            "-t",
            str(target_duration),
            str(output_mp4),
        ]
    else:
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=#F4F0E6:s={width}x{height}:r={fps}",
            "-i",
            str(audio_path),
            "-af",
            f"apad=pad_dur={target_duration}",
            "-vf",
            base_visual_filter,
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
            "-t",
            str(target_duration),
            str(output_mp4),
        ]

    if burn_subtitles:
        subtitle_path = _format_subtitle_filter_path(srt_path)
        subtitle_filter = (
            f"subtitles=filename='{subtitle_path}':"
            "force_style='FontName=Noto Sans,FontSize=42,PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,BorderStyle=3,Outline=2,MarginV=80,Alignment=2'"
        )
        if use_image_source:
            cmd[13] = f"{cmd[13]},{subtitle_filter}"
        else:
            cmd[12] = f"{base_visual_filter},{subtitle_filter}"
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return True, ""
    except subprocess.CalledProcessError as exc:
        return False, (exc.stderr or exc.stdout or str(exc))
    except Exception as exc:
        return False, str(exc)


def render_from_artifact(artifact_path: Path) -> Path:
    render_start = time.perf_counter()
    LOGGER.info("render.start artifact=%s", artifact_path)
    data = json.loads(artifact_path.read_text(encoding="utf-8"))
    out_dir = settings.OUTPUT_DIR
    if not out_dir.is_absolute():
        out_dir = settings.ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # Create video output directory
    video_dir = settings.VIDEO_OUTPUT_DIR
    if not video_dir.is_absolute():
        video_dir = settings.ROOT / video_dir
    video_dir.mkdir(parents=True, exist_ok=True)

    episode_id = data.get("canonical_script_id")
    if not episode_id:
        episode_id = 0
    output_mp4 = video_dir / f"episode_{episode_id}.mp4"
    output_audio = out_dir / f"episode_{episode_id}.wav"
    ffmpeg_available = command_exists("ffmpeg")

    segment_paths = [
        seg.get("audio_file", "")
        for seg in data.get("voice", {}).get("voice_segments", [])
        if seg.get("status") == "generated"
    ]
    srt_file = data.get("subtitles", {}).get("srt_file", "")

    assembled = False
    concat_error = ""
    render_error = ""
    subtitles_filter_available = _supports_subtitles_filter() if ffmpeg_available else False
    subtitle_burned_in = False
    generated_image_file = ""
    image_render_used = False

    topic_data = data.get("topic", {})
    topic_id = topic_data.get("id", "fallback_topic")
    topic_title = topic_data.get("title_hint", "Dutch Lesson")
    LOGGER.info("render.topic id=%s title=%s", topic_id, topic_title)
    image_path = generate_topic_image(
        topic_id=topic_id,
        topic_title=topic_title,
        episode_id=int(episode_id),
        output_root=out_dir,
    )
    generated_image_file = str(image_path)
    LOGGER.info("render.image.generated file=%s", generated_image_file)

    if ffmpeg_available and segment_paths and srt_file:
        concat_ok, concat_error = _concat_audio(segment_paths, output_audio)
        LOGGER.info("render.audio.concat ok=%s segments=%d", concat_ok, len(segment_paths))
        if concat_ok:
            assembled, render_error = _build_video(
                output_audio,
                Path(srt_file),
                output_mp4,
                burn_subtitles=subtitles_filter_available,
                image_path=image_path,
            )
            image_render_used = assembled and image_path.exists()
            subtitle_burned_in = assembled and subtitles_filter_available
            LOGGER.info("render.video.assembled=%s subtitle_burned_in=%s", assembled, subtitle_burned_in)
            if not assembled:
                raise RuntimeError(f"Video render failed: {render_error}")

    render_manifest = {
        "note": "FFmpeg render completed",
        "topic": data.get("topic", {}),
        "planned_video_file": str(output_mp4),
        "video_directory": str(video_dir),
        "visual_style": (settings.ROOT / "config/visual_style.yaml").as_posix(),
        "ffmpeg_available": ffmpeg_available,
        "audio_segments_found": len(segment_paths),
        "srt_file": srt_file,
        "assembled": assembled,
        "subtitles_filter_available": subtitles_filter_available,
        "subtitle_burned_in": subtitle_burned_in,
        "generated_image_file": generated_image_file,
        "image_render_used": image_render_used,
        "concat_error": concat_error,
        "render_error": render_error,
    }

    path = out_dir / f"render_manifest_{episode_id}.json"
    path.write_text(json.dumps(render_manifest, indent=2), encoding="utf-8")
    LOGGER.info(
        "render.done assembled=%s elapsed_sec=%.2f manifest=%s",
        assembled,
        time.perf_counter() - render_start,
        path,
    )
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Render step placeholder")
    parser.add_argument("artifact", help="Path to episode artifact JSON")
    args = parser.parse_args()

    artifact_path = Path(args.artifact)
    result = render_from_artifact(artifact_path)
    print(f"Render manifest written: {result}")


if __name__ == "__main__":
    main()
