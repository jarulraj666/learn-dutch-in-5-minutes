from __future__ import annotations

from collections import namedtuple
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from pipeline.utils import srt_timestamp

# Lightweight bridge so _build_multiline_karaoke can work with dict-like word timing output
_Word = namedtuple("_Word", ["word", "start", "end"])

WHISPER_MODEL_NAME = "large-v3"
TRANSCRIBE_BATCH_SIZE = 16
TRANSCRIBE_CHUNK_SIZE = 5
SCRIPT_PROMPT_MAX_CHARS = 1200
ALIGN_LANGUAGE_CODES = ("nl", "en")
NL_HINT_WORDS = {
    "ik", "jij", "hij", "zij", "wij", "jullie", "en", "het", "een", "naar",
    "koffie", "nederlands", "leert", "leren", "praat", "praten", "loopt", "lopen",
    "drinkt", "drink", "ben", "bent", "is", "zijn",
}
EN_HINT_WORDS = {
    "the", "and", "you", "we", "they", "he", "she", "are", "is", "to",
    "in", "with", "means", "learn", "today", "next", "word", "plural",
}


def _fallback_words_for_segment(text: str, start: float, end: float) -> list[Any]:
    """Build coarse word timings from segment bounds when model has no word timings."""
    words = [w for w in text.split() if w.strip()]
    if not words:
        return []
    if end <= start:
        end = start + 0.05 * len(words)

    step = (end - start) / len(words)
    out: list[Any] = []
    for i, token in enumerate(words):
        w_start = start + i * step
        w_end = start + (i + 1) * step
        out.append(_Word(token, w_start, w_end))
    return out


def _prepare_whisperx_runtime() -> None:
    """Register safe globals and patch cloud checkpoint loading for WhisperX."""
    import inspect
    import torch
    import omegaconf
    import omegaconf.base
    import omegaconf.nodes

    # WhisperX/Pyannote checkpoints may carry OmegaConf classes.
    safe_globals = [
        cls for _, cls in inspect.getmembers(omegaconf, inspect.isclass)
    ] + [
        cls for _, cls in inspect.getmembers(omegaconf.base, inspect.isclass)
    ] + [
        cls for _, cls in inspect.getmembers(omegaconf.nodes, inspect.isclass)
    ]
    torch.serialization.add_safe_globals(safe_globals)

    # Local trusted checkpoint files may need weights_only=False.
    try:
        import lightning_fabric.utilities.cloud_io as _cloud_io

        original_load = _cloud_io._load

        def _patched_load(path_or_url, map_location=None, weights_only=None):
            if weights_only is None and not str(path_or_url).startswith("http"):
                weights_only = False
            return original_load(path_or_url, map_location=map_location, weights_only=weights_only)

        _cloud_io._load = _patched_load
    except Exception:
        pass


def _line_lang_score(line: str) -> tuple[int, int]:
    """Return a rough Dutch/English lexical hit score for a line."""
    import re

    tokens = re.findall(r"[a-zA-Z']+", line.lower())
    nl = sum(1 for token in tokens if token in NL_HINT_WORDS)
    en = sum(1 for token in tokens if token in EN_HINT_WORDS)
    return nl, en


def _build_script_prompt(
    script_dialogue: list[dict] | None,
    language: str,
    force_language: bool,
) -> str:
    """Build and print the cleaned script prompt passed to WhisperX."""
    script_lines = _script_lines_without_tags(script_dialogue)

    # For forced Dutch runs, keep Dutch-leaning lines to reduce English prompt bias.
    if force_language and language.lower().startswith("nl"):
        dutch_lines: list[str] = []
        for line in script_lines:
            nl_score, en_score = _line_lang_score(line)
            if nl_score > 0 and nl_score >= en_score:
                dutch_lines.append(line)
        if dutch_lines:
            script_lines = dutch_lines

    formatted_script = "\n".join(script_lines)

    if formatted_script:
        print("=== FORMATTED SCRIPT SENT TO WHISPERX ===")
        print(formatted_script)
        print("=== END FORMATTED SCRIPT ===")

    return formatted_script[:SCRIPT_PROMPT_MAX_CHARS]


