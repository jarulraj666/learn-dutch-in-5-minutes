from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import time
from pathlib import Path

from pipeline import settings
from pipeline.utils import command_exists

LOGGER = logging.getLogger(__name__)

# English subtitle style for long video — matches the shorts English style from generate_shorts.py:
# Roboto 50pt, white text, italic, soft-red outline & back (&H003333CC = BGR 51,51,204)
_EN_SUBTITLE_FORCE_STYLE = (
    "FontName=Roboto,FontSize=50,"
    "PrimaryColour=&H00FFFFFF,SecondaryColour=&H00FFFFFF,"
    "OutlineColour=&H003333CC,BackColour=&H003333CC,"
    "Bold=0,Italic=1,Alignment=2,MarginV=60,BorderStyle=3,Outline=4,Shadow=0"
)


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


def _transform_srt_timestamps(
    srt_in: Path,
    srt_out: Path,
    offset_sec: float = 0.0,
    speed: float = 1.0,
) -> None:
    """Transform SRT timestamps: new_time = (original_time + offset_sec) / speed.

    Handles both intro offset and final-output playback speed in one pass so
    the YouTube caption track stays in sync with the final rendered video.
    """
    import re

    _TIMESTAMP_RE = re.compile(
        r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})"
    )
    _safe_speed = max(speed, 0.01)

    def _transform(h: str, m: str, s: str, ms: str) -> str:
        original_ms = (int(h) * 3600 + int(m) * 60 + int(s)) * 1000 + int(ms)
        original_sec = original_ms / 1000.0
        new_sec = max(0.0, (original_sec + offset_sec) / _safe_speed)
        new_total_ms = int(round(new_sec * 1000))
        new_h, rem = divmod(new_total_ms, 3_600_000)
        new_m, rem = divmod(rem, 60_000)
        new_s, new_ms = divmod(rem, 1_000)
        return f"{new_h:02d}:{new_m:02d}:{new_s:02d},{new_ms:03d}"

    def _replace_match(m: re.Match) -> str:
        start = _transform(m.group(1), m.group(2), m.group(3), m.group(4))
        end = _transform(m.group(5), m.group(6), m.group(7), m.group(8))
        return f"{start} --> {end}"

    text = srt_in.read_text(encoding="utf-8")
    srt_out.write_text(_TIMESTAMP_RE.sub(_replace_match, text), encoding="utf-8")


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


