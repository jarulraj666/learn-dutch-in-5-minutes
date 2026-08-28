from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import torch
import whisperx
from pipeline import settings
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
    """Enforce monotonic, non-overlapping segment boundaries.

    Also caps each segment's duration so WhisperX silence absorption
    (e.g. at TTS chunk boundaries) cannot stretch a line to unrealistic lengths.
    Max duration is generous: 1.8 seconds per word, minimum 1.5 s per segment.
    """
    MAX_SECONDS_PER_WORD = 1.8
    MIN_DURATION = 1.5

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

        # Cap duration: never longer than word_count × MAX_SECONDS_PER_WORD
        text = seg.get("text", "")
        word_count = max(1, len(text.split()))
        max_duration = max(MIN_DURATION, word_count * MAX_SECONDS_PER_WORD)
        end = min(end, start + max_duration)
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


def _assign_speaker_by_timestamp(
    original_speaker: str,
    segment_midpoint: float,
    speaker_timestamps: list,
) -> str:
    """Assign a speaker to a segment based on its midpoint time.
    
    Checks which speaker timestamp range contains the segment midpoint.
    Falls back to original_speaker if no match found.
    
    Args:
        original_speaker: Original speaker from script.
        segment_midpoint: Time in seconds (midpoint of the segment).
        speaker_timestamps: List of SpeakerTimestamp objects.
    
    Returns:
        Speaker ID from timestamps if match found, else original_speaker.
    """
    if not speaker_timestamps:
        return original_speaker
    
    for ts in speaker_timestamps:
        if ts.start_time <= segment_midpoint < ts.end_time:
            return ts.speaker_id
    
    return original_speaker

