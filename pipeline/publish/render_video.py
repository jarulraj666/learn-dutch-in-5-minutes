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

def _clamp_playback_speed(speed: float) -> float:
    if speed < 0.5:
        return 0.5
    if speed > 2.0:
        return 2.0
    return speed

def _atempo_chain(speed: float) -> str:
    """Build an ffmpeg atempo filter chain for arbitrary speed in [0.5, 2.0]."""
    return f"atempo={speed:.6f}"


def _apply_final_playback_speed(
    input_mp4: Path,
    output_mp4: Path,
    playback_speed: float,
    crf: int,
    preset: str,
) -> tuple[bool, str]:
    speed = _clamp_playback_speed(playback_speed)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_mp4),
        "-map",
        "0:v",
        "-map",
        "0:a",
        "-vf",
        f"setpts=PTS/{speed:.6f}",
        "-af",
        _atempo_chain(speed),
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
        "48000",
        "-ac",
        "2",
        "-shortest",
        str(output_mp4),
    ]
    LOGGER.info("ffmpeg.final_speed.cmd %s", " ".join(cmd))
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        if result.stderr:
            LOGGER.debug("ffmpeg.final_speed.stderr %s", result.stderr[-2000:])
        return True, ""
    except subprocess.CalledProcessError as exc:
        LOGGER.error("ffmpeg.final_speed.failed stderr=%s", (exc.stderr or exc.stdout or "")[-2000:])
        return False, exc.stderr or exc.stdout or str(exc)
    except Exception as exc:
        return False, str(exc)


def _format_subtitle_filter_path(path: Path) -> str:
    """FFmpeg subtitle/ass filters require escaped path characters."""
    return path.resolve().as_posix().replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def _ass_time_to_seconds(value: str) -> float:
    # ASS format: H:MM:SS.cc (centiseconds)
    hms, cs = value.rsplit(".", 1)
    h, m, s = hms.split(":")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(cs) / 100.0


def _seconds_to_ass_time(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    total_cs = int(round(seconds * 100))
    h = total_cs // 360000
    rem = total_cs % 360000
    m = rem // 6000
    rem = rem % 6000
    s = rem // 100
    cs = rem % 100
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _scale_ass_dialogue_timestamps(ass_in: Path, ass_out: Path, factor: float) -> None:
    """Scale Dialogue line start/end timestamps by *factor* and write to ass_out."""
    lines = ass_in.read_text(encoding="utf-8").splitlines()
    out_lines: list[str] = []

    for line in lines:
        if not line.startswith("Dialogue:"):
            out_lines.append(line)
            continue

        # Expected ASS format: Dialogue: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
        parts = line.split(",", 9)
        if len(parts) < 10:
            out_lines.append(line)
            continue

        try:
            start_s = _ass_time_to_seconds(parts[1]) * factor
            end_s = _ass_time_to_seconds(parts[2]) * factor
            parts[1] = _seconds_to_ass_time(start_s)
            parts[2] = _seconds_to_ass_time(end_s)
            out_lines.append(",".join(parts))
        except Exception:
            out_lines.append(line)

    ass_out.write_text("\n".join(out_lines) + "\n", encoding="utf-8")


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
    playback_speed: float,
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
    playback_speed = _clamp_playback_speed(float(playback_speed))

    vf_chain = (
        f"scale={width}:{height},"
        "eq=saturation=1.12:contrast=1.06:brightness=0.01,"
        "unsharp=5:5:0.45:3:3:0.0"
    )
    if abs(playback_speed - 1.0) > 1e-6:
        vf_chain += f",setpts=PTS/{playback_speed:.6f}"

    af_chain = _atempo_chain(playback_speed)
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
        "-af",
        af_chain,
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


def _build_intro_clip(
    intro_image: Path,
    output_path: Path,
    width: int,
    height: int,
    fps: int,
    crf: int,
    preset: str,
) -> tuple[bool, str]:
    """Create a 1-second clip from a static image with silent audio."""
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-framerate", str(fps), "-i", str(intro_image),
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
        "-vf", f"scale={width}:{height},setsar=1",
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-t", "1",
        str(output_path),
    ]
    LOGGER.info("ffmpeg.intro_clip %s", " ".join(cmd))
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        if result.stderr:
            LOGGER.debug("ffmpeg.intro_clip.stderr %s", result.stderr[-1000:])
        return True, ""
    except subprocess.CalledProcessError as exc:
        return False, exc.stderr or exc.stdout or str(exc)
    except Exception as exc:
        return False, str(exc)