def _build_video_with_multi_images(
    audio_path: Path,
    ass_path: Path,
    output_mp4: Path,
    burn_subtitles: bool,
    image_paths: list[Path],
    playback_speed: float,
    en_srt_path: Path | None = None,
) -> tuple[bool, str]:
    """Build video from multiple images with fade transitions between them.
    
    Creates individual video clips for each image (with fade duration),
    concatenates them, applies color/subtitle filters, and encodes to MP4.
    
    Args:
        audio_path: Path to audio WAV file
        ass_path: Path to ASS subtitle file
        output_mp4: Output video file path
        burn_subtitles: Whether to burn subtitles into video
        image_paths: List of image paths for each scene (in order)
        playback_speed: Playback speed factor (e.g., 0.9 for 90% speed)
    
    Returns:
        Tuple of (success: bool, error_message: str)
    """
    if not audio_path.exists():
        return False, f"Missing audio file: {audio_path}"
    if burn_subtitles and not ass_path.exists():
        return False, f"Missing subtitle file: {ass_path}"
    if not image_paths or not all(p.exists() for p in image_paths):
        missing = [p for p in image_paths if not p.exists()]
        return False, f"Missing image files: {missing}"
    
    render_cfg = settings.load_yaml(settings.ROOT / "config/visual_style.yaml").get("render", {})
    width = int(render_cfg.get("width", 1920))
    height = int(render_cfg.get("height", 1080))
    fps = int(render_cfg.get("fps", 30))
    crf = int(render_cfg.get("crf", 19))
    preset = str(render_cfg.get("preset", "slow"))
    fade_duration = float(render_cfg.get("fade_duration", 1.5))
    playback_speed = _clamp_playback_speed(float(playback_speed))
    
    # Get total audio duration
    try:
        import wave
        with wave.open(str(audio_path), 'rb') as wav_file:
            frames = wav_file.getnframes()
            rate = wav_file.getframerate()
            total_duration = frames / rate
    except Exception as e:
        LOGGER.warning("Failed to read audio duration: %s. Using fallback.", str(e))
        total_duration = 60.0
    
    num_images = len(image_paths)
    duration_per_image = total_duration / num_images
    
    LOGGER.info(
        "multi_image.render num_images=%d total_duration=%.2f duration_per_image=%.2f fade_duration=%.2f",
        num_images,
        total_duration,
        duration_per_image,
        fade_duration,
    )
    
    # Create temporary directory for intermediate clips
    import tempfile
    temp_dir = Path(tempfile.mkdtemp(prefix="video_render_"))
    try:
        # Step 1: Create individual clips for each image with proper duration
        clip_files = []
        for i, img_path in enumerate(image_paths):
            clip_output = temp_dir / f"clip_{i:02d}.mp4"
            
            # Create clip with duration slightly longer to account for fade overlap
            # The last image holds until end of audio
            if i == num_images - 1:
                clip_duration = total_duration - (i * duration_per_image)
            else:
                clip_duration = duration_per_image + fade_duration / 2
            
            LOGGER.info(
                "multi_image.creating_clip image_index=%d duration=%.2f output=%s",
                i,
                clip_duration,
                clip_output,
            )
            
            # ffmpeg: create video from image with specified duration
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1",
                "-framerate", str(fps),
                "-i", str(img_path),
                "-f", "lavfi",
                "-i", f"anullsrc=channel_layout=stereo:sample_rate=48000",
                "-vf", f"scale={width}:{height},format=yuv420p",
                "-c:v", "libx264",
                "-preset", "ultrafast",  # Fast encoding for intermediate clips
                "-crf", "28",  # Lower quality OK for intermediate
                "-c:a", "aac",
                "-t", str(clip_duration),
                str(clip_output),
            ]
            
            try:
                result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)
                clip_files.append(clip_output)
                LOGGER.debug("multi_image.clip_created index=%d", i)
            except subprocess.CalledProcessError as e:
                LOGGER.error("multi_image.clip_failed index=%d stderr=%s", i, e.stderr[-500:] if e.stderr else "")
                return False, f"Failed to create clip {i}: {e.stderr or str(e)}"
            except Exception as e:
                return False, f"Error creating clip {i}: {str(e)}"
        
        # Step 2: Create concat demuxer file
        concat_file = temp_dir / "concat.txt"
        concat_content = "\n".join(f"file '{clip.resolve()}'" for clip in clip_files)
        concat_file.write_text(concat_content, encoding="utf-8")
        
        LOGGER.info("multi_image.concat_demuxer created with %d clips", len(clip_files))
        
        # Step 3: Concatenate clips
        concat_output = temp_dir / "concat.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-c:v", "copy",  # Copy video codec (no re-encoding)
            "-c:a", "copy",  # Copy audio codec
            str(concat_output),
        ]
        
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300)
            LOGGER.debug("multi_image.concat_complete")
        except subprocess.CalledProcessError as e:
            LOGGER.error("multi_image.concat_failed stderr=%s", e.stderr[-500:] if e.stderr else "")
            return False, f"Failed to concatenate clips: {e.stderr or str(e)}"
        except Exception as e:
            return False, f"Error concatenating clips: {str(e)}"
        
        # Step 4: Re-sync with actual audio and apply filters/subtitles
        vf_chain = (
            f"scale={width}:{height},"
            "eq=saturation=1.12:contrast=1.06:brightness=0.01,"
            "unsharp=5:5:0.45:3:3:0.0"
        )
        
        if burn_subtitles:
            formatted_ass_path = _format_subtitle_filter_path(ass_path)
            ass_filter = f"ass='{formatted_ass_path}'"
            vf_chain += f",{ass_filter}"
        if en_srt_path and en_srt_path.exists():
            formatted_en_path = _format_subtitle_filter_path(en_srt_path)
            vf_chain += f",subtitles='{formatted_en_path}':force_style='{_EN_SUBTITLE_FORCE_STYLE}'"
        
        af_chain = _atempo_chain(playback_speed)
        
        cmd = [
            "ffmpeg", "-y",
            "-i", str(concat_output),
            "-i", str(audio_path),
            "-map", "0:v",
            "-map", "1:a",
            "-vf", vf_chain,
            "-af", af_chain,
            "-c:v", "libx264",
            "-preset", preset,
            "-crf", str(crf),
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "48000",
            "-ac", "2",
            "-shortest",
            str(output_mp4),
        ]
        
        LOGGER.info("multi_image.final_encode cmd=%s", " ".join(cmd))
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)
            if result.stderr:
                LOGGER.debug("multi_image.encode.stderr %s", result.stderr[-1000:])
            LOGGER.info("multi_image.render_complete output=%s", output_mp4)
            return True, ""
        except subprocess.CalledProcessError as e:
            LOGGER.error("multi_image.encode_failed stderr=%s", (e.stderr or e.stdout or "")[-1000:])
            return False, e.stderr or e.stdout or str(e)
        except Exception as e:
            return False, str(e)
        
    finally:
        # Clean up temporary files
        import shutil
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
            LOGGER.debug("multi_image.temp_cleanup removed %s", temp_dir)
        except Exception as e:
            LOGGER.warning("multi_image.temp_cleanup_failed: %s", str(e))


