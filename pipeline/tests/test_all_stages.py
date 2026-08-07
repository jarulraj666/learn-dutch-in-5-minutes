#!/usr/bin/env python3
"""Modular pipeline testing helper.

Usage:
  python -m pipeline.test_all_stages --help
  python -m pipeline.test_all_stages --all
"""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

try:
    import psutil
except ImportError:
    psutil = None


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
LOGGER = logging.getLogger(__name__)


def check_system_resources() -> bool:
    """Check available system resources.

    If psutil is unavailable, skip checks but keep the pipeline usable.
    """
    LOGGER.info("=== SYSTEM RESOURCE CHECK ===")

    if psutil is None:
        LOGGER.warning("psutil is not installed; skipping resource checks")
        return True

    mem = psutil.virtual_memory()
    LOGGER.info(
        "Memory: %.1f GB total, %.1f GB available (%.1f%% used)",
        mem.total / (1024**3),
        mem.available / (1024**3),
        mem.percent,
    )
    if mem.available < 8 * (1024**3):
        LOGGER.warning("Low memory (<8GB available). Rendering may be slow.")

    disk = psutil.disk_usage("/")
    LOGGER.info(
        "Disk: %.1f GB total, %.1f GB available (%.1f%% used)",
        disk.total / (1024**3),
        disk.free / (1024**3),
        disk.percent,
    )
    if disk.free < 5 * (1024**3):
        LOGGER.error("Critical: Less than 5GB disk space available")
        return False

    LOGGER.info("CPU cores: %d", psutil.cpu_count())
    LOGGER.info("CPU usage: %.1f%%", psutil.cpu_percent(interval=1))
    return True


def check_ollama_running() -> bool:
    """Check if Ollama is reachable on localhost:11434."""
    try:
        import requests

        response = requests.get("http://localhost:11434/api/tags", timeout=2)
        if response.status_code == 200:
            LOGGER.info("Ollama is running")
            return True

        LOGGER.error("Ollama responded with status code %d", response.status_code)
        return False
    except Exception:
        LOGGER.error("Ollama is not running on localhost:11434")
        LOGGER.info("Start Ollama with: ollama serve")
        return False


def run_stage(stage_label: str, module_name: str, stage_name: str) -> bool:
    """Run a stage test module with the current Python interpreter."""
    LOGGER.info("\n%s", "=" * 60)
    LOGGER.info("RUNNING: Stage %s - %s", stage_label, stage_name)
    LOGGER.info("%s", "=" * 60)

    try:
        subprocess.run(
            [sys.executable, "-m", f"pipeline.{module_name}"],
            cwd=Path(__file__).parent.parent,
            check=True,
        )
        LOGGER.info("Stage %s completed successfully", stage_label)
        return True
    except subprocess.CalledProcessError as exc:
        LOGGER.error("Stage %s failed with exit code %d", stage_label, exc.returncode)
        return False
    except KeyboardInterrupt:
        LOGGER.warning("Stage %s interrupted by user", stage_label)
        return False


def print_instructions() -> None:
    """Print concise usage and stage notes."""
    print(
        """
DUTCH LANGUAGE VIDEO PIPELINE TESTING

Run one stage manually:
  python -m pipeline.test_stage_1_script_generation
  python -m pipeline.test_stage_2_voice_generation
    python -m pipeline.test_stage_3a_speech_to_text
    python -m pipeline.test_stage_3c_karaoke_generation
    python -m pipeline.test_stage_3b_image_generation
  python -m pipeline.test_stage_4_video_rendering

Run all stages through this helper:
  python -m pipeline.test_all_stages --all

Troubleshooting:
  - Stage 1 fails: ensure Ollama is running (ollama serve)
  - Stage 2 fails: check GEMINI_API_KEYS, quota, and network
    - Stage 3a fails: check GEMINI_API_KEYS and network access
    - Stage 4 fails: ensure ffmpeg is installed and Stage 2/3a/3c/3b outputs exist
""".strip()
    )


def main() -> None:
    args = set(sys.argv[1:])

    if "--help" in args or "-h" in args:
        print_instructions()
        return

    if args.intersection({"all", "--all", "-a"}):
        LOGGER.info("Running all stages sequentially...")

        if not check_system_resources():
            LOGGER.error("System resources check failed")
            return

        if not check_ollama_running():
            LOGGER.error("Ollama is not running. Start with: ollama serve")
            return

        stages = [
            ("1", "test_stage_1_script_generation", "Script Generation"),
            ("2", "test_stage_2_voice_generation", "Voice Generation"),
            ("3a", "test_stage_3a_speech_to_text", "Speech-to-Text Extraction"),
            ("3c", "test_stage_3c_karaoke_generation", "Karaoke/SRT Generation"),
            ("3b", "test_stage_3b_image_generation", "Background Image Generation"),
            ("4", "test_stage_4_video_rendering", "Video Rendering"),
        ]

        for index, (stage_label, module_name, stage_name) in enumerate(stages, start=1):
            success = run_stage(stage_label, module_name, stage_name)
            if not success:
                LOGGER.error("\nPipeline stopped at stage %s", stage_label)
                return

            if index < len(stages):
                check_system_resources()

        LOGGER.info("\n%s", "=" * 60)
        LOGGER.info("ALL STAGES COMPLETED SUCCESSFULLY")
        LOGGER.info("%s", "=" * 60)
        return

    print_instructions()


if __name__ == "__main__":
    main()