def align_audio_with_script(
    wav_path: str | Path,
    script_dialogue: list[dict] | None = None,
    language: str = "nl",
    speaker_timestamps: list["settings.SpeakerTimestamp"] | None = None,
    category: str = "dialogue",
) -> list[dict[str, Any]]:
    """Forced alignment using Wav2Vec2.

    Feeds the full script text as a single segment spanning the entire audio so
    that Wav2Vec2 CTC alignment can freely locate each word without pre-set time
    windows.  The resulting per-word timestamps are accumulated back into one
    segment per script line, giving accurate start / end times.
    
    For dialogue category, optionally uses speaker_timestamps to refine speaker assignment.
    
    Args:
        wav_path: Path to audio file.
        script_dialogue: Dialogue script.
        language: Language code (e.g., 'nl').
        speaker_timestamps: Optional list of speaker timestamps for dialogue refinement.
        category: Episode category ('dialogue' or other).
    
    Returns:
        List of aligned segment dicts with speaker information.
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

        # For dialogue category, optionally refine speaker using timestamps
        refined_speaker = speaker
        if category == "dialogue" and speaker_timestamps:
            mid_time = (line_start + line_end) / 2.0
            refined_speaker = _assign_speaker_by_timestamp(speaker, mid_time, speaker_timestamps)

        segments.append({
            "start":   max(0.0, line_start),
            "end":     max(line_start, line_end),
            "text":    line_text,
            "words":   line_words,
            "speaker": refined_speaker,
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
    accumulated_cs = 0  # track total karaoke time used so far
    line_duration_cs = max(1, int(round((seg_end - seg_start) * 100.0)))

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

        # Use WhisperX's exact word timestamps as-is — no artificial caps or
        # heuristic guesses. Only guard against zero/negative rounding and
        # against cumulative rounding drift pushing the total past the line's
        # actual duration.
        raw_cs = int(round((float(w_end) - float(w_start)) * 100.0))
        dur_cs = max(1, raw_cs)

        remaining_cs = line_duration_cs - accumulated_cs
        if i == num_words - 1:
            dur_cs = max(1, min(dur_cs, remaining_cs))
        else:
            dur_cs = min(dur_cs, max(1, remaining_cs - (num_words - i - 1)))

        accumulated_cs += dur_cs
        tokens.append(f"{{\\kf{dur_cs}}}{w['word']}")

    if not tokens:
        return fallback_text

    # Wrap at 5 words per line using ASS hard line-break (\N)
    max_words_per_line = 5
    chunks = [tokens[i : i + max_words_per_line] for i in range(0, len(tokens), max_words_per_line)]
    return "\\N".join(" ".join(chunk) for chunk in chunks)


def _format_srt_timestamp(seconds: float) -> str:
    """Format float seconds to SRT timestamp format (HH:MM:SS,mmm)."""
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    if ms >= 1000:
        ms = 999
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{ms:03d}"


def _write_srt(
    srt_path: Path,
    rows: list[tuple[float, float, str, str | None]],
    dialogue_en: list[dict] | None = None,
) -> None:
    """Write English SRT subtitle file using timing from aligned rows.

    Maps English translations from dialogue_en by index to the Dutch timing.
    Falls back to Dutch text if no English translation available.
    """
    en_lines: list[str] = []
    if dialogue_en:
        for turn in dialogue_en:
            if isinstance(turn, dict):
                for text in turn.values():
                    en_lines.append(_strip_tts_tags(str(text).strip()))

    entries: list[str] = []
    for i, (start_t, end_t, dutch_text, _) in enumerate(rows):
        en_text = en_lines[i] if i < len(en_lines) else ""
        if not en_text:
            # Empty means the dialogue line was already English — strip ASS karaoke
            # tags from the Dutch text field to recover readable plain text.
            en_text = re.sub(r"\{[^}]*\}", "", dutch_text).replace("\\N", " ").strip()
        if not en_text:
            continue
        start_ts = _format_srt_timestamp(start_t)
        end_ts = _format_srt_timestamp(end_t)
        entries.append(f"{i + 1}\n{start_ts} --> {end_ts}\n{en_text}\n")

    srt_path.write_text("\n".join(entries), encoding="utf-8")


def _write_ass_karaoke(
    ass_path: Path,
    rows: list[tuple[float, float, str, str | None]],
    category: str = "dialogue",
) -> None:
    """Write ASS karaoke file with category-aware styling.
    
    For dialogue category: Creates two styles (SpeakerL, SpeakerR) for left/right positioning.
    For other categories: Uses single Default style (center-aligned, backward compatible).
    
    Args:
        ass_path: Output ASS file path.
        rows: List of (start_time, end_time, text, speaker_id) tuples.
        category: Episode category ('dialogue' or other).
    """
    # Load margin config
    visual_config = settings.load_yaml(settings.ROOT / "config/visual_style.yaml")
    margins = visual_config.get("render", {}).get("subtitle_margins", {})
    single = visual_config.get("render", {}).get("single_speaker_margins", {})
    dialogue_align = visual_config.get("render", {}).get("dialogue_alignment", {})

    # Get margin values with fallbacks
    left_l = margins.get("left_speaker_margin_l", 20)
    left_r = margins.get("left_speaker_margin_r", 800)
    right_l = margins.get("right_speaker_margin_l", 800)
    right_r = margins.get("right_speaker_margin_r", 20)
    margin_v = margins.get("margin_v", 486)

    # Dialogue alignment (multi-speaker)
    left_align = dialogue_align.get("left_speaker", 1)
    right_align = dialogue_align.get("right_speaker", 3)

    # Single-speaker margin values with fallbacks
    ss_margin_l = single.get("margin_l", 650)
    ss_margin_r = single.get("margin_r", 240)
    ss_margin_v = single.get("margin_v", 486)
    ss_alignment = single.get("alignment", 8)
    
    # Build header based on category
    if category == "dialogue":
        # Multi-speaker dialogue: two styles (left/right positioning)
        header = f"""[Script Info]
