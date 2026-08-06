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
from google.genai import types

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

    FALLBACK_MODEL = "gemini-2.5-flash-preview-tts"
    PRIMARY_MODEL = "gemini-3.1-flash-tts-preview"

    # Recommended word bounds per chunk for optimal prosody & audio fidelity
    TARGET_WORDS_PER_CHUNK = 100
    MAX_WORDS_PER_CHUNK = 130
    FORCE_SINGLE_CHUNK_DIALOGUE = True

    def __init__(self, api_key: str) -> None:
        """Initializes the Gemini TTS Client with an API key.

        Args:
            api_key: Google GenAI API key.
        """
        self.client = genai.Client(api_key=api_key)

    def _load_prompt(
        self,
        dialogue: list[dict[str, str]],
        level: str = "A1",
        category: str = "dialogue",
        speaker_genders: dict[str, str] | None = None,
        speaker_roles: dict[str, str] | None = None,
    ) -> str:
        """Loads prompt template from file and injects formatted dialogue and speaker metadata."""
        level_path = _PROMPTS_DIR / level
        category_pacing = level_path / f"tts_pacing_{category}.md"
        default_pacing = level_path / "tts_pacing.md"
        prompt_file = category_pacing if category_pacing.exists() else default_pacing
        prompt_template = prompt_file.read_text(encoding="utf-8")

        # Substitute speaker metadata placeholders if present in template
        genders = speaker_genders or {}
        roles = speaker_roles or {}
        prompt_template = (
            prompt_template
            .replace("{speaker1_role}", roles.get("Speaker1", "speaker"))
            .replace("{speaker2_role}", roles.get("Speaker2", "speaker"))
            .replace("{speaker1_gender}", genders.get("Speaker1", "female"))
            .replace("{speaker2_gender}", genders.get("Speaker2", "male"))
        )

        formatted_dialogue = "\n\n".join(
            f"{speaker}: {line}"
            for speaker, line in iter_dialogue_turns(dialogue)
            if line
        )

        return prompt_template.replace("{dialogue}", formatted_dialogue)

    def _get_speech_config(self, speaker_genders: dict[str, str] | None = None) -> types.SpeechConfig:
        """Constructs multi-speaker SpeechConfig using gender-based voice selection.

        Args:
            speaker_genders: Mapping of speaker_id to gender, e.g. {"Speaker1": "female", "Speaker2": "male"}.
                             Falls back to positional assignment if not provided.

        Returns:
            Typed SpeechConfig with speaker voice mappings.
        """
        speech_cfg = settings.PEDAGOGY_CONFIG.get("speech", {})
        gemini_voices = speech_cfg.get("voice_map", {}).get("gemini", {})

        # Guardrail: current config schema expects gender keys.
        if not isinstance(gemini_voices, dict):
            LOGGER.warning(
                "Invalid speech.voice_map.gemini config type: %s. Using defaults.",
                type(gemini_voices).__name__,
            )
            gemini_voices = {}
        else:
            missing_gender_keys = [k for k in ("female", "male") if k not in gemini_voices]
            if missing_gender_keys:
                LOGGER.warning(
                    "speech.voice_map.gemini missing keys %s. Expected keys: ['female', 'male']; falling back to defaults where needed.",
                    missing_gender_keys,
                )

        # Gender-based voice selection
        female_voice = gemini_voices.get("female", "Kore")
        male_voice = gemini_voices.get("male", "Puck")

        def _voice_for(speaker_id: str) -> str:
            gender = (speaker_genders or {}).get(speaker_id, "").lower()
            if gender == "female":
                return female_voice
            if gender == "male":
                return male_voice
            # Fallback: Speaker1 → female, Speaker2 → male
            return female_voice if speaker_id == "Speaker1" else male_voice

        s1_voice = _voice_for("Speaker1")
        s2_voice = _voice_for("Speaker2")

        if s1_voice == s2_voice:
            LOGGER.warning(
                "Both speakers resolved to the same voice '%s'. Dialogue may sound single-speaker.",
                s1_voice,
            )

        LOGGER.info("tts.voices Speaker1=%s Speaker2=%s", s1_voice, s2_voice)

        return types.SpeechConfig(
            multi_speaker_voice_config=types.MultiSpeakerVoiceConfig(
                speaker_voice_configs=[
                    types.SpeakerVoiceConfig(
                        speaker="Speaker1",
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=s1_voice,
                            )
                        ),
                    ),
                    types.SpeakerVoiceConfig(
                        speaker="Speaker2",
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=s2_voice,
                            )
                        ),
                    ),
                ]
            )
        )

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

        # Ensure every chunk starts with Speaker1 to prevent voice swap.
        # If a chunk starts with Speaker2, prepend the last Speaker1 line
        # from the preceding chunk as a priming context line.
        last_s1_item: dict[str, str] | None = None
        for i, chunk in enumerate(chunks):
            # Find the first speaker in this chunk
            first_speaker = None
            for item in chunk:
                parsed = iter_dialogue_turns([item])
                if parsed:
                    first_speaker, _ = parsed[0]
                    break

            if first_speaker == "Speaker2" and last_s1_item is not None:
                chunks[i] = [last_s1_item] + chunk
                LOGGER.debug("chunk %d: prepended Speaker1 primer to fix voice order", i + 1)

            # Track last Speaker1 item seen in this chunk
            for item in chunk:
                parsed = iter_dialogue_turns([item])
                if parsed:
                    spk, _ = parsed[0]
                    if spk == "Speaker1":
                        last_s1_item = item

        return chunks

    def generate_dialogue_audio(
        self,
        dialogue: list[dict[str, str]],
        output_path: str | Path,
        level: str = "A1",
        category: str = "dialogue",
        speaker_genders: dict[str, str] | None = None,
        speaker_roles: dict[str, str] | None = None,
    ) -> bool:
        """Generates multi-speaker audio with dynamic quality-focused chunking.

        Args:
            dialogue: List of dialogue dictionaries with speaker and line items.
            output_path: Destination audio file path (.wav).
            level: Pedagogy language proficiency level (e.g., 'A1').
            category: Episode category used to select TTS pacing prompt.
            speaker_genders: Mapping of speaker_id to gender for voice selection.

        Returns:
            True if audio generation and saving succeeded, False otherwise.
        """
        if not dialogue:
            LOGGER.error("Empty dialogue provided.")
            return False

        if category == "dialogue" and self.FORCE_SINGLE_CHUNK_DIALOGUE:
            # Keep one API call for dialogue to avoid cross-chunk speaker timbre drift.
            dialogue_chunks = [dialogue]
            LOGGER.info("dialogue.single_chunk enabled: processing full dialogue in one request")
        else:
            dialogue_chunks = self._chunk_dialogue(
                dialogue,
                target_words=self.TARGET_WORDS_PER_CHUNK,
                max_words=self.MAX_WORDS_PER_CHUNK,
            )
        speech_config = self._get_speech_config(speaker_genders=speaker_genders)

        LOGGER.info(
            "Generating TTS audio in %d chunk(s) using primary model: %s (fallback: %s)",
            len(dialogue_chunks),
            self.PRIMARY_MODEL,
            self.FALLBACK_MODEL,
        )

        pcm_buffers: list[bytes] = []

        for idx, chunk in enumerate(dialogue_chunks, start=1):
            prompt = self._load_prompt(chunk, level=level, category=category, speaker_genders=speaker_genders, speaker_roles=speaker_roles)
            chunk_word_count = sum(len(line.split()) for _, line in iter_dialogue_turns(chunk))

            LOGGER.info(
                "Processing chunk %d/%d (%d dialogue lines, ~%d words)",
                idx,
                len(dialogue_chunks),
                len(chunk),
                chunk_word_count,
            )

            LOGGER.info("tts.prompt.start chunk=%d", idx)
            LOGGER.info("%s", prompt)
            LOGGER.info("tts.prompt.end chunk=%d", idx)

            raw_pcm: bytes | None = None
            for model_name in (self.PRIMARY_MODEL, self.FALLBACK_MODEL):
                try:
                    response = self.client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_modalities=["AUDIO"],
                            speech_config=speech_config,
                        ),
                    )

                    # Extract PCM audio from response parts
                    for part in (response.candidates or [{}])[0].content.parts if response.candidates else []:
                        if hasattr(part, "inline_data") and part.inline_data:
                            data = part.inline_data.data
                            raw_pcm = base64.b64decode(data) if isinstance(data, str) else data
                            break

                    if raw_pcm is not None:
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

    def generate_dialogue_audio_with_timestamps(
        self,
        dialogue: list[dict[str, str]],
        output_path: str | Path,
        level: str = "A1",
        category: str = "dialogue",
        speaker_genders: dict[str, str] | None = None,
        speaker_roles: dict[str, str] | None = None,
    ) -> tuple[bool, list[settings.SpeakerTimestamp]]:
        """Generate multi-speaker audio and return speaker timestamps."""
        success = self.generate_dialogue_audio(dialogue, output_path, level, category, speaker_genders, speaker_roles)
        
        if not success:
            return False, []
        
        # For non-dialogue categories, return empty timestamps
        if category != "dialogue":
            return True, []
        
        # Extract speaker timestamps from actual generated audio
        wav_path = Path(output_path).with_suffix(".wav")
        speaker_timestamps = self._infer_speaker_timestamps(dialogue, wav_path)
        return success, speaker_timestamps

    def _infer_speaker_timestamps(
        self, dialogue: list[dict[str, str]], wav_path: Path | str
    ) -> list[settings.SpeakerTimestamp]:
        """Extract speaker switching points from actual audio duration.
        
        Analyzes the generated WAV file to get real audio duration, then distributes
        speaker time proportionally based on word count in the dialogue.
        
        Args:
            dialogue: List of dialogue dictionaries with speaker and line items.
            wav_path: Path to the generated WAV audio file.
        
        Returns:
            List of SpeakerTimestamp objects with timings based on actual audio.
        """
        wav_path = Path(wav_path)
        
        # Get actual audio duration from WAV file
        try:
            with wave.open(str(wav_path), "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                total_audio_duration = frames / rate
        except Exception as err:
            LOGGER.error(
                "Failed to read audio file %s for timestamp extraction: %s",
                wav_path,
                err,
            )
            return []
        
        # Calculate total words to distribute time proportionally
        speaker_turns = list(iter_dialogue_turns(dialogue))
        total_words = sum(len(line.split()) for _, line in speaker_turns)
        
        if total_words == 0:
            LOGGER.warning("No words found in dialogue for timestamp extraction")
            return []
        
        # Allocate time to each speaker based on word count proportion
        timestamps: list[settings.SpeakerTimestamp] = []
        current_time = 0.0
        
        for speaker, line in speaker_turns:
            word_count = len(line.split())
            # Allocate proportional time based on word count vs total words
            duration = (word_count / total_words) * total_audio_duration
            
            timestamp = settings.SpeakerTimestamp(
                speaker_id=speaker,
                start_time=current_time,
                end_time=current_time + duration,
            )
            timestamps.append(timestamp)
            current_time += duration
        
        LOGGER.info(
            "Extracted %d speaker timestamps from audio (duration %.1f seconds)",
            len(timestamps),
            total_audio_duration,
        )
        return timestamps


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