def _concat_video_segments(
    parts: list[Path],
    output_path: Path,
    width: int,
    height: int,
    fps: int,
    crf: int,
    preset: str,
) -> tuple[bool, str]:
    """Concatenate A/V segments together so audio stays aligned per segment."""
    n = len(parts)
    inputs: list[str] = []
    for p in parts:
        inputs.extend(["-i", str(p)])

    filter_parts: list[str] = []
    for i in range(n):
        # Reset timestamps per segment before concatenation to avoid boundary drift.
        filter_parts.append(f"[{i}:v]scale={width}:{height},fps={fps},setsar=1,setpts=PTS-STARTPTS[v{i}]")
        filter_parts.append(
            f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,asetpts=PTS-STARTPTS[a{i}]"
        )

    av_in = "".join(f"[v{i}][a{i}]" for i in range(n))
    filter_parts.append(f"{av_in}concat=n={n}:v=1:a=1[outv][outa]")
    filter_complex = ";".join(filter_parts)

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        str(output_path),
    ]
    LOGGER.info("ffmpeg.concat %s", " ".join(cmd))
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        if result.stderr:
            LOGGER.debug("ffmpeg.concat.stderr %s", result.stderr[-2000:])
        return True, ""
    except subprocess.CalledProcessError as exc:
        LOGGER.error("ffmpeg.concat.failed stderr=%s", (exc.stderr or exc.stdout or "")[-2000:])
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

    # Use audio_file from artifact as primary source, with fallback to raw audio path.
    audio_path = Path(data["audio_file"]) if data.get("audio_file") else None
    if not audio_path or not audio_path.exists():
        raw_audio_file = data.get("audio_file_raw")
        if raw_audio_file and Path(raw_audio_file).exists():
            audio_path = Path(raw_audio_file)
            LOGGER.warning(
                "render.audio.fallback_to_raw missing=%s raw=%s",
                data.get("audio_file"),
                raw_audio_file,
            )
        else:
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

    ass_path_for_render = ass_path

    ffmpeg_available = command_exists("ffmpeg")
    subtitles_filter_available = _supports_ass_filter() if ffmpeg_available else False

    # Require pre-generated background image in artifact
    image_file = data.get("generated_image_file")
    if not image_file:
        raise ValueError("Artifact must contain 'generated_image_file'. Ensure image generation ran successfully.")

    ip = Path(image_file)
    if not ip.is_absolute():
        ip = (settings.ROOT / image_file).resolve()
    if not ip.exists():
        raise FileNotFoundError(f"Image file not found: {image_file}")
    image_path = ip

    assembled = False
    render_error = ""
    subtitle_burned_in = False

    render_cfg = settings.load_yaml(settings.ROOT / "config/visual_style.yaml").get("render", {})
    width = int(render_cfg.get("width", 1920))
    height = int(render_cfg.get("height", 1080))
    fps = int(render_cfg.get("fps", 30))
    crf = int(render_cfg.get("crf", 19))
    preset = str(render_cfg.get("preset", "slow"))
    configured_speed = _clamp_playback_speed(float(render_cfg.get("playback_speed", 1.0)))
    playback_speed = configured_speed
    speed_application = str(render_cfg.get("speed_application", "final_output")).strip().lower()

    if speed_application == "pre_slow_audio":
        # Audio was already slowed before subtitle generation.
        # Keep render at realtime speed to avoid double-slowing.
        playback_speed = 1.0

    if speed_application == "final_output":
        # Apply speed once after final stitched video is produced.
        playback_speed = 1.0

    scaled_ass_tmp: Path | None = None
    ass_timestamps_scaled = False
    if speed_application == "render_filters" and abs(playback_speed - 1.0) > 1e-6:
        # Stretch subtitle event times to match slowed/sped media timeline.
        scale_factor = 1.0 / playback_speed
        scaled_ass_tmp = video_dir / f"_scaled_{ass_path.name}"
        _scale_ass_dialogue_timestamps(ass_path, scaled_ass_tmp, scale_factor)
        ass_path_for_render = scaled_ass_tmp
        ass_timestamps_scaled = True
        LOGGER.info(
            "ass.timestamps.scaled factor=%.6f speed=%.6f src=%s dst=%s",
            scale_factor,
            playback_speed,
            ass_path,
            scaled_ass_tmp,
        )
    elif speed_application != "render_filters":
        LOGGER.info(
            "ass.timestamps.unchanged mode=%s (no ASS timestamp scaling)",
            speed_application,
        )

    if not ffmpeg_available:
        raise RuntimeError("ffmpeg is not installed or not on PATH.")

    # Render main video (with burned subtitles) to a temp path so concat
    # does not disturb the subtitle timing offsets.
    main_video_tmp = video_dir / f"_main_{output_mp4.name}"
    assembled, render_error = _build_video_with_karaoke(
        audio_path=audio_path,
        ass_path=ass_path_for_render,
        output_mp4=main_video_tmp,
        burn_subtitles=subtitles_filter_available,
        image_path=image_path,
        playback_speed=playback_speed,
    )
    subtitle_burned_in = assembled and subtitles_filter_available
    if not assembled:
        raise RuntimeError(f"Video render failed: {render_error}")

    # Stitch intro image (1 s) + main video + end video
    intro_image = settings.ROOT / "assets" / "static_images" / "intro_image.png"
    end_video = settings.ROOT / "assets" / "static_videos" / "end_video.mp4"

    concat_parts: list[Path] = []
    intro_clip_tmp: Path | None = None

    if intro_image.exists():
        intro_clip_tmp = video_dir / "_intro_clip.mp4"
        ok, err = _build_intro_clip(intro_image, intro_clip_tmp, width, height, fps, crf, preset)
        if ok:
            concat_parts.append(intro_clip_tmp)
        else:
            LOGGER.warning("intro_clip.failed err=%s — skipping intro", err)
            intro_clip_tmp = None
    else:
        LOGGER.warning("intro_image.not_found path=%s — skipping intro", intro_image)

    concat_parts.append(main_video_tmp)

    if end_video.exists():
        concat_parts.append(end_video)
    else:
        LOGGER.warning("end_video.not_found path=%s — skipping outro", end_video)

    if len(concat_parts) > 1:
        ok, err = _concat_video_segments(concat_parts, output_mp4, width, height, fps, crf, preset)
        if not ok:
            LOGGER.warning("concat.failed err=%s — using main video only", err)
            main_video_tmp.replace(output_mp4)
    else:
        main_video_tmp.replace(output_mp4)

    if speed_application == "final_output" and abs(configured_speed - 1.0) > 1e-6:
        final_speed_tmp = video_dir / f"_final_speed_{output_mp4.name}"
        ok, err = _apply_final_playback_speed(output_mp4, final_speed_tmp, configured_speed, crf, preset)
        if not ok:
            raise RuntimeError(f"Final playback speed pass failed: {err}")
        final_speed_tmp.replace(output_mp4)

    # Clean up temp files
    for tmp in [main_video_tmp, intro_clip_tmp, scaled_ass_tmp]:
        if tmp and tmp.exists():
            tmp.unlink(missing_ok=True)

    topic_data = data.get("topic", {})
    render_manifest = {
        "note": "FFmpeg Karaoke render completed",
        "note_subtitle_styling": "Dialogue episodes use multi-speaker ASS styles (SpeakerL, SpeakerR); other categories use Default center-aligned style",
        "topic": topic_data,
        "planned_video_file": str(output_mp4),
        "input_audio_file": str(audio_path),
        "ass_subtitle_file": str(ass_path) if ass_path else "",
        "ffmpeg_available": ffmpeg_available,
        "assembled": assembled,
        "subtitle_burned_in": subtitle_burned_in,
        "playback_speed": configured_speed,
        "speed_application": speed_application,
        "ass_timestamps_scaled": ass_timestamps_scaled,
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