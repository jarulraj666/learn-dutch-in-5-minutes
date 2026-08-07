"""Factory helpers for TTS provider initialization."""

from __future__ import annotations

import logging
from typing import Protocol

from pipeline import settings
from pipeline.clients.elevenlabs_tts_client import create_elevenlabs_client
from pipeline.clients.gemini_tts_client import RotatingGeminiTTSClient

LOGGER = logging.getLogger(__name__)

SUPPORTED_TTS_PROVIDERS = {"gemini", "elevenlabs"}


class TTSClientProtocol(Protocol):
    provider_name: str

    def generate_dialogue_audio(
        self,
        dialogue: list[dict[str, str]],
        output_path: str,
        level: str = "A1A2",
        category: str = "dialogue",
        speaker_genders: dict[str, str] | None = None,
        speaker_roles: dict[str, str] | None = None,
    ) -> bool: ...


def normalize_provider_name(provider_name: str | None) -> str:
    name = (provider_name or "").strip().lower()
    return name or "gemini"


def create_tts_client(provider_name: str) -> TTSClientProtocol:
    provider = normalize_provider_name(provider_name)
    if provider not in SUPPORTED_TTS_PROVIDERS:
        raise ValueError(
            f"Unsupported TTS provider '{provider}'. Supported providers: {sorted(SUPPORTED_TTS_PROVIDERS)}"
        )

    if provider == "gemini":
        if not settings.GEMINI_TTS_API_KEYS:
            raise ValueError("No Gemini TTS API keys configured. Set GEMINI_TTS_API_KEYS in .env")
        return RotatingGeminiTTSClient(settings.GEMINI_TTS_KEY_ROTATOR)

    api_key = settings.ELEVENLABS_API_KEY
    if not api_key:
        raise ValueError("ELEVENLABS_API_KEY is missing.")
    client = create_elevenlabs_client(api_key)
    if not client:
        raise RuntimeError("Failed to initialize ElevenLabs TTS client.")
    return client
