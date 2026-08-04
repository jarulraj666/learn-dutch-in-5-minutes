"""Gemini TTS Client for multi-speaker dialogue generation.

This module handles audio generation using Google Gemini TTS driven directly
by prompt templates and pipeline configuration settings.
"""

from __future__ import annotations

import base64
import logging
import wave
from pathlib import Path
from typing import Any

from google import genai

from pipeline import settings
from pipeline.utils import iter_dialogue_turns

LOGGER = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"


def _trim_long_silences(
    pcm: bytes,
    sample_rate: int = 24000,
    sample_width: int = 2,
    max_silence_sec: float = 2.0,
    silence_threshold: int = 200,
) -> bytes:
    """Compress runs of silence longer than max_silence_sec down to max_silence_sec.

    Uses a simple amplitude threshold on 16-bit PCM samples.
    Keeps natural pauses intact while removing excessive TTS-generated silence.
    """
    import struct

    samples_per_frame = sample_rate // 100  # 10ms frames
    max_silent_frames = int(max_silence_sec * 100)  # in 10ms units
    bytes_per_sample = sample_width
    frame_bytes = samples_per_frame * bytes_per_sample

    output_frames: list[bytes] = []
    silent_run = 0
    i = 0

    while i + frame_bytes <= len(pcm):
        frame = pcm[i : i + frame_bytes]
        # Check if frame is silent (all samples below threshold)
        samples = struct.unpack(f"<{samples_per_frame}h", frame)
        is_silent = max(abs(s) for s in samples) < silence_threshold

        if is_silent:
            silent_run += 1
            if silent_run <= max_silent_frames:
                output_frames.append(frame)
            # else: drop frame (trim excess silence)
        else:
            silent_run = 0
            output_frames.append(frame)

        i += frame_bytes

    # Append any leftover bytes
    if i < len(pcm):
        output_frames.append(pcm[i:])

    result = b"".join(output_frames)
    trimmed_sec = (len(pcm) - len(result)) / (sample_rate * bytes_per_sample)
    if trimmed_sec > 0.1:
        import logging
        logging.getLogger(__name__).info(
            "silence_trim: removed %.1f s of excess silence from audio", trimmed_sec
        )
    return result


def write_wave_file(
    filename: str | Path,
    pcm_bytes: bytes,
    channels: int = 1,
    rate: int = 24000,
    sample_width: int = 2,
) -> None:
    """Writes raw PCM audio bytes to a WAV container.

    Args:
        filename: Destination path for the WAV file.
        pcm_bytes: Raw PCM audio data.
        channels: Number of audio channels (1 for Mono, 2 for Stereo).
        rate: Sample rate in Hz.
        sample_width: Sample width in bytes (2 bytes = 16-bit PCM).
    """
    output_path = Path(filename)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with wave.open(str(output_path), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm_bytes)


