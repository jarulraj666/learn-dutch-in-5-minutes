"""
Gemini TTS Client for multi-speaker dialogue generation.

This module provides a dedicated client for generating audio from full
conversation dialogues using Google Gemini 3.1 Flash TTS with multi-speaker support.
"""

import logging
import base64
import wave
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_TTS_PACING_PROMPT_FILE = _PROMPTS_DIR / "tts_pacing_prompt.md"


def _load_tts_prompt_template() -> str:
    """Load TTS pacing prompt template from file."""
    try:
        return _TTS_PACING_PROMPT_FILE.read_text(encoding="utf-8")
    except Exception as e:
        LOGGER.warning("Could not load TTS prompt template from %s: %s", _TTS_PACING_PROMPT_FILE, e)
        return "{dialogue}"


class GeminiTTSClient:
    """Client for generating multi-speaker audio from dialogue using Gemini TTS."""
    
    # Model variants — gemini-3.1-flash-tts-preview supports streaming & interactions API
    PRIMARY_MODEL = "gemini-3.1-flash-tts-preview"
    FALLBACK_MODEL = "gemini-2.5-flash-preview-tts"
    
    # Voice mapping for different languages and speaker roles
    # SpeakerA = male (Rasalgethi — Informative): knowledgeable teacher
    # SpeakerB = female (Sulafat — Warm): warm, encouraging language partner
    VOICE_MAP = {
        "nl": {
            "SpeakerA": "Rasalgethi",   # Male — Informative
            "SpeakerB": "Sulafat"        # Female — Warm
        },
        "en": {
            "SpeakerA": "Rasalgethi",   # Male — Informative
            "SpeakerB": "Sulafat"        # Female — Warm
        }
    }
    
    # Default audio parameters (Gemini TTS outputs PCM 24kHz mono)
    AUDIO_CHANNELS = 1
    AUDIO_SAMPLE_WIDTH = 2  # 16-bit
    AUDIO_SAMPLE_RATE = 24000
    
    def __init__(self, api_key: str):
        """Initialize Gemini TTS client.
        
        Args:
            api_key: Google Gemini API key
        """
        try:
            from google import genai
            self.client = genai.Client(api_key=api_key)
            self.api_available = True
        except ImportError:
            LOGGER.error("google-genai SDK not available. Install with: pip install google-genai")
            self.api_available = False
        except Exception as e:
            LOGGER.error("Failed to initialize Gemini client: %s", str(e))
            self.api_available = False
    
    def format_dialogue(self, dialogue: list[dict], language: str = "nl") -> str:
        """Format dialogue list into conversation text for Gemini TTS.
        
        Args:
            dialogue: List of dialogue items with 'speaker' and 'line' fields
            language: Language code (nl, en)
        
        Returns:
            Formatted dialogue string ready for TTS
        """
        if not dialogue:
            LOGGER.error("Empty dialogue provided")
            return ""
        
        lines = []
        for item in dialogue:
            speaker = item.get("speaker", "Unknown")
            text = item.get("line", "")

            if text:
                lines.append(f"{speaker}: {text}")

        formatted = "\n\n".join(lines)
        LOGGER.debug("Formatted dialogue (%d lines, %d chars)", len(lines), len(formatted))
        return formatted
    
    def generate_dialogue_audio(
        self,
        dialogue: list[dict],
        output_path: str,
        language: str = "nl"
    ) -> bool:
        """Generate audio from full dialogue using Gemini TTS.
        
        Args:
            dialogue: List of dialogue items {'speaker': 'SpeakerA'/'SpeakerB', 'line': 'text'}
            output_path: Output WAV file path
            language: Language code (nl for Dutch, en for English)
        
        Returns:
            True if successful, False otherwise
        """
        if not self.api_available:
            LOGGER.error("Gemini TTS API not available")
            return False
        
        try:
            # Format dialogue
            dialogue_text = self.format_dialogue(dialogue, language)
            if not dialogue_text:
                LOGGER.error("Failed to format dialogue")
                return False
            
            LOGGER.info("Generating multi-speaker audio for %d dialogue lines", len(dialogue))
            
            # Get voice configuration for speakers
            voices = self.VOICE_MAP.get(language, self.VOICE_MAP["en"])
            
            # Build speaker configuration
            speakers = []
            seen_speakers = set()
            for item in dialogue:
                speaker = item.get("speaker", "SpeakerA")
                if speaker not in seen_speakers:
                    voice = voices.get(speaker, "Kore")
                    speakers.append({"speaker": speaker, "voice": voice})
                    seen_speakers.add(speaker)
                    LOGGER.debug("Adding speaker: %s → voice: %s", speaker, voice)
            
            # Load prompt template from file and inject dialogue
            prompt_template = _load_tts_prompt_template()
            prompt = prompt_template.replace("{dialogue}", dialogue_text)

            LOGGER.debug("Calling Gemini TTS with %d speakers", len(speakers))
            LOGGER.debug("Prompt length: %d chars", len(prompt))

            # Flat speech_config list as required by the Interactions API
            speech_config = [
                {"speaker": s["speaker"], "voice": s["voice"]}
                for s in speakers
            ]

            import base64
            from google.genai import types

            # Attempt strategies in order:
            # 1. Interactions API with gemini-3.1-flash-tts-preview (recommended)
            # 2. generateContent API with gemini-2.5-flash-preview-tts (fallback)
            strategies = [
                ("interactions", self.PRIMARY_MODEL),
                ("generate_content", self.FALLBACK_MODEL),
            ]

            for strategy, model_name in strategies:
                try:
                    LOGGER.info("Attempting Gemini TTS — strategy=%s model=%s", strategy, model_name)

                    if strategy == "interactions":
                        # Interactions API: returns base64 audio in interaction.output_audio.data
                        interaction = self.client.interactions.create(
                            model=model_name,
                            input=prompt,
                            response_format={"type": "audio"},
                            generation_config={"speech_config": speech_config},
                        )
                        if not interaction or not getattr(interaction, "output_audio", None):
                            LOGGER.error("No audio output in Gemini Interactions response")
                            continue
                        if not getattr(interaction.output_audio, "data", None):
                            LOGGER.error("Empty audio data in Gemini Interactions response")
                            continue
                        audio_bytes = base64.b64decode(interaction.output_audio.data)

                    else:
                        # generateContent API: returns raw PCM bytes in inline_data.data
                        speaker_voice_configs = [
                            types.SpeakerVoiceConfig(
                                speaker=s["speaker"],
                                voice_config=types.VoiceConfig(
                                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=s["voice"])
                                ),
                            )
                            for s in speakers
                        ]
                        response = self.client.models.generate_content(
                            model=model_name,
                            contents=prompt,
                            config=types.GenerateContentConfig(
                                response_modalities=["AUDIO"],
                                speech_config=types.SpeechConfig(
                                    multi_speaker_voice_config=types.MultiSpeakerVoiceConfig(
                                        speaker_voice_configs=speaker_voice_configs
                                    )
                                ),
                            ),
                        )
                        try:
                            audio_bytes = response.candidates[0].content.parts[0].inline_data.data
                        except Exception as extract_err:
                            LOGGER.error("Failed to extract audio from generateContent response: %s", extract_err)
                            continue
                    
                    if not audio_bytes:
                        LOGGER.error("Decoded audio is empty")
                        continue
                    
                    LOGGER.info("Received audio: %d bytes from %s", len(audio_bytes), model_name)
                    
                    # Save as WAV file
                    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                    wav_path = str(Path(output_path).with_suffix(".wav"))
                    
                    try:
                        with wave.open(wav_path, "wb") as wf:
                            wf.setnchannels(self.AUDIO_CHANNELS)
                            wf.setsampwidth(self.AUDIO_SAMPLE_WIDTH)
                            wf.setframerate(self.AUDIO_SAMPLE_RATE)
                            wf.writeframes(audio_bytes)
                        
                        file_size = Path(wav_path).stat().st_size
                        duration_sec = len(audio_bytes) / (self.AUDIO_SAMPLE_RATE * self.AUDIO_SAMPLE_WIDTH)
                        
                        LOGGER.info("✓ Saved dialogue audio: %s (%d bytes, %.1f sec) using %s", 
                                   wav_path, file_size, duration_sec, model_name)
                        return True
                    
                    except Exception as wav_err:
                        LOGGER.error("Failed to write WAV file: %s", str(wav_err))
                        continue
                
                except Exception as api_err:
                    error_msg = str(api_err)
                    if "429" in error_msg or "quota" in error_msg.lower():
                        LOGGER.warning("Gemini quota exceeded (429) on %s/%s, trying next strategy",
                                       strategy, model_name)
                        continue
                    if "400" in error_msg or "invalid" in error_msg.lower():
                        LOGGER.warning("Gemini API error (400) on %s/%s: %s",
                                       strategy, model_name, error_msg[:100])
                        continue
                    LOGGER.error("Gemini TTS error on %s/%s: %s", strategy, model_name, error_msg)
                    continue
            
            # All models attempted and failed
            LOGGER.error("All Gemini TTS models failed to generate audio")
            return False
        
        except Exception as e:
            LOGGER.error("Error generating dialogue audio: %s", str(e))
            import traceback
            LOGGER.debug("Traceback: %s", traceback.format_exc())
            return False
    
    def generate_dialogue_with_fallback(
        self,
        dialogue: list[dict],
        output_path: str,
        language: str = "nl",
        fallback_provider = None
    ) -> bool:
        """Generate audio with fallback support.
        
        Args:
            dialogue: List of dialogue items
            output_path: Output WAV file path
            language: Language code
            fallback_provider: Callable fallback function (e.g., Parkiet client)
        
        Returns:
            True if successful (either Gemini or fallback)
        """
        success = self.generate_dialogue_audio(dialogue, output_path, language)
        
        if not success and fallback_provider:
            LOGGER.info("Gemini TTS failed, trying fallback provider")
            try:
                # Fallback: Try generating segments individually with fallback provider
                for item in dialogue:
                    success = fallback_provider(item.get("line", ""), item.get("speaker", "SpeakerA"))
                    if not success:
                        LOGGER.warning("Fallback provider also failed for segment: %s", item)
                        return False
                return True
            except Exception as e:
                LOGGER.error("Fallback provider error: %s", str(e))
                return False
        
        return success


def create_gemini_client(api_key: str) -> GeminiTTSClient | None:
    """Factory function to create Gemini TTS client.
    
    Args:
        api_key: Google Gemini API key
    
    Returns:
        GeminiTTSClient instance or None if initialization fails
    """
    try:
        client = GeminiTTSClient(api_key)
        if client.api_available:
            return client
        return None
    except Exception as e:
        LOGGER.error("Failed to create Gemini TTS client: %s", str(e))
        return None
