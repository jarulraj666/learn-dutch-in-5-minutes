"""Generate YouTube Shorts — one vertical (1080×1920) clip per scene.

Each entry in ``script.image_prompts`` becomes a self-contained Short:
- Audio is clipped from the full episode WAV at the scene's raw timestamps.
- ASS subtitles are windowed to the scene, time-shifted to 0, and restyled
  for a 1080×1920 PlayRes (blurred background, image pinned to top, speaker
  labels at the bottom).
- A vertical MP4 is rendered with FFmpeg using a blurred-fill background and
  the scene image centred near the top of the frame.

Trigger sentence timing is resolved from the ``_nl.orig.srt`` file (raw
Whisper timestamps, before any playback-speed transform) so that clipped WAV
boundaries exactly match the original audio.
"""
from __future__ import annotations

import logging
import re
import subprocess
import tempfile
import wave
from pathlib import Path

from PIL import Image, ImageOps

LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Vertical canvas constants
# ---------------------------------------------------------------------------
SHORT_WIDTH = 1080
SHORT_HEIGHT = 1920
SHORT_FPS = 30
SHORT_CRF = 19
SHORT_PRESET = "slow"
SHORT_AUDIO_BITRATE = "192k"

# Gap (seconds) added to the end of each scene window so the last word isn't cut off.
_END_BUFFER_SEC = 0.6


# ---------------------------------------------------------------------------
# ASS time helpers (self-contained; avoids importing private render_video symbols)
# ---------------------------------------------------------------------------

def _ass_to_sec(value: str) -> float:
    """Convert ASS timestamp ``H:MM:SS.CC`` to seconds."""
    hms, cs = value.rsplit(".", 1)
    h, m, s = hms.split(":")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(cs) / 100.0


def _sec_to_ass(seconds: float) -> str:
    """Convert seconds to ASS timestamp ``H:MM:SS.CC``."""
    if seconds < 0:
        seconds = 0.0
    total_cs = int(round(seconds * 100))
    h = total_cs // 360000
    rem = total_cs % 360000
    m = rem // 6000
    rem = rem % 6000
    s = rem // 100
    cs = rem % 100
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


# ---------------------------------------------------------------------------
# SRT / timing helpers
# ---------------------------------------------------------------------------

_SRT_TIMESTAMP_RE = re.compile(
    r"(\d+):(\d{2}):(\d{2})[,\.](\d+)\s*-->\s*(\d+):(\d{2}):(\d{2})[,\.](\d+)"
)
_ASS_TAG_RE = re.compile(r"\{[^}]*\}")


def _parse_srt_segments(srt_path: Path) -> list[dict]:
    """Return ``[{start_sec, end_sec, text}]`` from an SRT file."""
    if not srt_path.exists():
        LOGGER.warning("SRT not found: %s", srt_path)
        return []
    segments: list[dict] = []
    for block in re.split(r"\n\n+", srt_path.read_text(encoding="utf-8").strip()):
        lines = block.strip().splitlines()
        if len(lines) < 3:
            continue
        m = _SRT_TIMESTAMP_RE.match(lines[1])
        if not m:
            continue
        h1, m1, s1, ms1, h2, m2, s2, ms2 = (int(x) for x in m.groups())
        start = h1 * 3600 + m1 * 60 + s1 + ms1 / 1000.0
        end = h2 * 3600 + m2 * 60 + s2 + ms2 / 1000.0
        text = " ".join(lines[2:]).strip()
        if text:
            segments.append({"start_sec": start, "end_sec": end, "text": text})
    return segments


def _find_trigger_time(segments: list[dict], trigger: str) -> float | None:
    """Return the start time of the segment best matching *trigger*, or None."""
    trig = trigger.strip().lower()
    if not trig:
        return None
    # Exact match
    for seg in segments:
        if seg["text"].strip().lower() == trig:
            return seg["start_sec"]
    # Substring
    for seg in segments:
        seg_text = seg["text"].strip().lower()
        if trig in seg_text or seg_text in trig:
            return seg["start_sec"]
    # First-5-word prefix
    words = trig.split()
    if len(words) >= 3:
        prefix = " ".join(words[:5])
        for seg in segments:
            if prefix in seg["text"].strip().lower():
                return seg["start_sec"]
    return None


