"""Audio QA Module.

Validates that a generated WAV file contains all expected script sentences.
Compares WhisperX transcription against the script dialogue using fuzzy matching
and reports missing, extra, truncated, and out-of-order sentences with timestamps.
"""

from __future__ import annotations

import difflib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

# Fuzzy-match thresholds
_FOUND_THRESHOLD = 0.80      # ratio >= this → sentence found correctly
_TRUNCATED_THRESHOLD = 0.45  # ratio in [this, FOUND) → sentence partially spoken


# ── Data Types ────────────────────────────────────────────────────────────────


@dataclass
class QAIssue:
    issue_type: str          # MISSING | EXTRA | TRUNCATED | WRONG_ORDER
    sentence_idx: int        # 0-based index in script (or -1 for EXTRA)
    script_text: str         # expected text from script
    transcript_text: str     # best matching text found in transcript (or "" if EXTRA)
    start_ts: float          # timestamp in seconds (-1.0 if unknown)
    end_ts: float            # timestamp in seconds (-1.0 if unknown)
    similarity: float        # fuzzy similarity ratio (0–1)


@dataclass
class QAReport:
    total_script_sentences: int = 0
    total_transcript_segments: int = 0
    issues: list[QAIssue] = field(default_factory=list)

    @property
    def found_count(self) -> int:
        types_with_issues = {i.sentence_idx for i in self.issues if i.issue_type != "WRONG_ORDER"}
        return self.total_script_sentences - len(
            {i.sentence_idx for i in self.issues if i.issue_type in ("MISSING", "TRUNCATED")}
        )

    @property
    def passed(self) -> bool:
        return all(i.issue_type == "WRONG_ORDER" for i in self.issues) if self.issues else True


# ── Text Normalisation ─────────────────────────────────────────────────────────


# Strip TTS pacing directives like [slow], [pause for 1 second], etc.
_PACING_RE = re.compile(r"\[.*?\]")
# Remove punctuation except apostrophes and hyphens inside words
_PUNCT_RE = re.compile(r"[^\w\s'\-]", re.UNICODE)


def _normalise(text: str) -> str:
    """Lower-case, strip pacing markers and punctuation."""
    text = _PACING_RE.sub("", text)
    text = _PUNCT_RE.sub("", text)
    return " ".join(text.lower().split())


def _extract_script_sentences(dialogue: list[dict[str, str]]) -> list[str]:
    """Return flat list of normalised sentence texts from dialogue dicts."""
    sentences: list[str] = []
    for turn in dialogue:
        for text in turn.values():
            normalised = _normalise(text)
            if normalised:
                sentences.append(normalised)
    return sentences


# ── Matching Helpers ───────────────────────────────────────────────────────────


def _best_match(
    needle: str,
    segments: list[dict[str, Any]],
    exclude_indices: set[int] | None = None,
    min_idx: int = 0,
) -> tuple[int, float, dict[str, Any]]:
    """Return (segment_index, similarity_ratio, segment) for the best fuzzy match.

    Args:
        exclude_indices: Segment indices already consumed by earlier sentences.
        min_idx: Only consider segments at or after this index (for forward matching).
    """
    exclude_indices = exclude_indices or set()
    best_idx = -1
    best_ratio = 0.0
    best_seg: dict[str, Any] = {}

    for idx, seg in enumerate(segments):
        if idx < min_idx or idx in exclude_indices:
            continue
        seg_text = _normalise(seg.get("text", ""))
        ratio = difflib.SequenceMatcher(None, needle, seg_text).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_idx = idx
            best_seg = seg

    return best_idx, best_ratio, best_seg


def _find_combined_match(
    needle: str,
    segments: list[dict[str, Any]],
    start_idx: int,
    window: int = 4,
) -> tuple[float, str, float, float]:
    """
    Try combining up to `window` consecutive segments starting from start_idx.
    Returns (best_ratio, combined_text, start_ts, end_ts).
    """
    best_ratio = 0.0
    best_text = ""
    best_start = -1.0
    best_end = -1.0

    combined_parts: list[str] = []
    for offset in range(min(window, len(segments) - start_idx)):
        seg = segments[start_idx + offset]
        combined_parts.append(_normalise(seg.get("text", "")))
        combined = " ".join(combined_parts)
        ratio = difflib.SequenceMatcher(None, needle, combined).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_text = combined
            best_start = segments[start_idx].get("start", -1.0)
            best_end = seg.get("end", -1.0)

    return best_ratio, best_text, best_start, best_end


# ── Main QA Function ──────────────────────────────────────────────────────────