class GeminiTTSClient:
    """Client for multi-speaker TTS dialogue generation via Google Gemini API."""

    PRIMARY_MODEL = "gemini-3.1-flash-tts-preview"
    FALLBACK_MODEL = "gemini-2.5-flash-preview-tts"

    # Recommended word bounds per chunk for optimal prosody & audio fidelity
    TARGET_WORDS_PER_CHUNK = 100
    MAX_WORDS_PER_CHUNK = 130

    def __init__(self, api_key: str) -> None:
        """Initializes the Gemini TTS Client with an API key.

        Args:
            api_key: Google GenAI API key.
        """
        self.client = genai.Client(api_key=api_key)

    def _load_prompt(self, dialogue: list[dict[str, str]], level: str = "A1") -> str:
        """Loads prompt template from file and injects formatted dialogue.

        Args:
            dialogue: List of dialogue dictionaries with 'speaker' and 'line' keys.
            level: Pedagogy language level matching the directory structure.

        Returns:
            The populated prompt string.
        """
        level_path = _PROMPTS_DIR / level / "tts_pacing.md"
        prompt_template = level_path.read_text(encoding="utf-8")

        formatted_dialogue = "\n\n".join(
            f"{speaker}: {line}"
            for speaker, line in iter_dialogue_turns(dialogue)
            if line
        )

        return prompt_template.replace("{dialogue}", formatted_dialogue)

    def _get_speech_config(self) -> list[dict[str, str]]:
        """Constructs speaker configurations directly from pipeline settings.

        Returns:
            List of speaker voice configuration dictionaries.
        """
        speech_cfg = settings.PEDAGOGY_CONFIG.get("speech", {})
        gemini_voices = speech_cfg.get("voice_map", {}).get("gemini", {})

        s1_voice = gemini_voices.get("Speaker1", "Kore")
        s2_voice = gemini_voices.get("Speaker2", "Puck")

        return [
            {"speaker": "Speaker1", "voice": s1_voice},
            {"speaker": "Speaker2", "voice": s2_voice},
        ]

    def _chunk_dialogue(
        self,
        dialogue: list[dict[str, str]],
        target_words: int = TARGET_WORDS_PER_CHUNK,
        max_words: int = MAX_WORDS_PER_CHUNK,
    ) -> list[list[dict[str, str]]]:
        """Groups dialogue lines dynamically based on recommended word bounds.

        Prefers to split at natural section boundaries (new word/topic introductions)
        so the TTS receives complete teaching blocks without mid-block context loss.

        Args:
            dialogue: Full dialogue line entries.
            target_words: Soft word limit target per chunk.
            max_words: Hard ceiling for maximum words per chunk.

        Returns:
            List of chunked dialogue lists.
        """
        import re
        if not dialogue:
            return []

        # Detect lines that start a new teaching block — these are preferred break points.
        _SECTION_START = re.compile(
            r"^(our (first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|\d+\w*)"
            r"|next[, ]|now (let|we)|let'?s (move|look|begin|start)|moving on)",
            re.IGNORECASE,
        )

        def _is_section_start(line: str) -> bool:
            return bool(_SECTION_START.match(line.strip()))

        chunks: list[list[dict[str, str]]] = []
        current_chunk: list[dict[str, str]] = []
        current_word_count = 0
        pending_break = False  # defer break until next section boundary

        for item in dialogue:
            parsed = iter_dialogue_turns([item])
            if not parsed:
                continue
            _, line = parsed[0]
            line_word_count = len(line.split())
            at_boundary = _is_section_start(line)

            # Hard limit: must break regardless of boundary
            hard_limit = current_word_count + line_word_count > max_words

            # Soft limit reached — defer break until next section boundary
            if current_word_count >= target_words and not pending_break:
                pending_break = True

            should_break = (pending_break and at_boundary) or hard_limit

            if should_break and current_chunk:
                chunks.append(current_chunk)
                current_chunk = []
                current_word_count = 0
                pending_break = False

            current_chunk.append(item)
            current_word_count += line_word_count

        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    def generate_dialogue_audio(
        self,
        dialogue: list[dict[str, str]],
        output_path: str | Path,
        level: str = "A1",
    ) -> bool:
        """Generates multi-speaker audio with dynamic quality-focused chunking.

        Args:
            dialogue: List of dialogue dictionaries with speaker and line items.
            output_path: Destination audio file path (.wav).
            level: Pedagogy language proficiency level (e.g., 'A1').

        Returns:
            True if audio generation and saving succeeded, False otherwise.
        """
        if not dialogue:
            LOGGER.error("Empty dialogue provided.")
            return False

        dialogue_chunks = self._chunk_dialogue(
            dialogue,
            target_words=self.TARGET_WORDS_PER_CHUNK,
            max_words=self.MAX_WORDS_PER_CHUNK,
        )
        speech_config = self._get_speech_config()

        LOGGER.info(
            "Generating TTS audio in %d chunk(s) using primary model: %s (fallback: %s)",
            len(dialogue_chunks),
            self.PRIMARY_MODEL,
            self.FALLBACK_MODEL,
        )

        pcm_buffers: list[bytes] = []

        for idx, chunk in enumerate(dialogue_chunks, start=1):
            prompt = self._load_prompt(chunk, level=level)
            chunk_word_count = sum(len(line.split()) for _, line in iter_dialogue_turns(chunk))

            LOGGER.info(
                "Processing chunk %d/%d (%d dialogue lines, ~%d words)",
                idx,
                len(dialogue_chunks),
                len(chunk),
                chunk_word_count,
            )

            raw_pcm: bytes | None = None
            for model_name in (self.PRIMARY_MODEL, self.FALLBACK_MODEL):
                try:
                    interaction = self.client.interactions.create(
                        model=model_name,
                        input=prompt,
                        response_format={"type": "audio"},
                        generation_config={
                            "speech_config": speech_config,
                        },
                    )

                    if hasattr(interaction, "output_audio") and interaction.output_audio:
                        data = interaction.output_audio.data
                        raw_pcm = base64.b64decode(data) if isinstance(data, str) else data

                        if model_name == self.FALLBACK_MODEL:
                            LOGGER.warning(
                                "Successfully generated chunk %d using fallback model: %s",
                                idx,
                                model_name,
                            )
                        break
                except Exception as err:
                    if model_name == self.PRIMARY_MODEL:
                        LOGGER.warning(
                            "Primary model %s failed for chunk %d: %s. Retrying with fallback %s...",
                            self.PRIMARY_MODEL,
                            idx,
                            err,
                            self.FALLBACK_MODEL,
                        )
                    else:
                        LOGGER.error(
                            "Fallback model %s also failed for chunk %d: %s",
                            self.FALLBACK_MODEL,
                            idx,
                            err,
                        )

            if raw_pcm is None:
                LOGGER.error("Failed to generate audio for chunk %d with primary & fallback models.", idx)
                return False

            pcm_buffers.append(raw_pcm)

        # Write concatenated audio with silence trimming
        full_pcm = b"".join(pcm_buffers)
        full_pcm = _trim_long_silences(full_pcm, sample_rate=24000, max_silence_sec=2.0)
        target_file = Path(output_path).with_suffix(".wav")
        write_wave_file(target_file, full_pcm, channels=1, rate=24000, sample_width=2)

        LOGGER.info("✓ Full dialogue audio generated & saved: %s", target_file)
        return True


def create_gemini_client(api_key: str) -> GeminiTTSClient | None:
    """Factory helper to instantiate GeminiTTSClient.

    Args:
        api_key: Google GenAI API key.

    Returns:
        Instantiated client or None if initialization fails.
    """
    try:
        return GeminiTTSClient(api_key)
    except Exception as err:
        LOGGER.error("Could not construct GeminiTTSClient: %s", err)
        return None