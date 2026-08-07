#!/usr/bin/env python3
"""Test Stage QA: Audio vs Script Sentence Validation.

Transcribes the episode WAV and compares it against the script dialogue.
Reports missing, extra, truncated, and out-of-order sentences with timestamps.

Usage:
    # From episode artifact JSON (recommended):
    python -m pipeline.tests.test_stage_qa_audio output/A1A2/grammar/episode_grammar_present_tense_present_tense_of_regular_verbs_werken_wonen_leven.json

    # Explicit audio + script pair:
    python -m pipeline.tests.test_stage_qa_audio --wav path/to/audio.wav --script path/to/episode.json
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from pipeline import settings
from pipeline.generate.qa_audio import log_qa_report, run_audio_qa

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
LOGGER = logging.getLogger(__name__)


def _resolve_from_artifact(artifact_path: Path) -> tuple[Path, list[dict], str]:
    """Return (wav_path, dialogue, language) from an episode artifact JSON."""
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    # Resolve WAV path
    audio_raw = artifact.get("audio_file_raw") or artifact.get("audio_file") or \
                artifact.get("voice", {}).get("dialogue_audio", "")
    if not audio_raw:
        raise ValueError(f"No audio_file path found in artifact: {artifact_path}")

    wav_path = Path(audio_raw)
    if not wav_path.is_absolute():
        wav_path = Path(settings.ROOT) / wav_path
    if not wav_path.exists():
        raise FileNotFoundError(f"WAV file not found: {wav_path}")

    # Resolve dialogue
    dialogue = artifact.get("script", {}).get("dialogue")
    if not dialogue:
        raise ValueError(f"No script.dialogue found in artifact: {artifact_path}")

    language = artifact.get("script", {}).get("language", "nl")
    return wav_path, dialogue, language


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="QA check: compare WAV audio against script sentences."
    )
    parser.add_argument(
        "artifact",
        nargs="?",
        default=None,
        help="Path to episode artifact JSON (e.g. output/A1/grammar/episode_*.json). "
             "Overrides --wav / --script when provided.",
    )
    parser.add_argument(
        "--wav",
        metavar="WAV_FILE",
        help="Explicit path to WAV audio file (use with --script).",
    )
    parser.add_argument(
        "--script",
        metavar="SCRIPT_JSON",
        help="Explicit path to episode JSON containing script.dialogue.",
    )
    parser.add_argument(
        "--language",
        default="nl",
        help="Language code for WhisperX transcription (default: nl).",
    )
    parser.add_argument(
        "--save",
        metavar="OUTPUT_JSON",
        nargs="?",
        const=str(Path(settings.OUTPUT_DIR) / "test_stage_qa_audio.json"),
        help="Save QA report JSON (defaults to output/test_stage_qa_audio.json).",
    )
    args = parser.parse_args(argv)

    LOGGER.info("=== TEST STAGE QA: Audio vs Script ===")

    # --- Resolve inputs -------------------------------------------------------
    if args.artifact:
        artifact_path = Path(args.artifact)
        if not artifact_path.is_absolute():
            artifact_path = Path(settings.ROOT) / artifact_path
        LOGGER.info("Loading from artifact: %s", artifact_path)
        wav_path, dialogue, language = _resolve_from_artifact(artifact_path)
    elif args.wav and args.script:
        wav_path = Path(args.wav)
        script_path = Path(args.script)
        script_data = json.loads(script_path.read_text(encoding="utf-8"))
        dialogue = script_data.get("script", {}).get("dialogue") or script_data.get("dialogue")
        if not dialogue:
            LOGGER.error("No dialogue found in %s", script_path)
            sys.exit(1)
        language = args.language
    else:
        # Try default stage-1 output
        default_artifact = Path(settings.OUTPUT_DIR) / "test_stage_1_script.json"
        if default_artifact.exists():
            LOGGER.info("No argument given — falling back to %s", default_artifact)
            wav_path, dialogue, language = _resolve_from_artifact(default_artifact)
        else:
            LOGGER.error(
                "Provide an artifact JSON path, or --wav + --script.\n"
                "Example: python -m pipeline.tests.test_stage_qa_audio output/A1A2/grammar/episode_*.json"
            )
            sys.exit(1)

    LOGGER.info("WAV  : %s", wav_path)
    LOGGER.info("Lines: %d script sentences", len(dialogue))
    LOGGER.info("Lang : %s", language)

    # --- Run QA ---------------------------------------------------------------
    report = run_audio_qa(wav_path=wav_path, script_dialogue=dialogue, language=language)
    log_qa_report(report, wav_name=wav_path.name)

    # --- Optionally save JSON report ------------------------------------------
    if args.save:
        save_path = Path(args.save)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        report_data = {
            "wav_file": str(wav_path),
            "total_script_sentences": report.total_script_sentences,
            "total_transcript_segments": report.total_transcript_segments,
            "found_count": report.found_count,
            "passed": report.passed,
            "issues": [
                {
                    "issue_type": i.issue_type,
                    "sentence_idx": i.sentence_idx,
                    "script_text": i.script_text,
                    "transcript_text": i.transcript_text,
                    "start_ts": i.start_ts,
                    "end_ts": i.end_ts,
                    "similarity": i.similarity,
                }
                for i in report.issues
            ],
        }
        save_path.write_text(json.dumps(report_data, ensure_ascii=False, indent=2), encoding="utf-8")
        LOGGER.info("✓ QA report saved to: %s", save_path)

    # Exit non-zero if hard failures (MISSING sentences)
    hard_failures = [i for i in report.issues if i.issue_type == "MISSING"]
    sys.exit(1 if hard_failures else 0)


if __name__ == "__main__":
    main()