def run_audio_qa(
    wav_path: str | Path,
    script_dialogue: list[dict[str, str]],
    language: str = "nl",
) -> QAReport:
    """Transcribe `wav_path` and compare against `script_dialogue`.

    Args:
        wav_path: Path to the WAV audio file.
        script_dialogue: Dialogue list, e.g. [{"Speaker1": "text"}, ...].
        language: BCP-47 language code for WhisperX (default: "nl").

    Returns:
        QAReport containing all detected issues.
    """
    from pipeline.generate.generate_subtitles import transcribe_audio_segments

    wav_path = Path(wav_path)
    if not wav_path.exists():
        raise FileNotFoundError(f"Audio file not found: {wav_path}")

    LOGGER.info("qa_audio.start wav=%s", wav_path.name)

    # --- Step 1: Transcribe --------------------------------------------------
    LOGGER.info("qa_audio.transcribing ...")
    segments: list[dict[str, Any]] = transcribe_audio_segments(
        wav_path=wav_path,
        language=language,
        script_dialogue=script_dialogue,
    )
    LOGGER.info("qa_audio.transcribed segments=%d", len(segments))

    # --- Step 2: Build expected sentence list --------------------------------
    expected = _extract_script_sentences(script_dialogue)
    report = QAReport(
        total_script_sentences=len(expected),
        total_transcript_segments=len(segments),
    )

    if not segments:
        LOGGER.warning("qa_audio.no_transcript — WhisperX returned zero segments")
        for idx, sent in enumerate(expected):
            report.issues.append(QAIssue(
                issue_type="MISSING",
                sentence_idx=idx,
                script_text=sent,
                transcript_text="",
                start_ts=-1.0,
                end_ts=-1.0,
                similarity=0.0,
            ))
        return report

    # --- Step 3: Match each script sentence against segments -----------------
    consumed_seg_indices: set[int] = set()
    matched_seg_indices: list[int] = []  # order of best-matched segment per sentence
    # Track the last successfully matched segment index to bias forward matching
    # for duplicate sentences (e.g. Error Clinic repeats the same line twice).
    last_matched_seg_idx: int = 0

    for sent_idx, sentence in enumerate(expected):
        # Single-segment match — exclude already-consumed segments so duplicate
        # script sentences bind to different audio segments in sequence.
        best_idx, best_ratio, best_seg = _best_match(
            sentence, segments,
            exclude_indices=consumed_seg_indices,
            min_idx=0,
        )

        # If the best unconstrained match is below threshold, also try a
        # forward-only search from the last matched position to handle cases
        # where a sentence truly repeats and we need the next occurrence.
        if best_ratio < _FOUND_THRESHOLD:
            fwd_idx, fwd_ratio, fwd_seg = _best_match(
                sentence, segments,
                exclude_indices=consumed_seg_indices,
                min_idx=last_matched_seg_idx,
            )
            if fwd_ratio > best_ratio:
                best_idx, best_ratio, best_seg = fwd_idx, fwd_ratio, fwd_seg

        # Try combining nearby segments if single best is still weak
        if best_ratio < _FOUND_THRESHOLD and best_idx >= 0:
            # Search a window around the single best match
            window_start = max(0, best_idx - 1)
            c_ratio, c_text, c_start, c_end = _find_combined_match(sentence, segments, window_start)
            if c_ratio > best_ratio:
                best_ratio = c_ratio
                best_seg = {"text": c_text, "start": c_start, "end": c_end}
                # Mark best_idx as the window start (for ordering purposes)
                best_idx = window_start

        ts_start = best_seg.get("start", -1.0)
        ts_end = best_seg.get("end", -1.0)
        transcript_text = _normalise(best_seg.get("text", ""))

        if best_ratio >= _FOUND_THRESHOLD:
            consumed_seg_indices.add(best_idx)
            matched_seg_indices.append(best_idx)
            last_matched_seg_idx = max(last_matched_seg_idx, best_idx)
        elif best_ratio >= _TRUNCATED_THRESHOLD:
            consumed_seg_indices.add(best_idx)
            matched_seg_indices.append(best_idx)
            last_matched_seg_idx = max(last_matched_seg_idx, best_idx)
            report.issues.append(QAIssue(
                issue_type="TRUNCATED",
                sentence_idx=sent_idx,
                script_text=sentence,
                transcript_text=transcript_text,
                start_ts=ts_start,
                end_ts=ts_end,
                similarity=round(best_ratio, 3),
            ))
        else:
            matched_seg_indices.append(-1)  # no match found
            report.issues.append(QAIssue(
                issue_type="MISSING",
                sentence_idx=sent_idx,
                script_text=sentence,
                transcript_text=transcript_text,
                start_ts=ts_start,
                end_ts=ts_end,
                similarity=round(best_ratio, 3),
            ))

    # --- Step 4: Detect EXTRA segments ---------------------------------------
    for seg_idx, seg in enumerate(segments):
        if seg_idx not in consumed_seg_indices:
            seg_text = _normalise(seg.get("text", ""))
            if not seg_text:
                continue
            report.issues.append(QAIssue(
                issue_type="EXTRA",
                sentence_idx=-1,
                script_text="",
                transcript_text=seg_text,
                start_ts=seg.get("start", -1.0),
                end_ts=seg.get("end", -1.0),
                similarity=0.0,
            ))

    # --- Step 5: Detect WRONG_ORDER ------------------------------------------
    prev_valid = -1
    for sent_idx, seg_idx in enumerate(matched_seg_indices):
        if seg_idx == -1:
            continue  # already flagged as MISSING
        if seg_idx < prev_valid:
            report.issues.append(QAIssue(
                issue_type="WRONG_ORDER",
                sentence_idx=sent_idx,
                script_text=expected[sent_idx],
                transcript_text=_normalise(segments[seg_idx].get("text", "")),
                start_ts=segments[seg_idx].get("start", -1.0),
                end_ts=segments[seg_idx].get("end", -1.0),
                similarity=round(
                    difflib.SequenceMatcher(
                        None, expected[sent_idx],
                        _normalise(segments[seg_idx].get("text", ""))
                    ).ratio(),
                    3,
                ),
            ))
        else:
            prev_valid = seg_idx

    return report