def _parse_srt_segments(srt_path: Path) -> list[dict]:
    """Parse an SRT file to extract plain-text dialogue segment timings.

    Returns:
        List of dicts: {start_sec, end_sec, text}
    """
    segments = []
    if not srt_path.exists():
        LOGGER.warning("SRT file not found: %s", srt_path)
        return segments
    try:
        content = srt_path.read_text(encoding="utf-8")
        blocks = re.split(r"\n\n+", content.strip())
        for block in blocks:
            lines = block.strip().splitlines()
            if len(lines) < 3:
                continue
            try:
                # Line 0: index, Line 1: timestamps, Line 2+: text
                ts_line = lines[1]
                m = re.match(
                    r"(\d+):(\d{2}):(\d{2})[,\.](\d+)\s*-->\s*(\d+):(\d{2}):(\d{2})[,\.](\d+)",
                    ts_line,
                )
                if not m:
                    continue
                h1, m1, s1, ms1, h2, m2, s2, ms2 = (int(x) for x in m.groups())
                start_sec = h1 * 3600 + m1 * 60 + s1 + ms1 / 1000.0
                end_sec   = h2 * 3600 + m2 * 60 + s2 + ms2 / 1000.0
                text = " ".join(lines[2:]).strip()
                if text:
                    segments.append({"start_sec": start_sec, "end_sec": end_sec, "text": text})
            except (ValueError, IndexError):
                continue
        LOGGER.info("Parsed %d segments from SRT file", len(segments))
    except Exception as e:
        LOGGER.error("Error parsing SRT file: %s", str(e))
    return segments


def _parse_ass_segments(ass_path: Path) -> list[dict]:
    """Parse ASS subtitle file to extract dialogue segment timings.
    
    Reads [Events] section and extracts precise timing for each subtitle line.
    ASS format: Dialogue: Layer,Start,End,Style,...,Text
    Time format: 0:00:00.28 (centiseconds)
    
    Args:
        ass_path: Path to ASS subtitle file
    
    Returns:
        List of dicts: {start_sec, end_sec, text, style}
    """
    segments = []
    
    if not ass_path.exists():
        LOGGER.warning("ASS file not found: %s", ass_path)
        return segments
    
    try:
        content = ass_path.read_text(encoding="utf-8")
        in_events = False
        
        for line in content.split("\n"):
            if line.strip() == "[Events]":
                in_events = True
                continue
            
            if in_events and line.startswith("Dialogue:"):
                # Format: Dialogue: Layer,Start,End,Style,Name,...,Text
                parts = line.split(",", 9)  # Split into parts, max 10
                if len(parts) >= 10:
                    try:
                        start_str = parts[1].strip()  # "0:00:00.28"
                        end_str = parts[2].strip()    # "0:00:01.46"
                        style = parts[3].strip()
                        text = parts[9].strip()
                        
                        # Convert ASS time format (H:MM:SS.CS) to seconds
                        def ass_time_to_seconds(time_str):
                            parts = time_str.split(":")
                            hours = int(parts[0])
                            minutes = int(parts[1])
                            seconds_cs = float(parts[2])  # Includes centiseconds
                            return hours * 3600 + minutes * 60 + seconds_cs
                        
                        start_sec = ass_time_to_seconds(start_str)
                        end_sec = ass_time_to_seconds(end_str)
                        duration = end_sec - start_sec
                        
                        # Strip ASS override tags (e.g. {\k30}, {\an8}) from text
                        # so plain-text trigger sentence matching works correctly
                        clean_text = re.sub(r"\{[^}]*\}", "", text).strip()
                        
                        segments.append({
                            "start_sec": start_sec,
                            "end_sec": end_sec,
                            "duration": duration,
                            "text": clean_text,
                            "style": style,
                        })
                    except (ValueError, IndexError) as e:
                        LOGGER.debug("Failed to parse ASS line: %s error=%s", line[:50], str(e))
                        continue
        
        LOGGER.info("Parsed %d dialogue segments from ASS file", len(segments))
        return segments
    
    except Exception as e:
        LOGGER.error("Error parsing ASS file: %s", str(e))
        return []