def _wav_duration(wav_path: Path) -> float:
    """Return duration of a WAV file in seconds."""
    with wave.open(str(wav_path), "rb") as wf:
        return wf.getnframes() / wf.getframerate()


# ---------------------------------------------------------------------------
# Scene window computation
# ---------------------------------------------------------------------------

def _compute_scene_windows(
    image_prompts: list[dict],
    srt_segments: list[dict],
    audio_end_sec: float,
    image_files: list[str],
) -> list[dict]:
    """Map each image_prompt to a time window using trigger sentence lookup.

    Returns a list of dicts with keys:
      scene, trigger_sentence, description, image_path,
      start_sec, end_sec
    """
    windows: list[dict] = []
    trigger_times: list[tuple[int, float]] = []

    for i, prompt_info in enumerate(image_prompts):
        trigger = prompt_info.get("trigger_sentence", "")
        t = _find_trigger_time(srt_segments, trigger)
        if t is None:
            LOGGER.warning(
                "Scene %d trigger not found in SRT: %r — skipping scene", i + 1, trigger[:80]
            )
            continue
        trigger_times.append((i, t))
        LOGGER.info("scene=%d trigger_time=%.2fs trigger=%r", i + 1, t, trigger[:60])

    # Sort by time in case the order differs
    trigger_times.sort(key=lambda x: x[1])

    for rank, (orig_idx, start_sec) in enumerate(trigger_times):
        prompt_info = image_prompts[orig_idx]
        if rank + 1 < len(trigger_times):
            end_sec = trigger_times[rank + 1][1]
        else:
            end_sec = audio_end_sec

        # Add a small buffer at the end so the last syllable isn't cut
        end_sec = min(end_sec + _END_BUFFER_SEC, audio_end_sec)

        img_path = image_files[orig_idx] if orig_idx < len(image_files) else ""

        windows.append({
            "scene": orig_idx + 1,
            "trigger_sentence": prompt_info.get("trigger_sentence", ""),
            "description": prompt_info.get("description", ""),
            "image_path": img_path,
            "start_sec": start_sec,
            "end_sec": end_sec,
        })

    return windows


# ---------------------------------------------------------------------------
# Audio clipping
# ---------------------------------------------------------------------------

def _clip_audio(src_wav: Path, dest_wav: Path, start_sec: float, end_sec: float) -> bool:
    """Extract [start_sec, end_sec] from *src_wav* into *dest_wav*."""
    dest_wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start_sec:.6f}",
        "-to", f"{end_sec:.6f}",
        "-i", str(src_wav),
        "-c", "copy",
        str(dest_wav),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)
        return True
    except subprocess.CalledProcessError as exc:
        LOGGER.error("clip_audio.failed start=%.2f end=%.2f: %s", start_sec, end_sec, exc.stderr[-500:])
        return False


# ---------------------------------------------------------------------------
# Vertical ASS creation
# ---------------------------------------------------------------------------

# Vertical style definitions (1080×1920 coordinate space, font 70px)
# MarginV=0 with middle alignment (4/5/6) → text centred vertically on screen
_VERTICAL_STYLE_HEADER = (
    "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
    "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
    "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
    "Alignment, MarginL, MarginR, MarginV, Encoding"
)
# Colours taken from original: white primary, cyan secondary, black outline, semi-transparent bg
# Bold=-1 (bold), Italic=-1 (italic)
_COLOUR_ARGS = "&H00FFFFFF,&H0000FFFF,&H00000000,&HC0000000,-1,-1,0,0,100,100,0,0,3,5,0"

