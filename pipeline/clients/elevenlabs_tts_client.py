"""ElevenLabs TTS client for multi-speaker dialogue generation.

This client synthesizes each dialogue turn with a deterministic speaker voice,
then concatenates all raw PCM chunks into a single WAV file compatible with the
existing subtitle/render pipeline.
"""

from __future__ import annotations

import logging
import time
import wave
from pathlib import Path

import requests

from pipeline import settings
from pipeline.clients.gemini_tts_client import _trim_long_silences, write_wave_file
from pipeline.utils import iter_dialogue_turns

LOGGER = logging.getLogger(__name__)


class ElevenLabsTTSClient:
    """Client for dialogue TTS generation through ElevenLabs HTTP API."""

    provider_name = "elevenlabs"
    MODEL_ID = "eleven_multilingual_v2"
    SAMPLE_RATE = 24000
    RETRY_DELAYS_SEC = (1.0, 2.0, 4.0)
    MIN_SPEED = 0.7
    MAX_SPEED = 1.2

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("ELEVENLABS_API_KEY is missing.")
        self.api_key = api_key
        configured_speed = settings.ELEVENLABS_SPEED
        self.speed = max(self.MIN_SPEED, min(self.MAX_SPEED, configured_speed))
        if self.speed != configured_speed:
            LOGGER.warning(
                "ELEVENLABS_SPEED %.3f out of range [%.1f, %.1f]; clamped to %.3f",
                configured_speed,
                self.MIN_SPEED,
                self.MAX_SPEED,
                self.speed,
            )

    def _voice_map(self) -> tuple[str, str]:
        speech_cfg = settings.PEDAGOGY_CONFIG.get("speech", {})
        provider_map = speech_cfg.get("voice_map", {}).get("elevenlabs", {})
        if not isinstance(provider_map, dict):
            provider_map = {}

        female_voice = provider_map.get("female", "")
        male_voice = provider_map.get("male", "")

        if not female_voice or not male_voice:
            raise ValueError(
                "speech.voice_map.elevenlabs.female/male must be set with valid ElevenLabs voice IDs."
            )

        return female_voice, male_voice

    def _voice_for(self, speaker_id: str, speaker_genders: dict[str, str] | None = None) -> str:
        female_voice, male_voice = self._voice_map()
        gender = (speaker_genders or {}).get(speaker_id, "").lower()
        if gender == "female":
            return female_voice
        if gender == "male":
            return male_voice
        raise ValueError(
            f"No gender mapping found for {speaker_id!r}. "
            "Ensure script 'speakers' contains a valid gender entry for each speaker."
        )

    def _synthesize_line(self, text: str, voice_id: str) -> bytes:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/octet-stream",
        }
        payload = {
            "text": text,
            "model_id": self.MODEL_ID,
            "voice_settings": {
                "stability": 0.45,
                "similarity_boost": 0.8,
                "style": 0.0,
                "use_speaker_boost": True,
                "speed": self.speed,
            },
        }
        params = {"output_format": "pcm_24000"}

        attempts = 1 + len(self.RETRY_DELAYS_SEC)
        for attempt in range(1, attempts + 1):
            try:
                response = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    params=params,
                    timeout=120,
                )
            except requests.RequestException as err:
                if attempt < attempts:
                    delay = self.RETRY_DELAYS_SEC[attempt - 1]
                    LOGGER.warning(
                        "elevenlabs request failed attempt %d/%d: %s; retry in %.1fs",
                        attempt,
                        attempts,
                        err,
                        delay,
                    )
                    time.sleep(delay)
                    continue
                raise RuntimeError(f"ElevenLabs request failed after retries: {err}") from err

            if response.status_code in (429, 500, 502, 503, 504):
                if attempt < attempts:
                    delay = self.RETRY_DELAYS_SEC[attempt - 1]
                    LOGGER.warning(
                        "elevenlabs retriable status %s attempt %d/%d; retry in %.1fs",
                        response.status_code,
                        attempt,
                        attempts,
                        delay,
                    )
                    time.sleep(delay)
                    continue
                raise RuntimeError(
                    f"ElevenLabs returned status {response.status_code} after retries: {response.text[:200]}"
                )

            if response.status_code in (401, 403):
                raise PermissionError(
                    f"ElevenLabs auth failed with status {response.status_code}: {response.text[:200]}"
                )

            if response.status_code >= 400:
                raise RuntimeError(
                    f"ElevenLabs synthesis failed status {response.status_code}: {response.text[:200]}"
                )

            if not response.content:
                raise RuntimeError("ElevenLabs returned empty audio payload.")

            return response.content

        raise RuntimeError("Unexpected ElevenLabs retry loop termination.")

    def generate_dialogue_audio(
        self,
        dialogue: list[dict[str, str]],
        output_path: str | Path,
        level: str = "A1",
        category: str = "dialogue",
        speaker_genders: dict[str, str] | None = None,
        speaker_roles: dict[str, str] | None = None,
    ) -> bool:
        if not dialogue:
            LOGGER.error("Empty dialogue provided.")
            return False

        turns = iter_dialogue_turns(dialogue)
        if not turns:
            LOGGER.error("No parsable dialogue turns for ElevenLabs generation.")
            return False

        LOGGER.info("Generating ElevenLabs audio for %d turns (speed=%.2f)", len(turns), self.speed)

        pcm_buffers: list[bytes] = []
        try:
            for idx, (speaker, line) in enumerate(turns, start=1):
                voice_id = self._voice_for(speaker, speaker_genders=speaker_genders)
                LOGGER.debug("elevenlabs turn=%d speaker=%s voice_id=%s", idx, speaker, voice_id)
                pcm_buffers.append(self._synthesize_line(line, voice_id))
        except Exception as err:
            LOGGER.error("ElevenLabs dialogue synthesis failed: %s", err)
            return False

        full_pcm = b"".join(pcm_buffers)
        full_pcm = _trim_long_silences(full_pcm, sample_rate=self.SAMPLE_RATE, max_silence_sec=2.0)

        target_file = Path(output_path).with_suffix(".wav")
        write_wave_file(target_file, full_pcm, channels=1, rate=self.SAMPLE_RATE, sample_width=2)
        LOGGER.info("✓ ElevenLabs dialogue audio generated & saved: %s", target_file)
        return True

    def generate_dialogue_audio_with_timestamps(
        self,
        dialogue: list[dict[str, str]],
        output_path: str | Path,
        level: str = "A1",
        category: str = "dialogue",
        speaker_genders: dict[str, str] | None = None,
        speaker_roles: dict[str, str] | None = None,
    ) -> tuple[bool, list[settings.SpeakerTimestamp]]:
        success = self.generate_dialogue_audio(
            dialogue=dialogue,
            output_path=output_path,
            level=level,
            category=category,
            speaker_genders=speaker_genders,
            speaker_roles=speaker_roles,
        )
        if not success:
            return False, []

        if category != "dialogue":
            return True, []

        wav_path = Path(output_path).with_suffix(".wav")
        return True, self._infer_speaker_timestamps(dialogue, wav_path)

    def _infer_speaker_timestamps(
        self,
        dialogue: list[dict[str, str]],
        wav_path: Path | str,
    ) -> list[settings.SpeakerTimestamp]:
        wav_path = Path(wav_path)

        try:
            with wave.open(str(wav_path), "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                total_audio_duration = frames / rate
        except Exception as err:
            LOGGER.error("Failed to read ElevenLabs WAV for timestamps: %s", err)
            return []

        turns = iter_dialogue_turns(dialogue)
        total_words = sum(len(line.split()) for _, line in turns)
        if total_words == 0:
            return []

        timestamps: list[settings.SpeakerTimestamp] = []
        current_time = 0.0
        for speaker, line in turns:
            word_count = len(line.split())
            duration = (word_count / total_words) * total_audio_duration
            timestamps.append(
                settings.SpeakerTimestamp(
                    speaker_id=speaker,
                    start_time=current_time,
                    end_time=current_time + duration,
                )
            )
            current_time += duration

        return timestamps


def create_elevenlabs_client(api_key: str) -> ElevenLabsTTSClient | None:
    try:
        return ElevenLabsTTSClient(api_key)
    except Exception as err:
        LOGGER.error("Could not construct ElevenLabsTTSClient: %s", err)
        return None