def _load_align_models(whisperx: Any, device: str) -> dict[str, tuple[Any, Any]]:
    """Load available alignment models for supported language codes."""
    models: dict[str, tuple[Any, Any]] = {}
    for lang in ALIGN_LANGUAGE_CODES:
        try:
            model, metadata = whisperx.load_align_model(language_code=lang, device=device)
            models[lang] = (model, metadata)
        except Exception:
            pass
    return models


def _align_segments(
    whisperx: Any,
    segments_in: list[dict[str, Any]],
    align_models: dict[str, tuple[Any, Any]],
    audio: Any,
    device: str,
) -> list[dict[str, Any]]:
    """Align segments by detected language with safe fallbacks."""

    def _lang_key(seg: dict[str, Any]) -> str:
        raw = str(seg.get("language", ""))
        code = (raw or "nl")[:2].lower()
        return code if code in align_models else next(iter(align_models), "nl")

    from itertools import groupby

    aligned: list[dict[str, Any]] = []
    for lang, group in groupby(segments_in, key=_lang_key):
        group_segments = list(group)
        if lang not in align_models:
            aligned.extend(group_segments)
            continue

        model, metadata = align_models[lang]
        try:
            group_result = whisperx.align(
                group_segments,
                model,
                metadata,
                audio,
                device,
                return_char_alignments=False,
            )
            aligned.extend(group_result.get("segments", group_segments))
        except Exception:
            aligned.extend(group_segments)

    aligned.sort(key=lambda s: s.get("start", 0.0))
    return aligned