# MarginV=700 with bottom alignment (1/2/3) → text bottom at y = 1920 - 700 = 1220 (~260 px below centre)
# MarginL/MarginR=80 → 80 px safe-zone on outer edges to avoid mobile cutoff
_COLOUR_ARGS = "&H00FFFFFF,&H0000FFFF,&H00000000,&HC0000000,-1,-1,0,0,100,100,0,0,3,5,0"
_VERTICAL_STYLES = {
    "SpeakerL": f"Style: SpeakerL,Roboto,64,{_COLOUR_ARGS},1,150,150,700,1",
    "SpeakerR": f"Style: SpeakerR,Roboto,64,{_COLOUR_ARGS},3,150,150,700,1",
    "Default":  f"Style: Default,Roboto,64,{_COLOUR_ARGS},2,150,150,700,1",
}

# English subtitle styles — italic, slightly smaller, below Dutch (MarginV=600 → y=1320)
# BackColour &H003333CC = soft red RGB(204,51,51) fully opaque (&H00 alpha); white primary text
_EN_COLOUR_ARGS = "&H00FFFFFF,&H00FFFFFF,&H003333CC,&H003333CC,0,-1,0,0,100,100,0,0,3,4,0"
_ENGLISH_STYLES = {
    "EnglishL":       f"Style: EnglishL,Roboto,50,{_EN_COLOUR_ARGS},1,150,150,500,1",
    "EnglishR":       f"Style: EnglishR,Roboto,50,{_EN_COLOUR_ARGS},3,150,150,500,1",
    "EnglishDefault": f"Style: EnglishDefault,Roboto,50,{_EN_COLOUR_ARGS},2,150,150,500,1",
}
_DUTCH_TO_EN_STYLE = {
    "SpeakerL": "EnglishL",
    "SpeakerR": "EnglishR",
    "Default":  "EnglishDefault",
}


def _extract_dialogue_text(item: dict) -> str:
    """Extract plain text from a dialogue item ({Speaker1: text} or {speaker, line})."""
    if isinstance(item, dict):
        if "line" in item:
            return str(item["line"])
        for v in item.values():
            if isinstance(v, str):
                return v
    return ""


def _normalize_lookup_key(text: str) -> str:
    """Strip ASS tags, lowercase and normalise whitespace for fuzzy matching."""
    text = re.sub(r"\{[^}]*\}", "", text)
    text = text.replace("\\N", " ")
    text = re.sub(r"[^\w\s]", "", text.lower())
    return " ".join(text.split())


def _build_en_lookup(dialogue: list, dialogue_en: list) -> dict[str, str]:
    """Return {normalised_dutch_text: english_text} from parallel dialogue lists."""
    result: dict[str, str] = {}
    for nl_item, en_item in zip(dialogue or [], dialogue_en or []):
        nl_text = _extract_dialogue_text(nl_item)
        en_text = _extract_dialogue_text(en_item)
        if nl_text and en_text:
            key = _normalize_lookup_key(nl_text)
            if key:
                result[key] = en_text
    return result


