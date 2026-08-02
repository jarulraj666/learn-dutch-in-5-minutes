from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import torch
import whisperx
from pipeline.utils import iter_dialogue_turns

# ==============================================================================
# Configuration & Global Caching
# ==============================================================================

# Cache for Wav2Vec2 alignment models to avoid reloading models across calls
_ALIGN_MODEL_CACHE: dict[str, tuple[Any, Any]] = {}


def _get_align_model(language_code: str, device: str) -> tuple[Any, Any]:
    """Retrieve or cache the phoneme alignment model in memory."""
    key = f"{language_code}_{device}"
    if key not in _ALIGN_MODEL_CACHE:
        _ALIGN_MODEL_CACHE[key] = whisperx.load_align_model(
            language_code=language_code, device=device
        )
    return _ALIGN_MODEL_CACHE[key]


# ==============================================================================
# Text Cleaning & Script Processing
# ==============================================================================

def _strip_tts_tags(text: str) -> str:
    """Remove bracketed TTS instructions like [pause for 1 second] [slow] [excited]."""
    return re.sub(r"\[.*?\]", "", text).strip()


def _smooth_segment_boundaries(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Enforce monotonic, non-overlapping segment boundaries."""
    smoothed: list[dict[str, Any]] = []
    prev_end = 0.0

    for seg in segments:
        try:
            start = float(seg.get("start", prev_end))
            end = float(seg.get("end", start))
        except (TypeError, ValueError):
            start = prev_end
            end = prev_end

        start = max(prev_end, start)
        end = max(start, end)

        updated = dict(seg)
        updated["start"] = start
        updated["end"] = end
        smoothed.append(updated)
        prev_end = end

    return smoothed


# ==============================================================================
# Wav2Vec2 Forced Alignment Engine
# ==============================================================================

def align_audio_with_script(
    wav_path: str | Path,
    script_dialogue: list[dict] | None = None,
    language: str = "nl",
) -> list[dict[str, Any]]:
    """Forced alignment using Wav2Vec2.

    Feeds the full script text as a single segment spanning the entire audio so
    that Wav2Vec2 CTC alignment can freely locate each word without pre-set time
    windows.  The resulting per-word timestamps are accumulated back into one
    segment per script line, giving accurate start / end times.
    """
    path = Path(wav_path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {path}")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    audio = whisperx.load_audio(str(path))
    audio_duration = float(audio.shape[0]) / 16000.0

    # Strip TTS tags and build ordered (speaker, clean_text) pairs
    script_turns: list[tuple[str, str]] = [
        (speaker, _strip_tts_tags(text))
        for speaker, text in iter_dialogue_turns(script_dialogue or [])
        if _strip_tts_tags(text)
    ]
    if not script_turns:
        return []

    align_model, metadata = _get_align_model(language_code=language, device=device)

    # One segment = full script text over the full audio duration.
    # Wav2Vec2 CTC alignment locates each word freely — no proportional windows.
    full_text = " ".join(text for _, text in script_turns)
    unaligned = [{"start": 0.0, "end": audio_duration, "text": full_text}]

    aligned_result = whisperx.align(
        unaligned, align_model, metadata, audio, device,
        return_char_alignments=False,
    )

    # Flatten all word-level timestamps from the alignment output
    all_words: list[dict[str, Any]] = []
    for seg in aligned_result.get("segments", []):
        for word in seg.get("words", []):
            if not isinstance(word, dict) or "word" not in word:
                continue
            w_start = word.get("start")
            w_end = word.get("end")
            all_words.append({
                "word": str(word["word"]).strip(),
                "start": float(w_start) if w_start is not None else None,
                "end": float(w_end) if w_end is not None else None,
            })

    # Reconstruct one segment per script line using word-count slicing
    segments: list[dict[str, Any]] = []
    word_idx = 0
    for speaker, line_text in script_turns:
        n = len(line_text.split())
        if n == 0:
            continue

        line_words = all_words[word_idx : word_idx + n]
        word_idx += n

        valid_starts = [w["start"] for w in line_words if w.get("start") is not None]
        valid_ends   = [w["end"]   for w in line_words if w.get("end")   is not None]

        line_start = valid_starts[0] if valid_starts else (segments[-1]["end"] if segments else 0.0)
        line_end   = valid_ends[-1]  if valid_ends   else line_start

        segments.append({
            "start":   max(0.0, line_start),
            "end":     max(line_start, line_end),
            "text":    line_text,
            "words":   line_words,
            "speaker": speaker,
        })

    return _smooth_segment_boundaries(segments)


# Backward-compatible alias for existing pipeline stages
def transcribe_audio_segments(
    wav_path: str | Path,
    language: str = "nl",
    script_dialogue: list[dict] | None = None,
    force_language: bool = True,
) -> list[dict[str, Any]]:
    """Stage 3a compatibility entrypoint (uses fast alignment engine)."""
    del force_language  # Forced alignment relies solely on the provided script text
    return align_audio_with_script(
        wav_path=wav_path,
        script_dialogue=script_dialogue,
        language=language,
    )


# ==============================================================================
# Subtitle Generation (ASS Karaoke)
# ==============================================================================

def _format_ass_timestamp(seconds: float) -> str:
    """Format float seconds to ASS timestamp format (H:MM:SS.cs)."""
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs >= 100:
        cs = 99
    return f"{hrs}:{mins:02d}:{secs:02d}.{cs:02d}"


def _build_ass_karaoke_text(
    words: list[dict[str, Any]], 
    fallback_text: str, 
    seg_start: float, 
    seg_end: float
) -> str:
    """Build ASS karaoke line with automatic interpolation for missing word timestamps."""
    clean_words = []
    if words:
        for w in words:
            if isinstance(w, dict) and "word" in w:
                clean_words.append({
                    "word": str(w["word"]).strip(),
                    "start": w.get("start"),
                    "end": w.get("end"),
                })

    # If alignment completely dropped word bounds, interpolate across segment duration
    if not clean_words or all(w["start"] is None for w in clean_words):
        fallback_tokens = [t for t in fallback_text.split() if t.strip()]
        if not fallback_tokens:
            return fallback_text

        duration = max(0.1, seg_end - seg_start)
        step_cs = max(1, int(round((duration / len(fallback_tokens)) * 100.0)))
        return " ".join([f"{{\\kf{step_cs}}}{tok}" for tok in fallback_tokens])

    tokens: list[str] = []
    num_words = len(clean_words)

    # Fill in any missing timestamps linearly between valid surrounding bounds
    for i, w in enumerate(clean_words):
        w_start = w["start"]
        w_end = w["end"]

        # Infer missing start
        if w_start is None:
            w_start = seg_start if i == 0 else (clean_words[i - 1]["end"] or seg_start)

        # Infer missing end
        if w_end is None:
            if i < num_words - 1 and clean_words[i + 1]["start"] is not None:
                w_end = clean_words[i + 1]["start"]
            else:
                w_end = seg_end

        # Cap at 1.5 s: Wav2Vec2 absorbs trailing silence into the last word's
        # end timestamp, which would make the highlight sweep far too slowly.
        raw_cs = int(round((float(w_end) - float(w_start)) * 100.0))
        dur_cs = max(1, min(raw_cs, 150))
        tokens.append(f"{{\\kf{dur_cs}}}{w['word']}")

    return " ".join(tokens) if tokens else fallback_text


def _write_ass_karaoke(ass_path: Path, rows: list[tuple[float, float, str]]) -> None:
    """Write standard ASS karaoke file with custom styling header."""
    header = """[Script Info]
Title: Karaoke Subtitles
ScriptType: v4.00+
WrapStyle: 0
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,44,&H00FFFFFF,&H0000FFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,3,0,8,550,240,486,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for start_t, end_t, text in rows:
        start_ts = _format_ass_timestamp(start_t)
        end_ts = _format_ass_timestamp(end_t)
        lines.append(f"Dialogue: 0,{start_ts},{end_ts},Default,,0,0,0,,{text}")

    ass_path.write_text("\n".join(lines), encoding="utf-8")


def _stitch_subtitle_rows(
    rows: list[tuple[float, float, str]],
    min_duration: float = 0.45,
    lead_out_padding: float = 0.0,
) -> list[tuple[float, float, str]]:
    """Keep subtitles visible between turns by bridging to the next turn start."""
    if not rows:
        return []

    stitched: list[tuple[float, float, str]] = []
    for i, (start, end, text) in enumerate(rows):
        new_start = max(0.0, float(start))
        new_end = max(new_start, float(end))

        # Ensure each line is visible long enough, especially short interjections.
        new_end = max(new_end, new_start + min_duration)

        if i < len(rows) - 1:
            next_start = max(new_start, float(rows[i + 1][0]))
            bridged_end = max(new_end, next_start - lead_out_padding)
            # Never cross the next line boundary.
            new_end = min(bridged_end, next_start)

        stitched.append((new_start, max(new_start, new_end), text))

    return stitched


def generate_karaoke_from_segments(
    segments: list[dict[str, Any]],
    output_root: str,
    level: str,
    category: str,
    topic_id: str,
    title_slug: str,
    script_dialogue: list[dict] | None = None,
) -> dict[str, str]:
    """Stage 3c: Write ASS karaoke subtitle file from aligned segments."""
    del script_dialogue  # Kept for API compatibility

    out_dir = Path(output_root) / level / category / "subtitles"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Collect raw segment data
    raw: list[tuple[float, float, str, list[dict[str, Any]]]] = []
    for seg in segments:
        try:
            start = float(seg.get("start", 0.0))
            end = float(seg.get("end", start))
        except (ValueError, TypeError):
            continue
        text = str(seg.get("text", "")).strip()
        if not text:
            continue
        words = [w for w in seg.get("words", []) if isinstance(w, dict)]
        raw.append((start, max(start, end), text, words))

    # Stitch Dialogue End timestamps to next segment start before building kf text.
    # This keeps the subtitle visible during pauses without affecting kf durations.
    timing_rows = [(s, e, "") for s, e, _, _ in raw]
    stitched_timing = _stitch_subtitle_rows(timing_rows)

    rows: list[tuple[float, float, str]] = []
    for i, (start, orig_end, text, words) in enumerate(raw):
        stitched_end = stitched_timing[i][1] if i < len(stitched_timing) else orig_end
        ass_text = _build_ass_karaoke_text(
            words=words,
            fallback_text=text,
            seg_start=start,
            seg_end=orig_end,  # use actual word end for fallback interpolation
        )
        rows.append((start, stitched_end, ass_text))

    stitched_rows = rows

    ass_path = out_dir / f"episode_{topic_id}_{title_slug}.ass"
    _write_ass_karaoke(ass_path, stitched_rows)

    return {
        "ass_karaoke": str(ass_path),
    }


def generate_karaoke_from_audio(
    wav_path: str | Path,
    output_root: str,
    level: str,
    category: str,
    topic_id: str,
    title_slug: str,
    language: str = "nl",
    script_dialogue: list[dict] | None = None,
) -> dict[str, str]:
    """Legacy entrypoint combining forced alignment and ASS karaoke generation."""
    segments = align_audio_with_script(
        wav_path=wav_path,
        script_dialogue=script_dialogue,
        language=language,
    )
    return generate_karaoke_from_segments(
        segments=segments,
        output_root=output_root,
        level=level,
        category=category,
        topic_id=topic_id,
        title_slug=title_slug,
        script_dialogue=script_dialogue,
    )


def plan_subtitles(
    wav_path: str,
    output_root: str,
    level: str,
    category: str,
    topic_id: str,
    title_slug: str,
    language: str = "nl",
    script_dialogue: list[dict] | None = None,
) -> dict[str, Any]:
    """Main pipeline execution function."""
    subtitle_files = generate_karaoke_from_audio(
        wav_path=wav_path,
        output_root=output_root,
        level=level,
        category=category,
        topic_id=topic_id,
        title_slug=title_slug,
        language=language,
        script_dialogue=script_dialogue,
    )
    return {
        "karaoke_file": subtitle_files.get("ass_karaoke", ""),
        "srt_files": subtitle_files,
    }


# ==============================================================================
# Direct Script Execution Example
# ==============================================================================

if __name__ == "__main__":
    import json

    # Test payload containing isolated Dutch words and pauses
    sample_dialogue = [
        {"Speaker1": "Hello everyone! Welcome to today's Dutch lesson."},
        {"Speaker1": "[pause for 1 second] [slow] [excited] Laten we beginnen!"},
        {"Speaker1": "Our first word is IK."},
        {"Speaker1": "[pause for 1 second] [slow] Ik."},
        {"Speaker1": "[pause for 1 second] [slow] Ik ben Jan."},
    ]

    sample_audio_path = "sample_audio.wav"

    if Path(sample_audio_path).exists():
        print("Running fast forced alignment pipeline...")
        results = plan_subtitles(
            wav_path=sample_audio_path,
            output_root="output",
            level="A1",
            category="grammar",
            topic_id="cw_pronouns",
            title_slug="personal_pronouns",
            language="nl",
            script_dialogue=sample_dialogue,
        )
        print(f"Generated subtitles:\n{json.dumps(results, indent=2)}")