def _normalize_segments(aligned_segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize aligned segments into a stable shape consumed downstream."""
    normalized: list[dict[str, Any]] = []
    for seg in aligned_segments:
        text = str(seg.get("text", "")).strip()
        if not text:
            continue

        try:
            start = float(seg.get("start", 0.0))
            end = float(seg.get("end", start))
        except Exception:
            continue

        words: list[dict[str, Any]] = []
        for word_item in seg.get("words", []):
            if isinstance(word_item, dict) and "word" in word_item:
                word_start = float(word_item.get("start", start))
                word_end = float(word_item.get("end", word_start))
                words.append({"word": word_item["word"], "start": word_start, "end": word_end})

        normalized.append(
            {
                "start": max(0.0, start),
                "end": max(start, end),
                "text": text,
                "words": words,
            }
        )
    return normalized


def _normalize_match_text(text: str) -> str:
    """Normalize text for fuzzy matching between STT and script lines."""
    import re

    lowered = text.lower().strip()
    lowered = re.sub(r"[^a-z0-9\s']+", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered


def _match_score(a: str, b: str) -> float:
    """Similarity score in [0, 1] for two strings."""
    na = _normalize_match_text(a)
    nb = _normalize_match_text(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def _rewrite_segment_words_from_text(
    seg: dict[str, Any],
    new_text: str,
) -> dict[str, Any]:
    """Rebuild coarse word timings when transcript text is corrected."""
    start = float(seg.get("start", 0.0))
    end = float(seg.get("end", start))
    fallback_words = _fallback_words_for_segment(new_text, start, end)
    words = [{"word": w.word, "start": w.start, "end": w.end} for w in fallback_words]

    out = dict(seg)
    out["text"] = new_text
    out["words"] = words
    return out


def _reconcile_segments_with_script(
    segments: list[dict[str, Any]],
    script_dialogue: list[dict] | None,
) -> list[dict[str, Any]]:
    """Compare STT vs script and correct low-quality STT text using script lines.

    Uses monotonic fuzzy matching and supports occasional STT merges of 2 script lines.
    """
    script_lines = _script_lines_without_tags(script_dialogue)
    if not script_lines or not segments:
        return segments

    corrected: list[dict[str, Any]] = []
    script_idx = 0

    for seg in segments:
        stt_text = str(seg.get("text", "")).strip()
        if not stt_text or script_idx >= len(script_lines):
            corrected.append(seg)
            continue

        # Only search nearby script lines to preserve ordering.
        window = script_lines[script_idx : min(len(script_lines), script_idx + 4)]
        if not window:
            corrected.append(seg)
            continue

        best_single_score = -1.0
        best_single_offset = 0
        for off, line in enumerate(window):
            score = _match_score(stt_text, line)
            if score > best_single_score:
                best_single_score = score
                best_single_offset = off

        best_text = window[best_single_offset]
        best_advance = best_single_offset + 1
        best_score = best_single_score

        # Try a merged candidate of 2 script lines in case STT merged adjacent lines.
        if best_single_offset + 1 < len(window):
            merged = f"{window[best_single_offset]} {window[best_single_offset + 1]}"
            merged_score = _match_score(stt_text, merged)
            if merged_score >= best_single_score + 0.10 and merged_score >= 0.45:
                best_text = merged
                best_advance = best_single_offset + 2
                best_score = merged_score

        # Replace text when STT is clearly weak, or when script match is clearly better.
        if best_score >= 0.45 or (best_score >= 0.30 and len(stt_text.split()) <= 4):
            corrected.append(_rewrite_segment_words_from_text(seg, best_text))
            script_idx += best_advance
        else:
            corrected.append(seg)
            # Mild forward progress to avoid repeatedly comparing against stale script line.
            script_idx += 1

    return corrected


def _transcribe_with_whisperx(
    wav_path: Path,
    language: str,
    script_dialogue: list[dict] | None = None,
    force_language: bool = True,
) -> list[dict[str, Any]]:
    """Transcribe bilingual (Dutch + English) audio via WhisperX (large-v3 model).

    Does NOT translate. Transcribes exactly what is spoken in each segment,
    preserving code-switching between Dutch and English as-is.
    Uses per-segment language detection so both languages are handled correctly.
    Word-level timestamps are aligned using language-specific alignment models.
    """
    import torch
    import whisperx

    _prepare_whisperx_runtime()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    script_prompt = _build_script_prompt(script_dialogue, language, force_language)

    whisper_language = language if force_language and language else None

    # Load model for transcription.
    # vad_options tightens the silence threshold so short inter-sentence pauses
    # are treated as segment boundaries.
    asr_options: dict[str, Any] = {
        "initial_prompt": script_prompt,
    } if script_prompt else {}
    if force_language and whisper_language and whisper_language.lower().startswith("nl"):
        # Lower temperature and stronger beam search reduce Dutch phonetic drift.
        asr_options.update({
            "beam_size": 8,
            "best_of": 8,
            "temperatures": [0.0],
            "condition_on_previous_text": False,
        })

    model = whisperx.load_model(
        WHISPER_MODEL_NAME,
        device=device,
        compute_type=compute_type,
        language=whisper_language,
        task="transcribe",
        asr_options=asr_options or None,
        vad_options={"min_silence_duration_ms": 300},
    )
    audio = whisperx.load_audio(str(wav_path))

    # Transcribe first, then align in a separate step below.
    # chunk_size=5 helps keep adjacent short lines from merging.
    result = model.transcribe(
        audio,
        batch_size=TRANSCRIBE_BATCH_SIZE,
        chunk_size=TRANSCRIBE_CHUNK_SIZE,
        language=whisper_language,
    )
    align_models = _load_align_models(whisperx, device)
    segments_in = result.get("segments", [])
    aligned_segments = _align_segments(whisperx, segments_in, align_models, audio, device)
    normalized = _normalize_segments(aligned_segments)
    normalized = _reconcile_segments_with_script(normalized, script_dialogue)

    if not normalized:
        raise RuntimeError("WhisperX returned no usable transcript segments.")
    return normalized


def transcribe_audio_segments(
    wav_path: str | Path,
    language: str = "nl",
    script_dialogue: list[dict] | None = None,
    force_language: bool = True,
) -> list[dict[str, Any]]:
    """Stage 3a: speech-to-text using WhisperX (large-v3 model).

    Returns normalized transcript segments with per-word timing.
    """
    path = Path(wav_path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {path}")

    return _transcribe_with_whisperx(
        path,
        language,
        script_dialogue=script_dialogue,
        force_language=force_language,
    )


def _format_ass_timestamp(seconds: float) -> str:
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs >= 100:
        cs = 99
    return f"{hrs}:{mins:02d}:{secs:02d}.{cs:02d}"


def _write_ass_karaoke(
    ass_path: Path, karaoke_rows: list[tuple[float, float, str]]
) -> None:
    header = """[Script Info]
Title: Karaoke Subtitles - Center Aligned with Rounded Box
ScriptType: v4.00+
WrapStyle: 0
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Helvetica Neue,48,&H00FFFFFF,&H0000FFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,3,3,1,5,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for start_t, end_t, text in karaoke_rows:
        start_ts = _format_ass_timestamp(start_t)
        end_ts = _format_ass_timestamp(end_t)
        lines.append(f"Dialogue: 0,{start_ts},{end_ts},Default,,0,0,0,,{text}")

    ass_path.write_text("\n".join(lines), encoding="utf-8")


def _write_srt(
    srt_path: Path,
    rows: list[tuple[float, float, str]],
) -> None:
    """Write a standard SRT subtitle file."""
    entries: list[str] = []
    for i, (start_t, end_t, text) in enumerate(rows, 1):
        start_ts = srt_timestamp(start_t)
        end_ts = srt_timestamp(end_t)
        entries.append(f"{i}\n{start_ts} --> {end_ts}\n{text}")
    srt_path.write_text("\n\n".join(entries) + "\n", encoding="utf-8")


def _split_into_chunks(words: list[Any], max_words: int = 5) -> list[list[Any]]:
    """Split a word list into chunks of max_words per chunk."""
    chunks = []
    for i in range(0, len(words), max_words):
        chunks.append(words[i : i + max_words])
    return chunks


# Inline ASS override tags: position (right of center, below center), opaque black box, white base text, yellow karaoke highlight
# \pos(1050,620): 90px right of center (960), 80px below center (540) on 1920x1080
_ASS_INLINE_TAGS = r"{\pos(1150,680)\3a&H00&\4c&H00000000&\1c&H00FFFFFF&\2c&H0000FFFF&}"


def _build_multiline_karaoke(
    words: list[Any],
    segment_start: float | None = None,
    segment_end: float | None = None,
    max_words_per_line: int = 5,
) -> str:
    """Build karaoke text with max N words per line, center-aligned.

    Uses inline ASS override tags for: opaque black background box,
    white base text, yellow karaoke highlight sweep.

    Args:
        words: List of word objects with .word, .start, .end attributes
        max_words_per_line: Maximum words per subtitle line (default: 5)

    Returns:
        Formatted karaoke text with inline tags and newlines for multi-line display
    """
    # Build raw intervals from word boundaries so karaoke transitions follow
    # the transcribed timing stream (word-start to next-word-start, last to segment end).
    raw_cs: list[float] = []
    for i, w in enumerate(words):
        if i + 1 < len(words):
            duration_seconds = words[i + 1].start - w.start
        elif segment_end is not None:
            duration_seconds = segment_end - w.start
        else:
            duration_seconds = w.end - w.start
        raw_cs.append(max(0.0, duration_seconds * 100.0))

    # Sanitize corrupted STT word timings: when a single word consumes more than
    # 60% of the segment duration (Gemini hallucination artifact), fall back to
    # equal-time distribution so all words get proportional karaoke duration.
    if raw_cs:
        total_raw = sum(raw_cs)
        n_words = len(raw_cs)
        if total_raw > 0 and max(raw_cs) / total_raw > 0.60 and n_words > 1:
            equal = total_raw / n_words
            raw_cs = [equal] * n_words

    if segment_start is None:
        segment_start = float(words[0].start)
    if segment_end is None:
        segment_end = float(words[-1].end)

    total_event_cs = max(1, int(round((segment_end - segment_start) * 100.0)))

    # Quantize to integer centiseconds while preserving exact event duration.
    # Keep relative word-speed variation from raw timings (fast words stay fast).
    n = len(words)
    if total_event_cs >= n:
        base_cs = [1] * n
        remaining = total_event_cs - n
        weight_sum = sum(raw_cs)

        if remaining > 0:
            if weight_sum <= 0.0:
                # No usable timing info: spread remaining time evenly.
                for i in range(remaining):
                    base_cs[i % n] += 1
            else:
                scaled = [(remaining * w) / weight_sum for w in raw_cs]
                add_floor = [int(v) for v in scaled]
                used = sum(add_floor)
                for i, v in enumerate(add_floor):
                    base_cs[i] += v

                rem = remaining - used
                if rem > 0:
                    frac_idx = sorted(
                        range(n),
                        key=lambda i: (scaled[i] - int(scaled[i])),
                        reverse=True,
                    )
                    for i in range(rem):
                        base_cs[frac_idx[i % n]] += 1
    else:
        # Extremely short event: keep earliest words visible first.
        base_cs = [1 if i < total_event_cs else 0 for i in range(n)]

    timed_tokens: list[str] = [
        f"{{\\kf{dur_cs}}}{w.word.strip()}"
        for w, dur_cs in zip(words, base_cs)
    ]

    lines: list[str] = []
    for i in range(0, len(timed_tokens), max_words_per_line):
        lines.append(" ".join(timed_tokens[i : i + max_words_per_line]))

    # Prepend inline tags once; they apply to all following text in the event
    multiline_text = _ASS_INLINE_TAGS + "\\N".join(lines)

    return multiline_text


def _strip_tts_tags(text: str) -> str:
    """Remove TTS control tags like [pause for 1 second], [slow], [excited] from a line."""
    import re
    return re.sub(r"\[.*?\]", "", text).strip()


def _script_lines_without_tags(script_dialogue: list[dict] | None) -> list[str]:
    """Normalize script dialogue into plain subtitle lines.

    Uses only the line field from each dialogue item and removes bracketed tags.
    """
    if not script_dialogue:
        return []

    cleaned: list[str] = []
    for item in script_dialogue:
        if not isinstance(item, dict):
            continue
        line = _strip_tts_tags(str(item.get("line", "")))
        if not line:
            continue
        cleaned.append(line)

    return cleaned


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
    """Legacy combined entrypoint (STT + karaoke build)."""
    segments = transcribe_audio_segments(
        wav_path=wav_path,
        language=language,
        script_dialogue=script_dialogue,
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


def generate_karaoke_from_segments(
    segments: list[dict[str, Any]],
    output_root: str,
    level: str,
    category: str,
    topic_id: str,
    title_slug: str,
    script_dialogue: list[dict] | None = None,
) -> dict[str, str]:
    """Stage 3c: build ASS/SRT from precomputed transcript segments."""
    out_dir = Path(output_root) / level / category / "subtitles"
    out_dir.mkdir(parents=True, exist_ok=True)

    karaoke_rows_ass: list[tuple[float, float, str]] = []
    script_lines = _script_lines_without_tags(script_dialogue)

    for idx, seg in enumerate(segments):
        stt_text = _strip_tts_tags(str(seg.get("text", "")).strip())
        seg_text = script_lines[idx] if idx < len(script_lines) else stt_text
        raw_words = seg.get("words", [])
        # Prefer model word timings when provided.
        valid_words = [
            _Word(w["word"], w["start"], w["end"])
            for w in raw_words
            if isinstance(w, dict) and "word" in w and "start" in w and "end" in w
        ]
        if not valid_words:
            seg_start_raw = seg.get("start")
            seg_end_raw = seg.get("end")
            if seg_start_raw is not None and seg_end_raw is not None:
                valid_words = _fallback_words_for_segment(
                    seg_text,
                    float(seg_start_raw),
                    float(seg_end_raw),
                )
        if valid_words:
            # Keep cue window aligned with karaoke word timings; this prevents
            # the highlight from finishing too early inside a longer segment.
            seg_start = float(valid_words[0].start)
            seg_end = float(valid_words[-1].end)
            if seg_end <= seg_start:
                seg_start = float(seg.get("start", seg_start))
                seg_end = float(seg.get("end", max(seg_start + 0.1, seg_end)))
            ass_karaoke_text = _build_multiline_karaoke(
                valid_words,
                segment_start=seg_start,
                segment_end=seg_end,
                max_words_per_line=5,
            )
            karaoke_rows_ass.append((seg_start, seg_end, ass_karaoke_text))

    ass_path = out_dir / f"episode_{topic_id}_{title_slug}.ass"
    _write_ass_karaoke(ass_path, karaoke_rows_ass)

    return {
        "ass_karaoke": str(ass_path),
    }


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
    """Generate subtitles and save to output/{level}/{category}/subtitles/."""
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