def _get_segments_for_scene(segments: list[dict], scene_start: float, scene_end: float) -> list[dict]:
    """Find all ASS segments that fall within a scene's time window.
    
    Args:
        segments: List of {start_sec, end_sec, text, ...} from ASS file
        scene_start: Scene start time in seconds
        scene_end: Scene end time in seconds
    
    Returns:
        List of segments that overlap with scene time window
    """
    matching = []
    
    for seg in segments:
        seg_start = seg.get("start_sec", 0)
        seg_end = seg.get("end_sec", 0)
        
        # Check if segment overlaps with scene window
        if seg_end > scene_start and seg_start < scene_end:
            matching.append(seg)
    
    return matching


def _find_segment_by_text(segments: list[dict], trigger_sentence: str) -> dict | None:
    """Find the ASS segment that best matches a trigger sentence.
    
    Looks for the dialogue segment containing the trigger sentence text so
    we can get the exact start time of when that sentence was spoken.
    
    Args:
        segments: List of {start_sec, end_sec, text, ...} from ASS file
        trigger_sentence: Dutch sentence to search for
    
    Returns:
        Matching segment dict, or None if not found
    """
    trigger = trigger_sentence.strip().lower()
    if not trigger:
        return None
    
    # Exact match
    for seg in segments:
        seg_text = seg.get("text", "").strip().lower()
        if trigger == seg_text:
            return seg
    
    # Substring match (trigger in segment or segment in trigger)
    for seg in segments:
        seg_text = seg.get("text", "").strip().lower()
        if trigger in seg_text or seg_text in trigger:
            return seg
    
    # First-words match (first 5 words of trigger sentence)
    trigger_words = trigger.split()
    if len(trigger_words) >= 3:
        trigger_prefix = " ".join(trigger_words[:5])
        for seg in segments:
            seg_text = seg.get("text", "").strip().lower()
            if trigger_prefix in seg_text:
                return seg
    
    return None