Title: Karaoke Subtitles
ScriptType: v4.00+
WrapStyle: 0
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: SpeakerL,Roboto,64,&H00FFFFFF,&H0000FFFF,&H00000000,&HC0000000,-1,0,0,0,100,100,0,0,3,5,0,{left_align},{left_l},{left_r},{margin_v},1
Style: SpeakerR,Roboto,64,&H00FFFFFF,&H0000FFFF,&H00000000,&HC0000000,-1,0,0,0,100,100,0,0,3,5,0,{right_align},{right_l},{right_r},{margin_v},1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    else:
        # Single-speaker (non-dialogue): center-aligned (backward compatible)
        header = f"""[Script Info]
Title: Karaoke Subtitles
ScriptType: v4.00+
WrapStyle: 0
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Roboto,58,&H00FFFFFF,&H0000FFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,3,0,{ss_alignment},{ss_margin_l},{ss_margin_r},{ss_margin_v},1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    lines = [header]
    for start_t, end_t, text, speaker in rows:
        start_ts = _format_ass_timestamp(start_t)
        end_ts = _format_ass_timestamp(end_t)
        
        # Determine style based on category and speaker
        if category == "dialogue" and speaker:
            style = "SpeakerL" if speaker == "Speaker1" else "SpeakerR"
        else:
            style = "Default"
        lines.append(f"Dialogue: 0,{start_ts},{end_ts},{style},,0,0,0,,{text}")

    ass_path.write_text("\n".join(lines), encoding="utf-8")


def _stitch_subtitle_rows(
    rows: list[tuple[float, float, str, str | None] | tuple[float, float, str]],
    min_duration: float = 0.45,
    lead_out_padding: float = 0.0,
    inter_line_gap: float = 0.08,
    max_bridge_gap: float = 3.0,
) -> list[tuple[float, float, str, str | None]]:
    """Return subtitle rows with no bridging — subtitle disappears when speech ends.
    
    Handles both 3-tuples (start, end, text) and 4-tuples (start, end, text, speaker).
    """
    if not rows:
        return []

    stitched: list[tuple[float, float, str, str | None]] = []
    for row in rows:
        if len(row) == 4:
            start, end, text, speaker = row
        else:
            start, end, text = row
            speaker = None
        
        new_start = max(0.0, float(start))
        new_end = max(new_start, float(end))
        new_end = max(new_end, new_start + min_duration)
        stitched.append((new_start, new_end, text, speaker))

    return stitched


def generate_karaoke_from_segments(
    segments: list[dict[str, Any]],
    output_root: str,
    level: str,
    category: str,
    topic_id: str,
    title_slug: str,
    script_dialogue: list[dict] | None = None,
    dialogue_en: list[dict] | None = None,
) -> dict[str, str]:
    """Stage 3c: Write ASS karaoke subtitle file from aligned segments.

    Also writes an English SRT file if dialogue_en translations are provided.
    """
    del script_dialogue  # Kept for API compatibility

    out_dir = Path(output_root) / "subtitles" / f"episode_{topic_id}_{title_slug}"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Collect raw segment data with speaker info
    raw: list[tuple[float, float, str, list[dict[str, Any]], str | None]] = []
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
        speaker = seg.get("speaker")  # Extract speaker for dialogue
        raw.append((start, max(start, end), text, words, speaker))

    # Stitch Dialogue End timestamps to next segment start before building kf text.
    # This keeps the subtitle visible during pauses without affecting kf durations.
    timing_rows = [(s, e, "", sp) for s, e, _, _, sp in raw]
    stitched_timing = _stitch_subtitle_rows(timing_rows)

    rows: list[tuple[float, float, str, str | None]] = []
    for i, (start, orig_end, text, words, speaker) in enumerate(raw):
        stitched_end = stitched_timing[i][1] if i < len(stitched_timing) else orig_end
        ass_text = _build_ass_karaoke_text(
            words=words,
            fallback_text=text,
            seg_start=start,
            seg_end=orig_end,  # use actual word end for fallback interpolation
        )
        rows.append((start, stitched_end, ass_text, speaker))

    stitched_rows = rows

    ass_path = out_dir / f"episode_{topic_id}_{title_slug}.ass"
    _write_ass_karaoke(ass_path, stitched_rows, category=category)

    result: dict[str, str] = {"ass_karaoke": str(ass_path)}

    # Dutch SRT: use plain segment text (before karaoke tag injection) for clean timing lookup
    dutch_rows: list[tuple[float, float, str, str | None]] = [
        (start, stitched_timing[i][1] if i < len(stitched_timing) else orig_end, text, speaker)
        for i, (start, orig_end, text, words, speaker) in enumerate(raw)
    ]
    srt_nl_path = out_dir / f"episode_{topic_id}_{title_slug}_nl.srt"
    _write_srt(srt_nl_path, dutch_rows, dialogue_en=None)
    result["nl"] = str(srt_nl_path)

    srt_en_path = out_dir / f"episode_{topic_id}_{title_slug}_en.srt"
    _write_srt(srt_en_path, stitched_rows, dialogue_en=dialogue_en)
    result["en"] = str(srt_en_path)

    return result


def generate_karaoke_from_audio(
    wav_path: str | Path,
    output_root: str,
    level: str,
    category: str,
    topic_id: str,
    title_slug: str,
    language: str = "nl",
    script_dialogue: list[dict] | None = None,
    dialogue_en: list[dict] | None = None,
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
        dialogue_en=dialogue_en,
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
    dialogue_en: list[dict] | None = None,
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
        dialogue_en=dialogue_en,
    )
    return {
        "karaoke_file": subtitle_files.get("ass_karaoke", ""),
        "srt_nl": subtitle_files.get("nl", ""),
        "srt_en": subtitle_files.get("en", ""),
        "srt_files": subtitle_files,
        "nl": subtitle_files.get("nl", ""),
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
            level="A1A2",
            category="grammar",
            topic_id="cw_pronouns",
            title_slug="personal_pronouns",
            language="nl",
            script_dialogue=sample_dialogue,
        )
        print(f"Generated subtitles:\n{json.dumps(results, indent=2)}")