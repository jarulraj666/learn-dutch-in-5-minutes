"""Claim and process Railway speaking-feedback jobs using local WhisperX."""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "learn" / "backend"))
load_dotenv(ROOT / ".env")

from speaking_feedback import evaluate_speaking_recording  # noqa: E402


def _configuration() -> tuple[str, dict[str, str]]:
    base_url = os.environ.get("LEARN_API_URL", "").rstrip("/")
    token = os.environ.get("SPEAKING_WORKER_TOKEN", "")
    if not base_url or not token:
        raise RuntimeError("LEARN_API_URL and SPEAKING_WORKER_TOKEN are required")
    return base_url, {"Authorization": f"Bearer {token}"}


def process_one() -> bool:
    base_url, headers = _configuration()
    response = requests.post(f"{base_url}/api/internal/speaking-jobs/claim", headers=headers, timeout=30)
    response.raise_for_status()
    job = response.json()
    if not job:
        return False

    job_id = job["id"]
    suffix = ".webm"
    try:
        audio = requests.get(f"{base_url}/api/internal/speaking-jobs/{job_id}/audio", headers=headers, timeout=60)
        audio.raise_for_status()
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp:
            temp.write(audio.content)
            audio_path = Path(temp.name)
        try:
            feedback = asyncio.run(evaluate_speaking_recording(
                audio_path, job["question_text"], job.get("grading_rubric") or [], job.get("model_answer") or "",
            ))
        finally:
            audio_path.unlink(missing_ok=True)
        completed = requests.post(
            f"{base_url}/api/internal/speaking-jobs/{job_id}/complete", headers=headers, json=feedback, timeout=60,
        )
        completed.raise_for_status()
        print(f"completed speaking job {job_id}")
        return True
    except Exception:
        requests.post(f"{base_url}/api/internal/speaking-jobs/{job_id}/fail", headers=headers, timeout=30)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Process Railway speaking jobs with local WhisperX")
    parser.add_argument("--watch", action="store_true", help="Keep polling for new jobs")
    parser.add_argument("--interval", type=int, default=60, help="Seconds between empty queue checks")
    args = parser.parse_args()
    while True:
        found = process_one()
        if found or not args.watch:
            if not found:
                print("no pending speaking jobs")
            if not args.watch:
                return 0
            continue
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())