# ── Reporting ─────────────────────────────────────────────────────────────────


def _fmt_ts(seconds: float) -> str:
    if seconds < 0:
        return "??:??"
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def log_qa_report(report: QAReport, wav_name: str = "") -> None:
    """Log QA results to the console using the module logger."""
    label = f" [{wav_name}]" if wav_name else ""
    missing = [i for i in report.issues if i.issue_type == "MISSING"]
    extra = [i for i in report.issues if i.issue_type == "EXTRA"]
    truncated = [i for i in report.issues if i.issue_type == "TRUNCATED"]
    wrong_order = [i for i in report.issues if i.issue_type == "WRONG_ORDER"]

    total = report.total_script_sentences
    found = report.found_count

    # Score: penalise missing (full), truncated (half), extra/order (quarter each)
    penalty = len(missing) * 1.0 + len(truncated) * 0.5 + (len(extra) + len(wrong_order)) * 0.25
    score = max(0.0, 100.0 * (1.0 - penalty / total)) if total else 100.0
    score_str = f"{score:.1f}/100"

    if not report.issues:
        LOGGER.info(
            "qa_audio.PASS%s — score=%s | all %d/%d sentences found in audio",
            label, score_str, found, total,
        )
        return

    severity = logging.WARNING
    LOGGER.log(
        severity,
        "qa_audio.FAIL%s — score=%s | %d/%d sentences matched | "
        "missing=%d extra=%d truncated=%d wrong_order=%d",
        label, score_str, found, total,
        len(missing), len(extra), len(truncated), len(wrong_order),
    )

    for issue in missing:
        LOGGER.warning(
            "  [MISSING  ] #%02d @ (%s–%s) sim=%.2f | expected: %r",
            issue.sentence_idx + 1,
            _fmt_ts(issue.start_ts),
            _fmt_ts(issue.end_ts),
            issue.similarity,
            issue.script_text[:80],
        )

    for issue in truncated:
        LOGGER.warning(
            "  [TRUNCATED] #%02d @ (%s–%s) sim=%.2f | expected: %r | got: %r",
            issue.sentence_idx + 1,
            _fmt_ts(issue.start_ts),
            _fmt_ts(issue.end_ts),
            issue.similarity,
            issue.script_text[:60],
            issue.transcript_text[:60],
        )

    for issue in wrong_order:
        LOGGER.warning(
            "  [ORDER    ] #%02d @ (%s–%s) | expected order disrupted: %r",
            issue.sentence_idx + 1,
            _fmt_ts(issue.start_ts),
            _fmt_ts(issue.end_ts),
            issue.script_text[:60],
        )

    for issue in extra:
        LOGGER.warning(
            "  [EXTRA    ] @ (%s–%s) | not in script: %r",
            _fmt_ts(issue.start_ts),
            _fmt_ts(issue.end_ts),
            issue.transcript_text[:80],
        )
