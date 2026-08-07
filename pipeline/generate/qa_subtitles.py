"""Subtitle QA Module.

Validates timing in .ass (Advanced SubStation Alpha karaoke) and .srt subtitle files.
Checks for malformed timestamps, out-of-order lines, overlaps, karaoke tag mismatches,
and optionally cross-checks line count against the expected script dialogue turn count.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

LOGGER = logging.getLogger(__name__)

# Hard failure issue types (cause .passed to return False)
_HARD_ISSUE_TYPES = frozenset({"START_AFTER_END", "ZERO_DURATION", "OUT_OF_ORDER", "KARAOKE_MISMATCH"})

# Timing thresholds
_ZERO_DURATION_THRESHOLD = 0.05   # seconds — below this is effectively zero
_TOO_SHORT_THRESHOLD = 0.10       # seconds — warning: suspiciously short line
_TOO_LONG_THRESHOLD = 15.0        # seconds — warning: suspiciously long line
_KARAOKE_TOLERANCE_CS = 10        # centiseconds — allowed deviation in karaoke sum vs line duration


# ── Data Types ────────────────────────────────────────────────────────────────


@dataclass
class SubtitleQAIssue:
    issue_type: str   # START_AFTER_END | ZERO_DURATION | OUT_OF_ORDER | OVERLAP |
                      # TOO_SHORT | TOO_LONG | KARAOKE_MISMATCH | BAD_SEQUENCE | COUNT_MISMATCH
    line_idx: int     # 0-based dialogue line index (-1 for file-level issues)
    start_ts: float   # start timestamp in seconds (-1.0 if not applicable)
    end_ts: float     # end timestamp in seconds (-1.0 if not applicable)
    detail: str       # human-readable description of the issue


@dataclass
class SubtitleQAReport:
    file_path: str
    file_type: str              # "ASS" or "SRT"
    line_count: int = 0
    issues: list[SubtitleQAIssue] = field(default_factory=list)

    @property
    def hard_issues(self) -> list[SubtitleQAIssue]:
        return [i for i in self.issues if i.issue_type in _HARD_ISSUE_TYPES]

    @property
    def passed(self) -> bool:
        return len(self.hard_issues) == 0


# ── Timestamp Parsers ─────────────────────────────────────────────────────────


def _parse_ass_ts(ts: str) -> float:
    """Convert ASS timestamp H:MM:SS.cs to float seconds (centiseconds resolution)."""
    m = re.match(r"^(\d+):(\d{2}):(\d{2})\.(\d{2})$", ts.strip())
    if not m:
        raise ValueError(f"Invalid ASS timestamp: {ts!r}")
    h, mn, s, cs = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
    return h * 3600.0 + mn * 60.0 + s + cs / 100.0


def _parse_srt_ts(ts: str) -> float:
    """Convert SRT timestamp HH:MM:SS,mmm to float seconds (millisecond resolution)."""
    m = re.match(r"^(\d{2}):(\d{2}):(\d{2}),(\d{3})$", ts.strip())
    if not m:
        raise ValueError(f"Invalid SRT timestamp: {ts!r}")
    h, mn, s, ms = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
    return h * 3600.0 + mn * 60.0 + s + ms / 1000.0


# ── Format Helpers ────────────────────────────────────────────────────────────


_KARAOKE_RE = re.compile(r"\{\\kf(\d+)\}")

_ASS_DIALOGUE_RE = re.compile(
    r"^Dialogue:\s*\d+,"            # Layer
    r"(\d+:\d{2}:\d{2}\.\d{2}),"   # Start
    r"(\d+:\d{2}:\d{2}\.\d{2}),"   # End
    r"([^,]*),"                     # Style
    r"[^,]*,"                       # Name
    r"[^,]*,[^,]*,[^,]*,"           # MarginL, MarginR, MarginV
    r"[^,]*,"                       # Effect
    r"(.*)$",                       # Text
    re.IGNORECASE,
)

_SRT_TIMING_RE = re.compile(
    r"^(\d{2}:\d{2}:\d{2},\d{3})\s+-->\s+(\d{2}:\d{2}:\d{2},\d{3})"
)


def _karaoke_sum_cs(text: str) -> int:
    """Sum all \\kfN values in centiseconds from an ASS text field."""
    return sum(int(n) for n in _KARAOKE_RE.findall(text))


# ── Shared Timing Checks ──────────────────────────────────────────────────────


def _check_timing(
    lines: list[tuple[float, float]],
    issues: list[SubtitleQAIssue],
) -> None:
    """Run timing sanity checks across (start, end) pairs (in seconds).

    Appends SubtitleQAIssue entries directly to *issues*.
    """
    prev_start = -1.0
    prev_end = -1.0

    for idx, (start, end) in enumerate(lines):
        duration = end - start

        if start >= end:
            issues.append(SubtitleQAIssue(
                issue_type="START_AFTER_END",
                line_idx=idx,
                start_ts=start,
                end_ts=end,
                detail=f"start {start:.3f}s >= end {end:.3f}s",
            ))
        elif duration < _ZERO_DURATION_THRESHOLD:
            issues.append(SubtitleQAIssue(
                issue_type="ZERO_DURATION",
                line_idx=idx,
                start_ts=start,
                end_ts=end,
                detail=f"duration {duration:.3f}s < threshold {_ZERO_DURATION_THRESHOLD}s",
            ))
        elif duration < _TOO_SHORT_THRESHOLD:
            issues.append(SubtitleQAIssue(
                issue_type="TOO_SHORT",
                line_idx=idx,
                start_ts=start,
                end_ts=end,
                detail=f"duration {duration:.3f}s < {_TOO_SHORT_THRESHOLD}s",
            ))

        if duration > _TOO_LONG_THRESHOLD:
            issues.append(SubtitleQAIssue(
                issue_type="TOO_LONG",
                line_idx=idx,
                start_ts=start,
                end_ts=end,
                detail=f"duration {duration:.3f}s > {_TOO_LONG_THRESHOLD}s",
            ))

        if idx > 0:
            if start < prev_start:
                issues.append(SubtitleQAIssue(
                    issue_type="OUT_OF_ORDER",
                    line_idx=idx,
                    start_ts=start,
                    end_ts=end,
                    detail=f"start {start:.3f}s < previous start {prev_start:.3f}s",
                ))
            elif start < prev_end:
                issues.append(SubtitleQAIssue(
                    issue_type="OVERLAP",
                    line_idx=idx,
                    start_ts=start,
                    end_ts=end,
                    detail=f"start {start:.3f}s < previous end {prev_end:.3f}s",
                ))

        prev_start = start
        prev_end = end


# ── Public QA Functions ───────────────────────────────────────────────────────


def run_ass_qa(
    ass_path: str | Path,
    expected_count: int | None = None,
) -> SubtitleQAReport:
    """Validate timing and karaoke tags in an ASS subtitle file.

    Args:
        ass_path: Path to the .ass file.
        expected_count: Expected number of dialogue lines (from script dialogue turns).
            Pass None to skip the COUNT_MISMATCH cross-check.

    Returns:
        SubtitleQAReport with all detected issues.
    """
    ass_path = Path(ass_path)
    if not ass_path.exists():
        raise FileNotFoundError(f"ASS file not found: {ass_path}")

    LOGGER.info("qa_subtitles.ass.start file=%s", ass_path.name)
    report = SubtitleQAReport(file_path=str(ass_path), file_type="ASS")

    raw_lines = ass_path.read_text(encoding="utf-8").splitlines()
    # Each entry: (start_s, end_s, text)
    dialogue_entries: list[tuple[float, float, str]] = []

    for raw in raw_lines:
        m = _ASS_DIALOGUE_RE.match(raw)
        if not m:
            continue
        try:
            start = _parse_ass_ts(m.group(1))
            end = _parse_ass_ts(m.group(2))
        except ValueError as exc:
            report.issues.append(SubtitleQAIssue(
                issue_type="START_AFTER_END",
                line_idx=len(dialogue_entries),
                start_ts=-1.0,
                end_ts=-1.0,
                detail=f"Unparseable timestamp: {exc}",
            ))
            continue
        dialogue_entries.append((start, end, m.group(4)))

    report.line_count = len(dialogue_entries)
    LOGGER.info("qa_subtitles.ass.parsed lines=%d", report.line_count)

    # Timing checks
    _check_timing([(s, e) for s, e, _ in dialogue_entries], report.issues)

    # Karaoke tag sum check — each line's {\kfN} durations must sum to
    # within _KARAOKE_TOLERANCE_CS of the line's display duration.
    for idx, (start, end, text) in enumerate(dialogue_entries):
        ksum = _karaoke_sum_cs(text)
        if ksum == 0:
            continue  # no karaoke tags on this line — skip (e.g. plain-style lines)
        expected_cs = round((end - start) * 100)
        deviation = abs(ksum - expected_cs)
        if deviation > _KARAOKE_TOLERANCE_CS:
            report.issues.append(SubtitleQAIssue(
                issue_type="KARAOKE_MISMATCH",
                line_idx=idx,
                start_ts=start,
                end_ts=end,
                detail=(
                    f"karaoke sum {ksum}cs vs line duration {expected_cs}cs "
                    f"(deviation {deviation}cs > tolerance {_KARAOKE_TOLERANCE_CS}cs)"
                ),
            ))

    # Cross-check line count vs script dialogue turns
    if expected_count is not None and report.line_count != expected_count:
        report.issues.append(SubtitleQAIssue(
            issue_type="COUNT_MISMATCH",
            line_idx=-1,
            start_ts=-1.0,
            end_ts=-1.0,
            detail=(
                f"subtitle lines {report.line_count} != "
                f"script dialogue turns {expected_count}"
            ),
        ))

    LOGGER.info(
        "qa_subtitles.ass.done lines=%d hard_issues=%d total_issues=%d",
        report.line_count, len(report.hard_issues), len(report.issues),
    )
    return report


def run_srt_qa(
    srt_path: str | Path,
    expected_count: int | None = None,
) -> SubtitleQAReport:
    """Validate timing in an SRT subtitle file.

    Args:
        srt_path: Path to the .srt file.
        expected_count: Expected number of subtitle entries (from script dialogue turns).
            Pass None to skip the COUNT_MISMATCH cross-check.

    Returns:
        SubtitleQAReport with all detected issues.
    """
    srt_path = Path(srt_path)
    if not srt_path.exists():
        raise FileNotFoundError(f"SRT file not found: {srt_path}")

    LOGGER.info("qa_subtitles.srt.start file=%s", srt_path.name)
    report = SubtitleQAReport(file_path=str(srt_path), file_type="SRT")

    raw_lines = srt_path.read_text(encoding="utf-8").splitlines()
    # Each entry: (start_s, end_s, sequence_number)
    entries: list[tuple[float, float, int]] = []
    seq_num: int | None = None

    for raw in raw_lines:
        stripped = raw.strip()
        if not stripped:
            seq_num = None
            continue

        # Sequence number line — a bare integer
        if seq_num is None and stripped.isdigit():
            seq_num = int(stripped)
            continue

        # Timing line immediately follows the sequence number
        if seq_num is not None:
            m = _SRT_TIMING_RE.match(stripped)
            if m:
                try:
                    start = _parse_srt_ts(m.group(1))
                    end = _parse_srt_ts(m.group(2))
                except ValueError as exc:
                    report.issues.append(SubtitleQAIssue(
                        issue_type="START_AFTER_END",
                        line_idx=len(entries),
                        start_ts=-1.0,
                        end_ts=-1.0,
                        detail=f"Unparseable timestamp: {exc}",
                    ))
                    seq_num = None
                    continue
                entries.append((start, end, seq_num))
                # Keep seq_num set — remaining lines are subtitle text (ignored)

    report.line_count = len(entries)
    LOGGER.info("qa_subtitles.srt.parsed entries=%d", report.line_count)

    # Timing checks
    _check_timing([(s, e) for s, e, _ in entries], report.issues)

    # Sequence number continuity check
    for idx, (start, end, snum) in enumerate(entries):
        expected_seq = idx + 1
        if snum != expected_seq:
            report.issues.append(SubtitleQAIssue(
                issue_type="BAD_SEQUENCE",
                line_idx=idx,
                start_ts=start,
                end_ts=end,
                detail=f"sequence number {snum} != expected {expected_seq}",
            ))

    # Cross-check entry count vs expected count
    if expected_count is not None and report.line_count != expected_count:
        report.issues.append(SubtitleQAIssue(
            issue_type="COUNT_MISMATCH",
            line_idx=-1,
            start_ts=-1.0,
            end_ts=-1.0,
            detail=(
                f"subtitle entries {report.line_count} != "
                f"expected count {expected_count}"
            ),
        ))

    LOGGER.info(
        "qa_subtitles.srt.done entries=%d hard_issues=%d total_issues=%d",
        report.line_count, len(report.hard_issues), len(report.issues),
    )
    return report


# ── Reporting ─────────────────────────────────────────────────────────────────


def _fmt_ts(seconds: float) -> str:
    if seconds < 0:
        return "??:??"
    m, s = divmod(int(seconds), 60)
    cs = round((seconds % 1) * 100)
    return f"{m:02d}:{s:02d}.{cs:02d}"


def log_subtitle_qa_report(
    report: SubtitleQAReport,
    *,
    file_label: str = "",
) -> None:
    """Log subtitle QA results to the module logger."""
    label = f" [{file_label}]" if file_label else f" [{Path(report.file_path).name}]"
    hard = report.hard_issues
    warnings = [i for i in report.issues if i.issue_type not in _HARD_ISSUE_TYPES]

    if not report.issues:
        LOGGER.info(
            "qa_subtitles.PASS%s — %s %d lines, 0 issues",
            label, report.file_type, report.line_count,
        )
        return

    LOGGER.log(
        logging.WARNING,
        "qa_subtitles.%s%s — %s %d lines | hard=%d warnings=%d",
        "FAIL" if hard else "WARN",
        label,
        report.file_type,
        report.line_count,
        len(hard),
        len(warnings),
    )

    _W = 18  # column width for issue type
    for issue in report.issues:
        is_hard = issue.issue_type in _HARD_ISSUE_TYPES
        log_fn = LOGGER.warning if is_hard else LOGGER.info
        ts_range = (
            f"@ ({_fmt_ts(issue.start_ts)}–{_fmt_ts(issue.end_ts)})"
            if issue.start_ts >= 0
            else ""
        )
        line_ref = f"#line {issue.line_idx + 1:02d}" if issue.line_idx >= 0 else "#file   "
        log_fn(
            "  [%-*s] %s %s | %s",
            _W,
            issue.issue_type,
            line_ref,
            ts_range,
            issue.detail,
        )
