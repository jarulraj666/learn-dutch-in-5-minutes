"""Generate and export A2 mock exams (Staatsexamen NT2 Programma I style).

Three independently-triggerable stages, mirroring how the webapp drives the
topic pipeline:

    content — call the LLM, normalize, save to the SQLite staging table
              (mock_exam_jobs). Fast, no external media APIs required.
    media   — generate audio/image/video for a previously-generated exam's
              passages, update the staged artifact. Requires Gemini
              image/TTS keys and ffmpeg.
    question_audio — voice only the per-question audio of a listening/KNM exam
              (Gemini TTS); leaves passage media untouched.
    export  — push the staged artifact into the learner-app Postgres tables
              (mock_exams / mock_exam_passages / mock_exam_questions).
    production_sync — upload local media to R2, replace artifact paths with
              public URLs, then push the exam to PRODUCTION_DATABASE_URL.

Usage:
    python -m pipeline.tools.generate_and_export_mock_exams --section reading --exam-number 1 --stage content
    python -m pipeline.tools.generate_and_export_mock_exams --section reading --exam-number 1 --stage media
    export DATABASE_URL='postgresql://user:pass@host/db'
    python -m pipeline.tools.generate_and_export_mock_exams --section reading --exam-number 1 --stage export

    # All 25 exams, all stages:
    python -m pipeline.tools.generate_and_export_mock_exams --stage content
    python -m pipeline.tools.generate_and_export_mock_exams --stage media
    python -m pipeline.tools.generate_and_export_mock_exams --stage export
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
LOGGER = logging.getLogger(__name__)


def _exam_targets(section: str | None, exam_number: int | None) -> list[tuple[str, int]]:
    from pipeline.generate.generate_mock_exam import SECTIONS

    sections = [section] if section else list(SECTIONS)
    numbers = [exam_number] if exam_number else list(range(1, 6))
    return [(s, n) for s in sections for n in numbers]


def run_content(section: str | None, exam_number: int | None, dry_run: bool) -> int:
    from pipeline.generate.generate_mock_exam import generate_mock_exam_content
    from pipeline.core.store_mock_exam import save_mock_exam_job

    ok = 0
    for sec, num in _exam_targets(section, exam_number):
        exam_id = f"a2-{sec}-{num}"
        try:
            artifact = generate_mock_exam_content(sec, num)
        except Exception as exc:
            LOGGER.error("content generation failed for %s: %s", exam_id, exc)
            continue

        print(f"{exam_id}: {len(artifact['questions'])} questions, {len(artifact['passages'])} passages")
        if not dry_run:
            save_mock_exam_job(exam_id, sec, num, artifact["level"], artifact, status="content_generated")
        ok += 1
    print(f"content stage: {ok} exam(s) generated")
    return 0 if ok else 1


def run_media(section: str | None, exam_number: int | None, dry_run: bool) -> int:
    from pipeline.generate.generate_mock_exam import generate_mock_exam_media
    from pipeline.core.store_mock_exam import load_mock_exam_job, save_mock_exam_job

    ok = 0
    for sec, num in _exam_targets(section, exam_number):
        exam_id = f"a2-{sec}-{num}"
        job = load_mock_exam_job(exam_id)
        if not job or not job.get("artifact"):
            LOGGER.warning("media stage: no staged content for %s (run --stage content first)", exam_id)
            continue

        artifact = generate_mock_exam_media(job["artifact"])
        print(f"{exam_id}: media generated for {len(artifact['passages'])} passage(s)")
        if not dry_run:
            save_mock_exam_job(exam_id, sec, num, artifact["level"], artifact, status="media_generated")
        ok += 1
    print(f"media stage: {ok} exam(s) processed")
    return 0 if ok else 1


def run_question_audio(section: str | None, exam_number: int | None, dry_run: bool, overwrite: bool) -> int:
    from pipeline.generate.generate_mock_exam import generate_mock_exam_question_audio
    from pipeline.core.store_mock_exam import load_mock_exam_job, save_mock_exam_job

    ok = 0
    for sec, num in _exam_targets(section, exam_number):
        if sec not in ("knm", "listening"):
            continue
        exam_id = f"a2-{sec}-{num}"
        job = load_mock_exam_job(exam_id)
        if not job or not job.get("artifact"):
            LOGGER.warning("question_audio stage: no staged content for %s (run --stage content first)", exam_id)
            continue

        artifact = job["artifact"]
        voiced = generate_mock_exam_question_audio(artifact, overwrite=overwrite)
        print(f"{exam_id}: audio ready for {voiced}/{len(artifact.get('questions', []))} question(s)")
        if not dry_run:
            save_mock_exam_job(exam_id, sec, num, artifact["level"], artifact, status="media_generated")
        ok += 1
    print(f"question_audio stage: {ok} exam(s) processed")
    return 0 if ok else 1


def run_export(section: str | None, exam_number: int | None, database_url: str, dry_run: bool) -> int:
    from pipeline.core.store_mock_exam import (
        load_mock_exam_job, mark_mock_exam_job_exported, push_mock_exam_to_postgres,
    )

    if not dry_run and not database_url:
        print("DATABASE_URL is required for --stage export (or pass --dry-run).")
        return 1

    ok = 0
    for sec, num in _exam_targets(section, exam_number):
        exam_id = f"a2-{sec}-{num}"
        job = load_mock_exam_job(exam_id)
        if not job or not job.get("artifact"):
            LOGGER.warning("export stage: no staged content for %s (run --stage content first)", exam_id)
            continue

        print(f"{exam_id}: exporting to Postgres")
        if not dry_run:
            push_mock_exam_to_postgres(job["artifact"], database_url)
            mark_mock_exam_job_exported(exam_id)
        ok += 1
    print(f"export stage: {ok} exam(s) exported")
    return 0 if ok else 1


def run_production_sync(section: str | None, exam_number: int | None, dry_run: bool) -> int:
    from pipeline.core.object_storage import ObjectStorageError, upload_mock_exam_media
    from pipeline.core.store_mock_exam import load_mock_exam_job, mark_mock_exam_job_exported, push_mock_exam_to_postgres, save_mock_exam_job

    database_url = os.environ.get("PRODUCTION_DATABASE_URL", "")
    if not database_url:
        print("PRODUCTION_DATABASE_URL is required for --stage production_sync.")
        return 1
    if not dry_run:
        import psycopg

        try:
            with psycopg.connect(database_url):
                pass
        except psycopg.Error as exc:
            LOGGER.error("production sync cannot connect to PRODUCTION_DATABASE_URL: %s", exc)
            return 1

    ok = 0
    for sec, num in _exam_targets(section, exam_number):
        exam_id = f"a2-{sec}-{num}"
        job = load_mock_exam_job(exam_id)
        if not job or not job.get("artifact"):
            LOGGER.warning("production_sync stage: no staged content for %s", exam_id)
            continue
        artifact = job["artifact"]
        try:
            uploaded = 0 if dry_run else upload_mock_exam_media(artifact)
            print(f"{exam_id}: {uploaded} media file(s) uploaded; syncing to production")
            if not dry_run:
                push_mock_exam_to_postgres(artifact, database_url)
                save_mock_exam_job(exam_id, sec, num, artifact["level"], artifact, status="exported")
                mark_mock_exam_job_exported(exam_id)
        except ObjectStorageError as exc:
            LOGGER.error("production sync failed for %s: %s", exam_id, exc)
            continue
        ok += 1
    print(f"production_sync stage: {ok} exam(s) synced")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate and export A2 mock exams")
    parser.add_argument("--section", choices=["reading", "listening", "writing", "speaking", "knm"])
    parser.add_argument("--exam-number", type=int, choices=range(1, 6))
    parser.add_argument("--stage", choices=["content", "media", "question_audio", "export", "production_sync"], required=True)
    parser.add_argument("--dry-run", action="store_true", help="Report only; no writes")
    parser.add_argument("--overwrite", action="store_true", help="Re-voice questions that already have audio")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL", ""))
    args = parser.parse_args()

    if args.stage == "content":
        return run_content(args.section, args.exam_number, args.dry_run)
    if args.stage == "media":
        return run_media(args.section, args.exam_number, args.dry_run)
    if args.stage == "question_audio":
        return run_question_audio(args.section, args.exam_number, args.dry_run, args.overwrite)
    if args.stage == "production_sync":
        return run_production_sync(args.section, args.exam_number, args.dry_run)
    return run_export(args.section, args.exam_number, args.database_url, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
