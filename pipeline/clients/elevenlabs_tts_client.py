"""ElevenLabs TTS client for multi-speaker dialogue generation.

This client synthesizes each dialogue turn with a deterministic speaker voice,
then concatenates all raw PCM chunks into a single WAV file compatible with the
existing subtitle/render pipeline.
"""

from __future__ import annotations

import logging
import random
import re
import time
import wave
from pathlib import Path

import requests

from pipeline import settings
from pipeline.clients.gemini_tts_client import write_wave_file
from pipeline.utils import iter_dialogue_turns

LOGGER = logging.getLogger(__name__)


class ElevenLabsTTSClient:
    """Client for dialogue TTS generation through ElevenLabs HTTP API."""

    provider_name = "elevenlabs"
    MODEL_ID = "eleven_flash_v2_5"
    SAMPLE_RATE = 24000
    RETRY_DELAYS_SEC = (1.0, 2.0, 4.0)
    MIN_SPEED = 0.7
    MAX_SPEED = 1.2

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("ELEVENLABS_API_KEY is missing.")
        self.api_key = api_key
        self.model_id = settings.ELEVENLABS_MODEL or self.MODEL_ID
        configured_speed = settings.ELEVENLABS_SPEED
        self.speed = max(self.MIN_SPEED, min(self.MAX_SPEED, configured_speed))
        self.sentence_pause_seconds = settings.ELEVENLABS_SENTENCE_PAUSE_SECONDS
        if self.speed != configured_speed:
            LOGGER.warning(
                "ELEVENLABS_SPEED %.3f out of range [%.1f, %.1f]; clamped to %.3f",
                configured_speed,
                self.MIN_SPEED,
                self.MAX_SPEED,
                self.speed,
            )

    def _voice_map(self) -> dict[str, list[str]]:
        speech_cfg = settings.PEDAGOGY_CONFIG.get("speech", {})
        provider_map = speech_cfg.get("voice_map", {}).get("elevenlabs", {})
        if not isinstance(provider_map, dict):
            provider_map = {}

        selected_plan = settings.ELEVENLABS_VOICE_PLAN
        if selected_plan not in ("free", "paid"):
            LOGGER.warning(
                "Invalid ELEVENLABS_VOICE_PLAN=%r. Expected 'free' or 'paid'. Falling back to 'free'.",
                selected_plan,
            )
            selected_plan = "free"

        # Preferred shape:
        # elevenlabs:
        #   free: {female: [...], male: [...]}
        #   paid: {female: [...], male: [...]}
        # Backward compatible shape:
        # elevenlabs: {female: [...], male: [...]}.
        plan_map = provider_map.get(selected_plan)
        if isinstance(plan_map, dict):
            effective_map = plan_map
            LOGGER.info("elevenlabs.voice_plan=%s", selected_plan)
        else:
            effective_map = provider_map
            LOGGER.info("elevenlabs.voice_plan=%s (fallback: legacy flat map)", selected_plan)

        voice_map: dict[str, list[str]] = {}
        for gender in ("female", "male"):
            configured = effective_map.get(gender, [])
            if isinstance(configured, str):
                configured = [configured]
            if not isinstance(configured, list):
                configured = []
            voices = list(dict.fromkeys(
                voice for voice in configured if isinstance(voice, str) and voice.strip()
            ))
            if not voices:
                raise ValueError(
                    f"speech.voice_map.elevenlabs.{selected_plan}.{gender} must be set with valid ElevenLabs voice IDs."
                )
            voice_map[gender] = voices

        return voice_map

    def _voice_assignments(
        self,
        speakers: list[str],
        speaker_genders: dict[str, str] | None = None,
    ) -> dict[str, str]:
        voice_map = self._voice_map()
        speakers_by_gender: dict[str, list[str]] = {"female": [], "male": []}
        for speaker in speakers:
            gender = (speaker_genders or {}).get(speaker, "").lower()
            if gender not in speakers_by_gender:
                raise ValueError(
                    f"No gender mapping found for {speaker!r}. "
                    "Ensure script 'speakers' contains a valid gender entry for each speaker."
                )
            if speaker not in speakers_by_gender[gender]:
                speakers_by_gender[gender].append(speaker)

        assignments: dict[str, str] = {}
        for gender, gender_speakers in speakers_by_gender.items():
            voices = voice_map[gender]
            if len(gender_speakers) > len(voices):
                raise ValueError(
                    f"Not enough distinct ElevenLabs {gender} voices for speakers: "
                    f"{', '.join(gender_speakers)}. Configure at least "
                    f"{len(gender_speakers)} distinct voices."
                )
            assignments.update(zip(gender_speakers, random.sample(voices, len(gender_speakers))))

        return assignments

    def _speaker_gender_map(
        self,
        speakers: list[str],
        speaker_genders: dict[str, str] | None = None,
    ) -> dict[str, str]:
        gender_map: dict[str, str] = {}
        for speaker in speakers:
            gender = (speaker_genders or {}).get(speaker, "").lower()
            if gender not in ("female", "male"):
                raise ValueError(
                    f"No gender mapping found for {speaker!r}. "
                    "Ensure script 'speakers' contains a valid gender entry for each speaker."
                )
            gender_map[speaker] = gender
        return gender_map

    @staticmethod
    def _is_paid_plan_required_error(err: Exception) -> bool:
        msg = str(err).lower()
        return "paid_plan_required" in msg or "payment_required" in msg

    def _choose_fallback_voice(
        self,
        speaker: str,
        voice_assignments: dict[str, str],
        voice_map: dict[str, list[str]],
        speaker_gender_map: dict[str, str],
        blocked_by_speaker: dict[str, set[str]],
    ) -> str | None:
        gender = speaker_gender_map[speaker]
        candidates = [
            voice
            for voice in voice_map[gender]
            if voice not in blocked_by_speaker[speaker]
        ]
        if not candidates:
            return None

        peer_voices = {
            assigned_voice
            for other_speaker, assigned_voice in voice_assignments.items()
            if other_speaker != speaker
            and speaker_gender_map.get(other_speaker) == gender
        }
        distinct_candidates = [voice for voice in candidates if voice not in peer_voices]
        pool = distinct_candidates or candidates
        return random.choice(pool)

    def _voice_for(self, speaker_id: str, speaker_genders: dict[str, str] | None = None) -> str:
        assignments = self._voice_assignments([speaker_id], speaker_genders=speaker_genders)
        return assignments[speaker_id]

    def _synthesize_line(self, text: str, voice_id: str) -> bytes:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/octet-stream",
        }
        payload = {
            "text": text,
            "model_id": self.model_id,
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
                    f"ElevenLabs synthesis failed voice={voice_id} status {response.status_code}: {response.text[:200]}"
                )

            if not response.content:
                raise RuntimeError("ElevenLabs returned empty audio payload.")

            return response.content

        raise RuntimeError("Unexpected ElevenLabs retry loop termination.")

    def _sentence_pause_pcm(self) -> bytes:
        samples = round(self.SAMPLE_RATE * self.sentence_pause_seconds)
        return b"\x00" * (samples * 2)

    @staticmethod
    def _sentences(text: str) -> list[str]:
        return [sentence for sentence in re.split(r"(?<=[.!?])\s+", text.strip()) if sentence]

    def generate_dialogue_audio(
        self,
        dialogue: list[dict[str, str]],
        output_path: str | Path,
        level: str = "A1A2",
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

        LOGGER.info(
            "Generating ElevenLabs audio for %d turns (speed=%.2f, model=%s)",
            len(turns),
            self.speed,
            self.model_id,
        )

        pcm_buffers: list[bytes] = []
        try:
            speakers = [speaker for speaker, _ in turns]
            voice_map = self._voice_map()
            speaker_gender_map = self._speaker_gender_map(
                speakers,
                speaker_genders=speaker_genders,
            )
            voice_assignments = self._voice_assignments(
                speakers,
                speaker_genders=speaker_genders,
            )
            for speaker in sorted(voice_assignments.keys()):
                LOGGER.info(
                    "elevenlabs.voice_assignment speaker=%s gender=%s voice_id=%s",
                    speaker,
                    speaker_gender_map.get(speaker, "unknown"),
                    voice_assignments[speaker],
                )
            blocked_by_speaker = {
                speaker: set() for speaker in speaker_gender_map
            }
            for idx, (speaker, line) in enumerate(turns, start=1):
                for sentence in self._sentences(line):
                    if pcm_buffers:
                        pcm_buffers.append(self._sentence_pause_pcm())
                    while True:
                        voice_id = voice_assignments[speaker]
                        LOGGER.debug("elevenlabs turn=%d speaker=%s voice_id=%s", idx, speaker, voice_id)
                        try:
                            synthesized_line = self._synthesize_line(sentence, voice_id)
                            pcm_buffers.append(synthesized_line)
                            break
                        except Exception as err:
                            if not self._is_paid_plan_required_error(err):
                                raise
                            blocked_by_speaker[speaker].add(voice_id)
                            fallback_voice = self._choose_fallback_voice(
                                speaker,
                                voice_assignments,
                                voice_map,
                                speaker_gender_map,
                                blocked_by_speaker,
                            )
                            if not fallback_voice:
                                raise RuntimeError(
                                    f"ElevenLabs paid-plan voice rejected for {speaker}; "
                                    "no eligible fallback voice remains in configured pool."
                                ) from err
                            LOGGER.warning(
                                "elevenlabs.voice_switch turn=%d speaker=%s from=%s to=%s reason=paid_plan_required",
                                idx,
                                speaker,
                                voice_id,
                                fallback_voice,
                            )
                            voice_assignments[speaker] = fallback_voice
        except Exception as err:
            LOGGER.error("ElevenLabs dialogue synthesis failed: %s", err)
            return False

        full_pcm = b"".join(pcm_buffers)

        target_file = Path(output_path).with_suffix(".wav")
        write_wave_file(target_file, full_pcm, channels=1, rate=self.SAMPLE_RATE, sample_width=2)
        LOGGER.info("✓ ElevenLabs dialogue audio generated & saved: %s", target_file)
        return True

    def generate_dialogue_audio_with_timestamps(
        self,
        dialogue: list[dict[str, str]],
        output_path: str | Path,
        level: str = "A1A2",
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