def _build_video_with_timed_images(
    audio_path: Path,
    ass_path: Path,
    output_mp4: Path,
    burn_subtitles: bool,
    image_data: list[dict],  # List of {image_path, trigger_sentence}
    playback_speed: float,
    nl_srt_path: Path | None = None,
    en_srt_path: Path | None = None,
) -> tuple[bool, str]:
    """Render video with images timed by matching trigger sentences to subtitle timing.

    Prefers the Dutch SRT file (plain text, no tag stripping needed) for trigger
    sentence lookup. Falls back to ASS parsing if no Dutch SRT is provided.

    Each image has a trigger_sentence (exact Dutch dialogue line). The subtitle file is
    searched for that sentence to find when it was spoken, giving the image's start
    time. The end time is the start of the next scene's trigger sentence (or audio end).

    Args:
        audio_path: Path to dialogue audio WAV file
        ass_path: Path to ASS subtitle file (for burning subtitles)
        output_mp4: Output video file path
        burn_subtitles: Whether to burn subtitles into video
        image_data: List of {image_path, trigger_sentence} for each scene
        playback_speed: Playback speed factor
        nl_srt_path: Optional path to Dutch plain-text SRT for trigger matching
        playback_speed: Playback speed factor
    
    Returns:
        Tuple of (success: bool, error_message: str)
    """
    if not audio_path.exists():
        return False, f"Missing audio file: {audio_path}"
    if burn_subtitles and not ass_path.exists():
        return False, f"Missing subtitle file: {ass_path}"
    
    for img_info in image_data:
        img_path = Path(img_info.get("image_path", ""))
        if not img_path.exists():
            return False, f"Missing image: {img_path}"
    
    render_cfg = settings.load_yaml(settings.ROOT / "config/visual_style.yaml").get("render", {})
    width = int(render_cfg.get("width", 1920))
    height = int(render_cfg.get("height", 1080))
    fps = int(render_cfg.get("fps", 30))
    crf = int(render_cfg.get("crf", 19))
    preset = str(render_cfg.get("preset", "slow"))
    playback_speed = _clamp_playback_speed(float(playback_speed))
    
    if not ass_path.exists():
        return False, f"ASS subtitle file required but missing: {ass_path}"

    if not nl_srt_path or not nl_srt_path.exists():
        return False, f"Dutch SRT required for trigger sentence matching but missing: {nl_srt_path}"

    timing_segments = _parse_srt_segments(nl_srt_path)
    if not timing_segments:
        return False, f"No segments found in Dutch SRT: {nl_srt_path}"

    LOGGER.info("timed_image.nl_srt segments=%d path=%s", len(timing_segments), nl_srt_path)

    audio_end_sec = 0.0
    try:
        import wave
        with wave.open(str(audio_path), "rb") as wf:
            audio_end_sec = wf.getnframes() / wf.getframerate()
    except Exception as e:
        LOGGER.warning("Could not read audio duration: %s — using last segment end", str(e))
        audio_end_sec = max(s.get("end_sec", 0) for s in timing_segments)

    LOGGER.info(
        "timed_image.render num_images=%d srt_segments=%d audio_end=%.2f",
        len(image_data), len(timing_segments), audio_end_sec,
    )

    # Resolve each scene's start time by finding its trigger sentence in subtitle file
    scene_starts: list[float] = []
    for i, img_info in enumerate(image_data):
        trigger = img_info.get("trigger_sentence", "")
        seg = _find_segment_by_text(timing_segments, trigger)
        if seg is None:
            return False, (
                f"Trigger sentence for scene {i} not found in subtitle file: {trigger!r}. "
                f"Ensure the sentence appears verbatim in the dialogue."
            )
        scene_starts.append(seg["start_sec"])
        LOGGER.info(
            "timed_image.scene index=%d trigger=%r matched_at=%.2fs",
            i, trigger[:60], seg["start_sec"],
        )
    
    # Sort scenes by start time (ASS order)
    indexed_starts = sorted(enumerate(scene_starts), key=lambda x: x[1])
    
    import tempfile
    temp_dir = Path(tempfile.mkdtemp(prefix="video_render_"))
    try:
        # Step 1: Create individual clips — each runs from trigger start to next trigger start.
        # The first clip always starts from 0 (not from scene 1's trigger time) so the
        # concatenated video duration matches the full audio duration and all scene transitions
        # align correctly with the spoken trigger sentences.
        clip_files = []
        for rank, (orig_idx, start_sec) in enumerate(indexed_starts):
            img_info = image_data[orig_idx]
            img_path = Path(img_info.get("image_path", ""))
            clip_output = temp_dir / f"clip_{rank:02d}.mp4"

            # First clip: always starts at 0 to keep video/audio durations in sync
            effective_start = 0.0 if rank == 0 else start_sec

            # End time = next scene's trigger start, or audio end for the last scene
            if rank + 1 < len(indexed_starts):
                end_sec = indexed_starts[rank + 1][1]
            else:
                end_sec = audio_end_sec

            clip_duration = max(end_sec - effective_start, 0.5)  # minimum 0.5s safety floor
            
            LOGGER.info(
                "timed_image.clip rank=%d orig_scene=%d trigger_at=%.2f effective_start=%.2f end=%.2f duration=%.2f",
                rank, orig_idx, start_sec, effective_start, end_sec, clip_duration,
            )
            
            # ffmpeg: create video from image with specified duration
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1",
                "-framerate", str(fps),
                "-i", str(img_path),
                "-f", "lavfi",
                "-i", f"anullsrc=channel_layout=stereo:sample_rate=48000",
                "-vf", f"scale={width}:{height},format=yuv420p",
                "-c:v", "libx264",
                "-preset", "ultrafast",  # Fast encoding for intermediate clips
                "-crf", "28",  # Lower quality OK for intermediate
                "-c:a", "aac",
                "-t", str(clip_duration),
                str(clip_output),
            ]
            
            try:
                result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)
                clip_files.append(clip_output)
                LOGGER.debug("timed_image.clip_created index=%d", i)
            except subprocess.CalledProcessError as e:
                LOGGER.error("timed_image.clip_failed index=%d stderr=%s", i, e.stderr[-500:] if e.stderr else "")
                return False, f"Failed to create clip {i}: {e.stderr or str(e)}"
            except Exception as e:
                return False, f"Error creating clip {i}: {str(e)}"
        
        # Step 2: Create concat demuxer file
        concat_file = temp_dir / "concat.txt"
        concat_content = "\n".join(f"file '{clip.resolve()}'" for clip in clip_files)
        concat_file.write_text(concat_content, encoding="utf-8")
        
        LOGGER.debug("timed_image.concat_file created with %d clips", len(clip_files))
        
        # Step 3: Concatenate all clips
        concat_output = temp_dir / "concatenated.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-c", "copy",
            "-y",
            str(concat_output),
        ]
        
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300)
            LOGGER.debug("timed_image.concat_complete")
        except subprocess.CalledProcessError as e:
            LOGGER.error("timed_image.concat_failed stderr=%s", e.stderr[-500:] if e.stderr else "")
            return False, f"Failed to concatenate clips: {e.stderr or str(e)}"
        except Exception as e:
            return False, f"Error concatenating clips: {str(e)}"
        
        # Step 4: Re-sync with audio, apply filters, and encode final output
        vf_chain = (
            f"scale={width}:{height},"
            "eq=saturation=1.12:contrast=1.06:brightness=0.01,"
            "unsharp=5:5:0.45:3:3:0.0"
        )
        
        if burn_subtitles:
            formatted_ass_path = _format_subtitle_filter_path(ass_path)
            ass_filter = f"ass='{formatted_ass_path}'"
            vf_chain += f",{ass_filter}"
        if en_srt_path and en_srt_path.exists():
            formatted_en_path = _format_subtitle_filter_path(en_srt_path)
            vf_chain += f",subtitles='{formatted_en_path}':force_style='{_EN_SUBTITLE_FORCE_STYLE}'"
        
        if abs(playback_speed - 1.0) > 1e-6:
            vf_chain += f",setpts=PTS/{playback_speed:.6f}"
        
        af_chain = _atempo_chain(playback_speed)
        
        cmd = [
            "ffmpeg", "-y",
            "-i", str(concat_output),
            "-i", str(audio_path),
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-vf", vf_chain,
            "-af", af_chain,
            "-c:v", "libx264",
            "-preset", preset,
            "-crf", str(crf),
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "48000",
            "-ac", "2",
            "-shortest",
            str(output_mp4),
        ]
        
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)
            LOGGER.info("timed_image.render_complete output=%s", output_mp4)
            return True, ""
        except subprocess.CalledProcessError as e:
            LOGGER.error("timed_image.encode_failed stderr=%s", e.stderr[-500:] if e.stderr else "")
            return False, f"Failed to encode final video: {e.stderr or str(e)}"
        except Exception as e:
            return False, f"Error encoding video: {str(e)}"
    
    finally:
        # Cleanup temporary directory
        try:
            import shutil
            shutil.rmtree(temp_dir)
            LOGGER.debug("timed_image.temp_cleanup_complete")
        except Exception as e:
            LOGGER.warning("timed_image.temp_cleanup_failed: %s", str(e))