def _create_vertical_ass(
    src_ass: Path,
    dest_ass: Path,
    start_sec: float,
    end_sec: float,
    en_lookup: dict[str, str] | None = None,
) -> bool:
    """Create a vertical-format ASS clipped to [start_sec, end_sec].

    - Updates PlayResX/PlayResY to 1080/1920.
    - Replaces style definitions with vertical-optimised versions.
    - Filters Dialogue events to the time window.
    - Shifts all Dialogue timestamps so the window starts at 0.
    - If *en_lookup* is provided, adds a plain English translation line
      immediately below each Dutch line (no karaoke tags).
    """
    if not src_ass.exists():
        LOGGER.error("Source ASS not found: %s", src_ass)
        return False

    dest_ass.parent.mkdir(parents=True, exist_ok=True)
    lines = src_ass.read_text(encoding="utf-8").splitlines()

    out_lines: list[str] = []
    in_events = False
    in_styles = False
    styles_written = False

    for line in lines:
        stripped = line.strip()

        # ── Script Info ──────────────────────────────────────────────────
        if stripped.startswith("PlayResX:"):
            out_lines.append(f"PlayResX: {SHORT_WIDTH}")
            continue
        if stripped.startswith("PlayResY:"):
            out_lines.append(f"PlayResY: {SHORT_HEIGHT}")
            continue

        # ── Styles section ───────────────────────────────────────────────
        if stripped == "[V4+ Styles]":
            in_styles = True
            in_events = False
            out_lines.append(line)
            continue

        if in_styles and not styles_written:
            if stripped.startswith("Format:"):
                out_lines.append(_VERTICAL_STYLE_HEADER)
                for style_line in _VERTICAL_STYLES.values():
                    out_lines.append(style_line)
                for style_line in _ENGLISH_STYLES.values():
                    out_lines.append(style_line)
                styles_written = True
                continue
            if stripped.startswith("Style:"):
                # Skip original style lines — already replaced above
                continue
            if stripped.startswith("["):
                # End of styles section
                in_styles = False

        if in_styles and stripped.startswith("Style:"):
            continue  # Skip any remaining original styles

        # ── Events section ───────────────────────────────────────────────
        if stripped == "[Events]":
            in_events = True
            in_styles = False
            out_lines.append(line)
            continue

        if in_events and stripped.startswith("Dialogue:"):
            parts = line.split(",", 9)
            if len(parts) < 10:
                continue
            try:
                seg_start = _ass_to_sec(parts[1].strip())
                seg_end = _ass_to_sec(parts[2].strip())
            except Exception:
                continue

            # Keep events that overlap with the window
            if seg_end <= start_sec or seg_start >= end_sec:
                continue

            # Clamp to window boundaries, shift to start at 0
            new_start = max(seg_start - start_sec, 0.0)
            new_end = min(seg_end - start_sec, end_sec - start_sec)
            if new_end <= new_start:
                continue

            # Ensure unknown styles fall back to Default
            style = parts[3].strip()
            if style not in _VERTICAL_STYLES:
                style = "Default"

            parts[1] = _sec_to_ass(new_start)
            parts[2] = _sec_to_ass(new_end)
            parts[3] = style
            out_lines.append(",".join(parts))

            # English translation line (plain text, no karaoke, below Dutch)
            if en_lookup is not None:
                raw_text = parts[9].strip() if len(parts) > 9 else ""
                key = _normalize_lookup_key(raw_text)
                en_text = en_lookup.get(key, "")
                if not en_text and key:
                    # Fallback: match on first 4 words
                    prefix = " ".join(key.split()[:4])
                    for k, v in en_lookup.items():
                        if k.startswith(prefix):
                            en_text = v
                            break
                if en_text:
                    en_parts = parts.copy()
                    en_parts[3] = _DUTCH_TO_EN_STYLE.get(style, "EnglishDefault")
                    en_parts[9] = en_text
                    out_lines.append(",".join(en_parts))
            continue

        out_lines.append(line)

    dest_ass.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    LOGGER.info("vertical_ass.created events_window=[%.2f, %.2f] dest=%s", start_sec, end_sec, dest_ass)
    return True


# ---------------------------------------------------------------------------
# Vertical video render
# ---------------------------------------------------------------------------

