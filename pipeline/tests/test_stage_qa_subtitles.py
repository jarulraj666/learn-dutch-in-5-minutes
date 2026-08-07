#!/usr/bin/env python3
"""Test Stage QA: Subtitle Timing Validation.

Validates .ass (karaoke) and .srt subtitle files for timing correctness.
Reports out-of-order lines, overlaps, karaoke tag mismatches, and line count
drift against the script dialogue.

Usage:
    # From episode artifact JSON (recommended):
    python -m pipeline.tests.test_stage_qa_subtitles output/A1/dialogue/episode_*.json

    # Explicit ASS file only:
    python -m pipeline.tests.test_stage_qa_subtitles --ass output/subtitles/episode_*.ass

    # Both ASS and SRT:
    python -m pipeline.tests.test_stage_qa_subtitles \\
        --ass output/subtitles/episode_*.ass \\
        --srt output/subtitles/episode_*_en.srt
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from pipeline import settings
from pipeline.generate.qa_subtitles import (
    SubtitleQAReport,
    _HARD_ISSUE_TYPES,
    log_subtitle_qa_report,
    run_ass_qa,
    run_srt_qa,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
LOGGER = logging.getLogger(__name__)


def _resolve_from_artifact(
    artifact_path: Path,
) -> tuple[Path | None, Path | None, int | None]:
    """Return (ass_path, srt_path, expected_count) from an episode artifact JSON.

    Subtitle paths that are absent or do not exist on disk are returned as None.
    """
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    def _resolve(raw: str) -> Path | None:
        if not raw:
            return None
        p = Path(raw)
        if not p.is_absolute():
            p = Path(settings.ROOT) / p
        return p if p.exists() else None

    # Subtitle paths may be at top-level, nested under 'subtitles', or under 'subtitle_plan'
    _subtitles = artifact.get("subtitles") or {}
    _subtitle_plan = artifact.get("subtitle_plan") or {}
    ass_raw = (
        artifact.get("karaoke_file", "")
        or _subtitles.get("karaoke_file", "")
        or _subtitle_plan.get("karaoke_file", "")
    )
    srt_raw = (
        _subtitles.get("srt_en", "")
        or artifact.get("srt_en", "")
        or artifact.get("srt_file", "")
        or _subtitles.get("srt_files", {}).get("en", "")
        or _subtitle_plan.get("srt_en", "")
    )

    ass_path = _resolve(ass_raw)
    srt_path = _resolve(srt_raw)

    # expected_count = number of dialogue turns in the script
    dialogue = artifact.get("script", {}).get("dialogue") or []
    expected_count = len(dialogue) if dialogue else None

    return ass_path, srt_path, expected_count


def _report_to_dict(report: SubtitleQAReport) -> dict:
    return {
        "file_path": report.file_path,
        "file_type": report.file_type,
        "line_count": report.line_count,
        "passed": report.passed,
        "hard_issues": len(report.hard_issues),
        "total_issues": len(report.issues),
        "issues": [
            {
                "issue_type": i.issue_type,
                "line_idx": i.line_idx,
                "start_ts": i.start_ts,
                "end_ts": i.end_ts,
                "detail": i.detail,
            }
            for i in report.issues
        ],
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="QA check: validate subtitle timing in .ass and .srt files."
    )
    parser.add_argument(
        "artifact",
        nargs="?",
        default=None,
        help="Path to episode artifact JSON (e.g. output/A1/dialogue/episode_*.json). "
             "Overrides --ass / --srt when provided.",
    )
    parser.add_argument(
        "--ass",
        metavar="ASS_FILE",
        help="Explicit path to .ass karaoke subtitle file.",
    )
    parser.add_argument(
        "--srt",
        metavar="SRT_FILE",
        help="Explicit path to .srt subtitle file.",
    )
    parser.add_argument(
        "--expected-count",
        type=int,
        default=None,
        metavar="N",
        help="Expected number of subtitle lines (for COUNT_MISMATCH check). "
             "Auto-resolved from artifact when using artifact mode.",
    )
    parser.add_argument(
        "--save",
        metavar="OUTPUT_JSON",
        nargs="?",
        const=str(Path(settings.OUTPUT_DIR) / "test_stage_qa_subtitles.json"),
        help="Save QA report JSON (defaults to output/test_stage_qa_subtitles.json).",
    )
    args = parser.parse_args(argv)

    LOGGER.info("=== TEST STAGE QA: Subtitle Timing Validation ===")

    ass_path: Path | None = None
    srt_path: Path | None = None
    expected_count: int | None = args.expected_count

    # --- Resolve inputs -------------------------------------------------------
    if args.artifact:
        artifact_path = Path(args.artifact)
        if not artifact_path.is_absolute():
            artifact_path = Path(settings.ROOT) / artifact_path
        LOGGER.info("Loading from artifact: %s", artifact_path)
        ass_path, srt_path, resolved_count = _resolve_from_artifact(artifact_path)
        if expected_count is None:
            expected_count = resolved_count
        if ass_path:
            LOGGER.info("ASS file: %s", ass_path)
        else:
            LOGGER.warning("No ASS subtitle file found in artifact (skipping ASS QA)")
        if srt_path:
            LOGGER.info("SRT file: %s", srt_path)
        else:
            LOGGER.debug("No SRT subtitle file found in artifact (skipping SRT QA)")
    else:
        if args.ass:
            p = Path(args.ass)
            ass_path = p if p.is_absolute() else Path(settings.ROOT) / p
        if args.srt:
            p = Path(args.srt)
            srt_path = p if p.is_absolute() else Path(settings.ROOT) / p

    if not ass_path and not srt_path:
        LOGGER.error(
            "No subtitle files to check. Provide an artifact JSON or --ass / --srt."
        )
        sys.exit(1)

    # --- Run QA ---------------------------------------------------------------
    reports: list[SubtitleQAReport] = []
    any_hard_failure = False

    if ass_path:
        if not ass_path.exists():
            LOGGER.error("ASS file not found: %s", ass_path)
            sys.exit(1)
        LOGGER.info("--- Running ASS QA ---")
        ass_report = run_ass_qa(ass_path, expected_count=expected_count)
        log_subtitle_qa_report(ass_report)
        reports.append(ass_report)
        if not ass_report.passed:
            any_hard_failure = True

    if srt_path:
        if not srt_path.exists():
            LOGGER.debug("SRT file not found, skipping: %s", srt_path)
        else:
            LOGGER.info("--- Running SRT QA ---")
            srt_report = run_srt_qa(srt_path, expected_count=expected_count)
            log_subtitle_qa_report(srt_report)
            reports.append(srt_report)
            if not srt_report.passed:
                any_hard_failure = True

    # --- Save output ----------------------------------------------------------
    if args.save and reports:
        save_path = Path(args.save)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_text(
            json.dumps([_report_to_dict(r) for r in reports], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        LOGGER.info("QA report saved to: %s", save_path)

    # --- Final summary --------------------------------------------------------
    total_hard = sum(len(r.hard_issues) for r in reports)
    total_warn = sum(
        len([i for i in r.issues if i.issue_type not in _HARD_ISSUE_TYPES])
        for r in reports
    )
    if any_hard_failure:
        LOGGER.error(
            "=== QA FAILED — %d hard issue(s), %d warning(s) ===",
            total_hard,
            total_warn,
        )
        sys.exit(1)
    else:
        LOGGER.info(
            "=== QA PASSED — 0 hard issues, %d warning(s) ===",
            total_warn,
        )


if __name__ == "__main__":
    main()