def _build_video_with_karaoke(
    audio_path: Path,
    ass_path: Path,
    output_mp4: Path,
    burn_subtitles: bool,
    image_path: Path,
    playback_speed: float,
    en_srt_path: Path | None = None,
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
    if en_srt_path and en_srt_path.exists():
        formatted_en_path = _format_subtitle_filter_path(en_srt_path)
        vf_chain += f",subtitles='{formatted_en_path}':force_style='{_EN_SUBTITLE_FORCE_STYLE}'"

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


def render_from_artifact(artifact: dict) -> Path:
    render_start = time.perf_counter()
    topic_id = artifact.get("topic_id", "unknown")
    LOGGER.info("render.start topic=%s", topic_id)
    data = artifact

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

    video_dir = out_dir / level / category / "videos" / f"episode_{topic_id}_{title_slug}"
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

    # Dutch SRT for trigger sentence timing lookup.
    # Check all locations the pipeline may write it to.
    _subs = data.get("subtitles") or {}
    _nl_srt_raw = (
        _subs.get("srt_nl")                              # run_subtitles / run_pipeline key
        or (_subs.get("srt_files") or {}).get("nl")      # nested srt_files dict
        or _subs.get("nl")                               # legacy key
        or (data.get("srt_files") or {}).get("nl")       # old top-level key
    )
    nl_srt_path: Path | None = None
    if _nl_srt_raw:
        _p = Path(_nl_srt_raw).resolve()
        if not _p.exists():
            _p = (settings.ROOT / _nl_srt_raw).resolve()
        if _p.exists():
            # Prefer .orig.srt (pre-speed-transform) so re-renders use raw audio timestamps.
            # After the first render, _transform_srt_timestamps rewrites the SRT with
            # intro-offset + speed-adjusted times. Using the transformed file for trigger
            # matching shifts every scene start time forward, causing images to appear late.
            _orig = _p.with_suffix(".orig.srt")
            nl_srt_path = _orig if _orig.exists() else _p

    # English SRT — resolved later after render_cfg is loaded
    _en_srt_raw = _subs.get("srt_en") or (_subs.get("srt_files") or {}).get("en")
    en_srt_path: Path | None = None

    ffmpeg_available = command_exists("ffmpeg")
    subtitles_filter_available = _supports_ass_filter() if ffmpeg_available else False

    # Check for multi-image files (dialogue with 5-6 scenes)
    image_files_multi = data.get("generated_image_files", [])
    image_file = data.get("generated_image_file")
    # Image prompts are stored in script.image_prompts (with trigger_sentence for multi-image timing)
    image_prompts = data.get("image_prompts", []) or data.get("script", {}).get("image_prompts", [])
    
    # Check if image_prompts use trigger_sentence based timing (sentence → ASS lookup)
    has_timing_info = (
        image_prompts 
        and len(image_prompts) > 0 
        and all(
            "trigger_sentence" in p and p["trigger_sentence"]
            for p in image_prompts
        )
    )
    
    LOGGER.info("Multi-image detection: files=%d prompts=%d has_timing=%s", 
                len(image_files_multi), len(image_prompts), has_timing_info)
    
    # Resolve multi-image paths
    if image_files_multi and len(image_files_multi) > 1:
        LOGGER.info("Multi-image rendering detected: %d images", len(image_files_multi))
        image_paths = []
        for img_file in image_files_multi:
            ip = Path(img_file)
            if not ip.is_absolute():
                ip = (settings.ROOT / img_file).resolve()
            if not ip.exists():
                LOGGER.warning("Image file not found: %s. Checking fallback...", img_file)
                # Fallback to single-image mode
                image_files_multi = []
                break
            image_paths.append(ip)
        
        if image_files_multi:  # All images were found
            use_multi_image = True
        else:
            use_multi_image = False
            if not image_file:
                raise ValueError("Artifact must contain 'generated_image_file' or 'generated_image_files'.")
    else:
        use_multi_image = False
        if not image_file:
            raise ValueError("Artifact must contain 'generated_image_file'. Ensure image generation ran successfully.")
    
    # Resolve single image path (fallback or non-dialogue)
    image_path: Path | None = None
    if not use_multi_image:
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
    speed_cfg = render_cfg.get("playback_speed", {})
    if isinstance(speed_cfg, dict):
        raw_speed = speed_cfg.get(category, speed_cfg.get("default", 1.0))
    else:
        raw_speed = speed_cfg
    configured_speed = _clamp_playback_speed(float(raw_speed))
    playback_speed = 1.0  # Speed is always applied as a final pass after rendering

    # English SRT — burned into the video when burn_english_subtitles = true
    if bool(render_cfg.get("burn_english_subtitles", False)) and _en_srt_raw:
        _p = Path(_en_srt_raw).resolve()
        if not _p.exists():
            _p = (settings.ROOT / _en_srt_raw).resolve()
        _orig = _p.with_suffix(".orig.srt")
        if _orig.exists():
            en_srt_path = _orig
        elif _p.exists():
            en_srt_path = _p

    ass_path_for_render = ass_path
    scaled_ass_tmp: Path | None = None
    LOGGER.info("ass.burned_in — timestamps transform not needed (frames move with speed pass)")

    if not ffmpeg_available:
        raise RuntimeError("ffmpeg is not installed or not on PATH.")

    # Render main video (with burned subtitles) to a temp path so concat
    # does not disturb the subtitle timing offsets.
    main_video_tmp = video_dir / f"_main_{output_mp4.name}"
    
    # Choose rendering path based on image type and timing info
    if use_multi_image and has_timing_info:
        # Use dynamic timing-based rendering
        LOGGER.info("Using TIMED multi-image rendering (%d images with dynamic timing)", len(image_paths))
        
        # Build image_data list with trigger sentences for ASS-based timing lookup
        image_data = []
        for idx, (img_path, prompt) in enumerate(zip(image_paths, image_prompts)):
            image_data.append({
                "image_path": str(img_path),
                "trigger_sentence": prompt.get("trigger_sentence", ""),
            })
        
        assembled, render_error = _build_video_with_timed_images(
            audio_path=audio_path,
            ass_path=ass_path_for_render,
            output_mp4=main_video_tmp,
            burn_subtitles=subtitles_filter_available,
            image_data=image_data,
            playback_speed=playback_speed,
            nl_srt_path=nl_srt_path,
            en_srt_path=en_srt_path,
        )
    elif use_multi_image:
        # Use equal-time distribution
        LOGGER.info("Using equal-time multi-image rendering (%d images)", len(image_paths))
        assembled, render_error = _build_video_with_multi_images(
            audio_path=audio_path,
            ass_path=ass_path_for_render,
            output_mp4=main_video_tmp,
            burn_subtitles=subtitles_filter_available,
            image_paths=image_paths,
            playback_speed=playback_speed,
            en_srt_path=en_srt_path,
        )
    else:
        # Single-image rendering
        LOGGER.info("Using single-image rendering")
        assembled, render_error = _build_video_with_karaoke(
            audio_path=audio_path,
            ass_path=ass_path_for_render,
            output_mp4=main_video_tmp,
            burn_subtitles=subtitles_filter_available,
            image_path=image_path,
            playback_speed=playback_speed,
            en_srt_path=en_srt_path,
        )
    
    subtitle_burned_in = assembled and subtitles_filter_available
    if not assembled:
        raise RuntimeError(f"Video render failed: {render_error}")

    # Stitch intro image (1 s) + main video + end video
    intro_image = settings.ROOT / "assets" / "static_images" / "intro_image.png"
    end_video = settings.ROOT / "assets" / "static_videos" / "end_video.mp4"

    concat_parts: list[Path] = []
    intro_clip_tmp: Path | None = None
    intro_duration_sec: float = 0.0

    if intro_image.exists():
        intro_clip_tmp = video_dir / "_intro_clip.mp4"
        ok, err = _build_intro_clip(intro_image, intro_clip_tmp, width, height, fps, crf, preset)
        if ok:
            concat_parts.append(intro_clip_tmp)
            intro_duration_sec = 1.0
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

    if abs(configured_speed - 1.0) > 1e-6:
        final_speed_tmp = video_dir / f"_final_speed_{output_mp4.name}"
        ok, err = _apply_final_playback_speed(output_mp4, final_speed_tmp, configured_speed, crf, preset)
        if not ok:
            raise RuntimeError(f"Final playback speed pass failed: {err}")
        final_speed_tmp.replace(output_mp4)

    # Transform the English SRT timestamps to match the final video timeline:
    #   final_time = (original_time + intro_offset) / playback_speed
    # This accounts for both the prepended intro clip and the final-output speed pass.
    #
    # NOTE: ASS subtitles are burned into the video frames and naturally move with
    # them through the speed pass — no ASS transform is needed here.
    #
    # Always transform from the canonical original (*.orig.srt) so that re-running
    # --render does not compound the scaling (T/0.9 → T/0.81 → ...).
    srt_needs_transform = intro_duration_sec > 0 or abs(configured_speed - 1.0) > 1e-6
    if srt_needs_transform:
        import shutil
        subs = data.get("subtitles", {})
        for srt_key, log_tag in (("srt_en", "srt_en"), ("srt_nl", "srt_nl")):
            srt_raw = subs.get(srt_key, "")
            if not srt_raw:
                continue
            srt_path = Path(srt_raw)
            if not srt_path.is_absolute():
                srt_path = (settings.ROOT / srt_raw).resolve()
            if not srt_path.exists():
                continue
            # Keep an untouched original so rerenders always start from ground truth.
            srt_orig_path = srt_path.with_suffix(".orig.srt")
            if not srt_orig_path.exists():
                shutil.copy2(srt_path, srt_orig_path)
                LOGGER.info("%s.orig.saved path=%s", log_tag, srt_orig_path)
            _transform_srt_timestamps(
                srt_orig_path,
                srt_path,
                offset_sec=intro_duration_sec,
                speed=configured_speed,
            )
            LOGGER.info(
                "%s.timestamps.transformed offset_sec=%.3f speed=%.3f path=%s",
                log_tag,
                intro_duration_sec,
                configured_speed,
                srt_path,
            )

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