def _format_ass_path(path: Path) -> str:
    """Escape ASS path for FFmpeg filter (colons, backslashes, quotes)."""
    return path.resolve().as_posix().replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def _render_short_vertical(
    image_path: Path,
    audio_path: Path,
    ass_path: Path,
    output_mp4: Path,
    playback_speed: float,
    native_vertical: bool = False,
) -> tuple[bool, str]:
    """Render a 1080×1920 Short MP4.

    If *native_vertical* is True the image is already 9:16 and fills the full
    canvas directly (no blurred background).  Otherwise the 16:9 source image
    is zoomed/blurred to fill the background and the original is overlaid in
    the top portion of the frame.

    Layout (native_vertical=False — fallback):
      - Background: source image zoomed/blurred to fill 1080×1920.
      - Foreground: source image scaled to 1080-wide (~608 px tall), pinned
        80 px from the top of the frame.
      - Subtitles: burned from *ass_path* (pre-shifted, vertical-styled).
      - Audio: clipped WAV with atempo applied for consistent pacing.

    Layout (native_vertical=True — preferred):
      - Image: scaled to fill 1080×1920, aspect-preserved with letterbox padding.
      - Subtitles: burned directly on top.
    """
    output_mp4.parent.mkdir(parents=True, exist_ok=True)

    speed = max(0.5, min(2.0, playback_speed))
    formatted_ass = _format_ass_path(ass_path)

    if native_vertical:
        # Native 9:16 image — already normalised to 1080×1920 at generation time,
        # so a straight scale + subtitle burn is all that's needed (no padding/letterbox).
        vf = (
            f"scale={SHORT_WIDTH}:{SHORT_HEIGHT},"
            f"ass='{formatted_ass}',"
            f"format=yuv420p"
        )
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-framerate", str(SHORT_FPS),
            "-i", str(image_path),
            "-i", str(audio_path),
            "-vf", vf,
            "-map", "0:v",
            "-map", "1:a",
            "-af", f"atempo={speed:.6f}",
            "-c:v", "libx264",
            "-preset", SHORT_PRESET,
            "-crf", str(SHORT_CRF),
            "-c:a", "aac",
            "-b:a", SHORT_AUDIO_BITRATE,
            "-ar", "48000",
            "-ac", "2",
            "-shortest",
            str(output_mp4),
        ]
    else:
        # Fallback: 16:9 image → blurred fill background + centred foreground
        filter_complex = (
            f"[0:v]scale={SHORT_WIDTH}:{SHORT_HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={SHORT_WIDTH}:{SHORT_HEIGHT},boxblur=30:3[bg];"
            f"[0:v]scale={SHORT_WIDTH}:-2[fg];"
            f"[bg][fg]overlay=(W-w)/2:80[v_img];"
            f"[v_img]ass='{formatted_ass}',"
            f"format=yuv420p[vout]"
        )
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-framerate", str(SHORT_FPS),
            "-i", str(image_path),
            "-i", str(audio_path),
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-map", "1:a",
            "-af", f"atempo={speed:.6f}",
            "-c:v", "libx264",
            "-preset", SHORT_PRESET,
            "-crf", str(SHORT_CRF),
            "-c:a", "aac",
            "-b:a", SHORT_AUDIO_BITRATE,
            "-ar", "48000",
            "-ac", "2",
            "-shortest",
            str(output_mp4),
        ]

    LOGGER.info("render_short.start output=%s speed=%.2f native_vertical=%s", output_mp4, speed, native_vertical)
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300)
        if result.stderr:
            LOGGER.debug("render_short.ffmpeg_stderr %s", result.stderr[-500:])
        LOGGER.info("render_short.done output=%s", output_mp4)
        return True, ""
    except subprocess.CalledProcessError as exc:
        msg = (exc.stderr or exc.stdout or str(exc))[-1000:]
        LOGGER.error("render_short.failed output=%s: %s", output_mp4, msg)
        return False, msg
    except Exception as exc:
        return False, str(exc)


# ---------------------------------------------------------------------------
# Vertical image generation for Shorts
# ---------------------------------------------------------------------------


