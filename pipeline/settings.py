from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


load_env_file(ROOT / ".env")

DB_PATH = Path(os.getenv("DB_PATH", "db/content.db"))
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")
OLLAMA_IMAGE_MODEL = os.getenv("OLLAMA_IMAGE_MODEL", "x/flux2-klein:4b")
VISUAL_IMAGE_FORMAT = os.getenv("VISUAL_IMAGE_FORMAT", "png")
CHANNEL_TIMEZONE = os.getenv("CHANNEL_TIMEZONE", "Europe/Amsterdam")
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "output"))
VIDEO_OUTPUT_DIR = Path(os.getenv("VIDEO_OUTPUT_DIR", "output/videos"))
VIDEO_ARCHIVE_DIR = Path(os.getenv("VIDEO_ARCHIVE_DIR", "output/archive"))

# TTS Provider Configuration
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "gemini")  # Options: macos_say, gemini, kokoro
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_IMAGE_CREATION_API_KEY = os.getenv("GEMINI_IMAGE_CREATION_API_KEY", "")
GEMINI_TTS_API_KEY = os.getenv("GEMINI_TTS_API_KEY", "")
# Note: Kokoro TTS runs locally, no API key needed

# STT: WhisperX (medium model). Device is auto-detected (CUDA if available, else CPU).
# Override compute type via WHISPERX_COMPUTE_TYPE (default: float16 on GPU, int8 on CPU).
WHISPERX_MODEL = os.getenv("WHISPERX_MODEL", "medium")
WHISPERX_COMPUTE_TYPE = os.getenv("WHISPERX_COMPUTE_TYPE", "")

PEDAGOGY_CONFIG = load_yaml(ROOT / "config/pedagogy.yaml")
SCHEDULING_CONFIG = load_yaml(ROOT / "config/scheduling.yaml")


def get_pedagogy_for_level(level: str) -> dict[str, Any]:
    """Return pedagogy config merged with per-level overrides for *level* (e.g. 'A1', 'B2').

    Falls back to the base PEDAGOGY_CONFIG (A1 defaults) if the level is not found.
    """
    import copy

    base = {k: v for k, v in PEDAGOGY_CONFIG.items() if k != "levels"}
    level_overrides: dict[str, Any] = PEDAGOGY_CONFIG.get("levels", {}).get(level, {})
    if not level_overrides:
        return base

    merged = copy.deepcopy(base)
    for key, value in level_overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value
    return merged
PLAYLISTS_CONFIG = load_yaml(ROOT / "config/playlists.yaml")
TOPIC_BACKLOG_CONFIG = load_yaml(ROOT / "config/topic_backlog.yaml")
