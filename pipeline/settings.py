from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent


# Multi-Speaker Data Types
@dataclass
class SpeakerMetadata:
    """Metadata for a speaker in dialogue."""
    id: str  # e.g., "Speaker1", "Speaker2"
    role: str  # e.g., "teacher", "learner", "native", "student"
    gender: str  # e.g., "female", "male"
    voice_id: str  # TTS voice identifier (e.g., "Kore", "Puck")


@dataclass
class SpeakerTimestamp:
    """Speaker timing information for multi-speaker audio synchronization."""
    speaker_id: str  # e.g., "Speaker1", "Speaker2"
    start_time: float  # seconds
    end_time: float  # seconds


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


def get_env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "gemini")  # Options: gemini, elevenlabs
TTS_FALLBACK_PROVIDER = os.getenv("TTS_FALLBACK_PROVIDER", "gemini")  # Options: gemini, elevenlabs
# Comma-separated API key lists — set these in .env to enable round-robin rotation.
GEMINI_API_KEYS: list[str] = [k.strip() for k in os.getenv("GEMINI_API_KEYS", "").split(",") if k.strip()]
GEMINI_IMAGE_CREATION_API_KEYS: list[str] = [k.strip() for k in os.getenv("GEMINI_IMAGE_CREATION_API_KEYS", "").split(",") if k.strip()]
# TTS-specific key list. Falls back to GEMINI_API_KEYS if GEMINI_TTS_API_KEYS is not set.
_raw_tts_keys = [k.strip() for k in os.getenv("GEMINI_TTS_API_KEYS", "").split(",") if k.strip()]
GEMINI_TTS_API_KEYS: list[str] = _raw_tts_keys if _raw_tts_keys else GEMINI_API_KEYS

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_SPEED = get_env_float("ELEVENLABS_SPEED", 0.75)

# Key rotators — shared singletons for 429-aware round-robin rotation.
# Cooldown duration is taken from the API response when available; falls back to 12 hours.
from pipeline.clients.key_rotator import KeyRotator  # noqa: E402

GEMINI_KEY_ROTATOR = KeyRotator(GEMINI_API_KEYS, "gemini")
GEMINI_IMAGE_KEY_ROTATOR = KeyRotator(GEMINI_IMAGE_CREATION_API_KEYS, "gemini_image")
GEMINI_TTS_KEY_ROTATOR = KeyRotator(GEMINI_TTS_API_KEYS, "gemini_tts")

# STT: WhisperX (medium model). Device is auto-detected (CUDA if available, else CPU).
# Override compute type via WHISPERX_COMPUTE_TYPE (default: float16 on GPU, int8 on CPU).
WHISPERX_MODEL = os.getenv("WHISPERX_MODEL", "medium")

# QA: Audio vs script sentence validation (runs after voice generation in run_pipeline.py).
# Set QA_AUDIO_CHECK=false in .env to disable.
QA_AUDIO_CHECK = os.getenv("QA_AUDIO_CHECK", "false").lower() not in ("false", "0", "no")

# QA: Subtitle timing validation (runs after subtitle generation in run_pipeline.py).
# Checks ASS karaoke tag sums, SRT sequence ordering, overlaps, and line count vs script.
# Set QA_SUBTITLE_CHECK=false in .env to disable.
QA_SUBTITLE_CHECK = os.getenv("QA_SUBTITLE_CHECK", "true").lower() not in ("false", "0", "no")
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