def generate_shorts_images(artifact: dict, artifact_path: Path) -> list[dict]:
    """Generate native 9:16 (portrait) scene images for Shorts.

    Builds each scene prompt from the level-specific ``dialogue_image_prompt.md``
    template rendered with portrait orientation, then appends the scene-specific
    environment and focus details from the artifact.  Images are saved under::

        output/{level}/{category}/shorts/episode_{topic_id}_{title_slug}/images/

    Returns a list of dicts::

        [{"scene": 1, "image_path": "output/.../scene_1_vertical.png"}, ...]
    """
    from pipeline.generate.generate_visual_image import (  # noqa: PLC0415
        _enrich_dialogue_image_prompt,
        _generate_multiple_images,
    )

    script = artifact.get("script", {})
    image_prompts: list[dict] = script.get("image_prompts", [])
    if not image_prompts:
        LOGGER.warning("generate_shorts_images: no image_prompts — skipping")
        return []

    topic_id = artifact.get("topic_id", "unknown")
    topic_title = script.get("topic_title", artifact.get("title_slug", "episode"))
    title_slug = artifact.get("title_slug", "")
    level = artifact.get("level", "A1A2")
    category = artifact.get("category", "dialogue")

    workspace = artifact_path.parent.parent.parent.parent
    shorts_base = (
        workspace / "output" / level / category
        / "shorts" / f"episode_{topic_id}_{title_slug}"
    )
    images_dir = shorts_base / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    # Build portrait base prompt from the same template used for landscape images
    # but rendered with portrait=True orientation values.
    script_meta = script.copy()
    script_meta["speakers"] = script.get("speakers", artifact.get("script", {}).get("speakers", []))
    script_meta["scenario"] = script.get("scenario", artifact.get("topic", {}).get("scenario", "street"))
    script_meta["topic_title"] = topic_title
    portrait_base = _enrich_dialogue_image_prompt(script_meta, level, portrait=True)

    # Environment description from Stage 1 (provides scene-specific backdrop details)
    environment = script.get("image_prompt", "")

    # Build per-scene portrait prompts mirroring the landscape format in generate_script.py
    vertical_prompts = []
    for p in image_prompts:
        description = p.get("description", "")
        scene_prompt = (
            f"{portrait_base} "
            f"Environment: {environment} "
            f"Scene focus: {description}. "
            f"Visual emphasis: {description}. "
            f"ABSOLUTE REQUIREMENT — FULL-BLEED CANVAS: Every single pixel of this 9:16 portrait "
            f"image must be covered by richly illustrated content. The background environment must "
            f"extend to every edge and corner with zero white space, zero blank areas, zero empty "
            f"borders, zero padding, and zero margins anywhere in the image. "
            f"Characters are placed naturally within the fully illustrated scene background that "
            f"covers 100% of the canvas from top-left corner to bottom-right corner. "
            f"The bottom portion of the image must show the actual floor, ground, or surface of "
            f"the environment (e.g. floor tiles, carpet, pavement, grass) — NOT a flat colour, "
            f"NOT a gradient, NOT a plain coloured block. It must be a detailed, textured part of "
            f"the same scene that continues naturally from the rest of the image. "
            f"STRICTLY FORBIDDEN: no text, no captions, no labels, no sentences, no written words, "
            f"no dialogue bubbles, no speech bubbles, no subtitles, no watermarks, and absolutely "
            f"no white rectangle, white box, white panel, or any solid-coloured block anywhere in "
            f"the image — especially not in the lower half or centre of the frame."
        )
        vertical_prompts.append({**p, "prompt": scene_prompt})

    LOGGER.info(
        "generate_shorts_images: generating %d vertical images for topic=%s",
        len(vertical_prompts), topic_id,
    )

    # Use the same seed image chosen during landscape image generation (stored in artifact),
    # so the shorts characters match the main video exactly. Fall back to random pick if absent.
    import random as _random  # noqa: PLC0415
    from pipeline import settings as _settings  # noqa: PLC0415
    seed_image_path: Path | None = None
    prior_seed = artifact.get("seed_image_used", "")
    if prior_seed:
        candidate = _settings.ROOT / prior_seed
        if candidate.exists():
            seed_image_path = candidate
            LOGGER.info("generate_shorts_images: reusing episode seed image %s", seed_image_path)
        else:
            LOGGER.warning("generate_shorts_images: stored seed_image_used not found: %s — falling back to random", candidate)
    if seed_image_path is None:
        render_cfg = _settings.load_yaml(_settings.ROOT / "config/visual_style.yaml").get("render", {})
        seed_image_rels = render_cfg.get("dialogue_seed_images") or ([render_cfg["dialogue_seed_image"]] if render_cfg.get("dialogue_seed_image") else [])
        valid_seeds = [_settings.ROOT / r for r in seed_image_rels if (_settings.ROOT / r).exists()]
        if valid_seeds:
            seed_image_path = _random.choice(valid_seeds)
            LOGGER.info("generate_shorts_images: randomly selected seed image %s", seed_image_path)
        elif seed_image_rels:
            LOGGER.warning("generate_shorts_images: none of the configured seed images exist: %s — generating without seed", seed_image_rels)

    # _generate_multiple_images saves to output_root/visuals/episode_{topic_id}_{topic_title}/
    # We pass shorts_base as output_root so images land in shorts/.../visuals/...
    # Pass aspect_ratio="9:16" so Gemini generates native portrait images directly.
    generated = _generate_multiple_images(
        topic_id=topic_id,
        topic_title=topic_title,
        output_root=shorts_base,
        image_prompts=vertical_prompts,
        seed_image_path=seed_image_path,
        aspect_ratio="9:16",
    )

    # Save images to the flat images_dir with predictable names.
    results: list[dict] = []
    for i, (prompt_info, src_path) in enumerate(zip(image_prompts, generated)):
        scene_n = prompt_info.get("scene", i + 1)
        dest = images_dir / f"scene_{scene_n}_vertical.png"
        img = Image.open(src_path)
        img.save(dest, format="PNG")
        rel = str(dest.relative_to(workspace))
        results.append({"scene": scene_n, "image_path": rel})
        LOGGER.info("generate_shorts_images: scene=%d saved %s (%dx%d)", scene_n, dest, img.width, img.height)

    LOGGER.info("generate_shorts_images: done %d images", len(results))
    return results


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_scene_shorts(artifact: dict, artifact_path: Path) -> list[dict]:
    """Generate one Short per scene in ``artifact["script"]["image_prompts"]``.

    Returns a list of dicts (one per successfully rendered scene) with keys:
      scene, start_sec, end_sec, trigger_sentence, description,
      image_path, audio_clip, ass_file, video_file
    """
    script = artifact.get("script", {})
    image_prompts: list[dict] = script.get("image_prompts", [])
    if not image_prompts:
        LOGGER.warning("generate_shorts: no image_prompts found in artifact — skipping")
        return []

    # ── Resolve source file paths ─────────────────────────────────────────
    root = artifact_path.parent.parent.parent  # output/{level}/{category} → output/
    # Some paths in artifact are relative to the workspace root
    workspace = artifact_path.parent.parent.parent.parent  # repo root

    def _resolve(rel: str) -> Path:
        p = Path(rel)
        return p if p.is_absolute() else (workspace / p).resolve()

    audio_path = _resolve(artifact.get("audio_file", ""))
    ass_path = _resolve(artifact.get("karaoke_file", ""))

    # Prefer _nl.orig.srt (raw Whisper timings matching the unmodified WAV)
    srt_nl_raw = artifact.get("subtitles", {}).get("srt_nl") or artifact.get("subtitles", {}).get("nl", "")
    srt_nl_path = _resolve(srt_nl_raw) if srt_nl_raw else Path()
    orig_srt = srt_nl_path.with_name(srt_nl_path.stem + ".orig" + srt_nl_path.suffix)
    timing_srt = orig_srt if orig_srt.exists() else srt_nl_path

    image_files: list[str] = artifact.get("generated_image_files", [])
    playback_speed: float = 1.0  # Shorts always play at full speed; long video uses 0.9

    # Build Dutch→English lookup for inline translation subtitles
    script = artifact.get("script", {})
    en_lookup: dict[str, str] | None = None
    dialogue_nl = script.get("dialogue", [])
    dialogue_en_list = script.get("dialogue_en", [])
    if dialogue_nl and dialogue_en_list:
        en_lookup = _build_en_lookup(dialogue_nl, dialogue_en_list)
        LOGGER.info("generate_shorts: built en_lookup with %d entries", len(en_lookup))

    level = artifact.get("level", "A1A2")
    category = artifact.get("category", "dialogue")
    topic_id = artifact.get("topic_id", "")
    title_slug = artifact.get("title_slug", "")

    # ── Validate sources ─────────────────────────────────────────────────
    for label, path in [("audio", audio_path), ("ASS", ass_path), ("SRT", timing_srt)]:
        if not path.exists():
            LOGGER.error("generate_shorts: missing %s file: %s — aborting", label, path)
            return []

    audio_end_sec = _wav_duration(audio_path)
    LOGGER.info("generate_shorts: audio_duration=%.2fs timing_srt=%s", audio_end_sec, timing_srt)

    srt_segments = _parse_srt_segments(timing_srt)
    if not srt_segments:
        LOGGER.error("generate_shorts: no SRT segments parsed — aborting")
        return []

    # ── Compute per-scene time windows ───────────────────────────────────
    scene_windows = _compute_scene_windows(image_prompts, srt_segments, audio_end_sec, image_files)
    if not scene_windows:
        LOGGER.error("generate_shorts: could not resolve any scene windows — aborting")
        return []

    # ── Output directory ──────────────────────────────────────────────────
    shorts_base = (
        workspace / "output" / level / category
        / "shorts" / f"episode_{topic_id}_{title_slug}"
    )
    shorts_base.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []

    for window in scene_windows:
        scene_n = window["scene"]
        start_sec = window["start_sec"]
        end_sec = window["end_sec"]
        image_file = window["image_path"]
        scene_dir = shorts_base / f"scene_{scene_n}"
        scene_dir.mkdir(parents=True, exist_ok=True)

        LOGGER.info(
            "generate_shorts: scene=%d range=[%.2f, %.2f] duration=%.2fs",
            scene_n, start_sec, end_sec, end_sec - start_sec,
        )

        image_path_obj = _resolve(image_file) if image_file else Path()

        # Prefer native 9:16 vertical image if it was pre-generated
        vertical_image_path: Path | None = None
        shorts_images: list[dict] = artifact.get("shorts_images", [])
        for si in shorts_images:
            if si.get("scene") == scene_n:
                vi = _resolve(si["image_path"])
                if vi.exists():
                    vertical_image_path = vi
                break

        if vertical_image_path:
            render_image = vertical_image_path
            native_vertical = True
            LOGGER.info("generate_shorts: scene=%d using native vertical image", scene_n)
        elif image_path_obj.exists():
            render_image = image_path_obj
            native_vertical = False
        else:
            LOGGER.warning("generate_shorts: scene=%d image missing %s — skipping", scene_n, image_path_obj)
            continue

        # Clip audio
        clip_wav = scene_dir / "audio_clip.wav"
        if not _clip_audio(audio_path, clip_wav, start_sec, end_sec):
            LOGGER.warning("generate_shorts: scene=%d audio clip failed — skipping", scene_n)
            continue

        # Build vertical ASS
        vertical_ass = scene_dir / "subtitles_vertical.ass"
        if not _create_vertical_ass(ass_path, vertical_ass, start_sec, end_sec, en_lookup=en_lookup):
            LOGGER.warning("generate_shorts: scene=%d ASS creation failed — skipping", scene_n)
            continue

        # Render Short MP4
        short_mp4 = scene_dir / f"short_scene_{scene_n}.mp4"
        ok, err = _render_short_vertical(render_image, clip_wav, vertical_ass, short_mp4, playback_speed, native_vertical)
        if not ok:
            LOGGER.warning("generate_shorts: scene=%d render failed: %s — skipping", scene_n, err[:200])
            continue

        results.append({
            "scene": scene_n,
            "start_sec": start_sec,
            "end_sec": end_sec,
            "trigger_sentence": window["trigger_sentence"],
            "description": window["description"],
            "image_path": image_file,
            "audio_clip": str(clip_wav),
            "ass_file": str(vertical_ass),
            "video_file": str(short_mp4),
        })
        LOGGER.info("generate_shorts: scene=%d done video=%s", scene_n, short_mp4)

    LOGGER.info("generate_shorts: completed %d/%d scenes", len(results), len(scene_windows))
    return results
