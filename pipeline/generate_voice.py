from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any
import urllib.request
import logging

from pipeline import settings
from pipeline.utils import command_exists

LOGGER = logging.getLogger(__name__)

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

try:
    from kokoro_onnx import Kokoro as KokoroOnnx
    import soundfile as sf
    KOKORO_AVAILABLE = True
except ImportError:
    KOKORO_AVAILABLE = False

try:
    from transformers import pipeline as transformers_pipeline
    PARKIET_AVAILABLE = True
except ImportError:
    PARKIET_AVAILABLE = False

try:
    from pipeline.remote_parkiet_client import RemoteParkietClient
    REMOTE_PARKIET_AVAILABLE = True
except ImportError:
    REMOTE_PARKIET_AVAILABLE = False

try:
    from pipeline.gemini_tts_client import create_gemini_client
    GEMINI_CLIENT_AVAILABLE = True
except ImportError:
    GEMINI_CLIENT_AVAILABLE = False

_kokoro_instance = None  # Cache Kokoro TTS instance
_gemini_client = None  # Lazy-load Gemini TTS client
_KOKORO_MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
_KOKORO_VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"
_KOKORO_CACHE_DIR = Path.home() / ".cache" / "kokoro_onnx"


def _estimate_duration_seconds(text: str) -> float:
    # Simple estimate for subtitle timing fallback: ~2.6 words/sec plus a pause.
    words = max(1, len(text.split()))
    return max(1.2, words / 2.6 + 0.25)


def _get_voice_map(provider: str) -> dict[str, str]:
    """Get voice mapping for the specified TTS provider."""
    speech_cfg = settings.PEDAGOGY_CONFIG.get("speech", {})
    voice_maps = speech_cfg.get("voice_map", {})
    return voice_maps.get(provider, {})


def _generate_macos_say(text: str, speaker: str, voice: str, speech_rate: str, output_path: str) -> bool:
    """Generate audio using macOS say command."""
    try:
        subprocess.run(
            [
                "say",
                "-v",
                voice,
                "-r",
                speech_rate,
                "-o",
                output_path,
                text,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return True
    except Exception as e:
        print(f"Error generating audio with macOS say: {e}")
        return False


def _generate_gemini_tts(text: str, speaker: str, voice: str, output_path: str, language: str = "nl") -> bool:
    """Generate audio using Google Gemini TTS via models.generate_content() API."""
    if not settings.GEMINI_API_KEY:
        LOGGER.error("GEMINI_API_KEY environment variable not set")
        return False

    try:
        from google import genai
        from google.genai import types
        import wave

        client = genai.Client(api_key=settings.GEMINI_API_KEY)

        LOGGER.debug("Generating Gemini TTS audio for: %s (speaker=%s, language=%s)",
                     text[:50], speaker, language)

        voice_map = {
            "nl": {"SpeakerA": "Rasalgethi", "SpeakerB": "Sulafat"},
            "en": {"SpeakerA": "Rasalgethi", "SpeakerB": "Sulafat"},
        }
        gemini_voice = voice_map.get(language, voice_map["en"]).get(speaker, "Kore")

        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash-preview-tts",
                contents=text,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=gemini_voice
                            )
                        )
                    ),
                ),
            )
        except Exception as api_err:
            error_msg = str(api_err)
            if "429" in error_msg or "quota" in error_msg.lower():
                LOGGER.warning("Gemini TTS quota exceeded, falling back to Parkiet")
                colab_url = os.getenv("PARKIET_COLAB_URL") or getattr(settings, "PARKIET_COLAB_URL", None)
                if colab_url and REMOTE_PARKIET_AVAILABLE:
                    return _generate_remote_parkiet_tts(text, speaker, voice, output_path, colab_url)
                elif PARKIET_AVAILABLE:
                    return _generate_parkiet_tts(text, speaker, voice, output_path, tts_rate_wpm=65)
                LOGGER.error("Parkiet fallback also unavailable")
                return False
            LOGGER.error("Gemini API error: %s", error_msg[:200])
            return False

        # Extract audio bytes from response (inline_data.data is already raw PCM bytes)
        try:
            audio_bytes = response.candidates[0].content.parts[0].inline_data.data
        except Exception as extract_err:
            LOGGER.error("Failed to extract audio from Gemini response: %s", str(extract_err))
            return False

        if not audio_bytes:
            LOGGER.error("Decoded audio data is empty")
            return False

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        wav_path = str(Path(output_path).with_suffix(".wav"))

        try:
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(24000)
                wf.writeframes(audio_bytes)
        except Exception as wav_err:
            LOGGER.error("Failed to write WAV: %s", str(wav_err))
            return False

        LOGGER.info("✓ Generated Gemini TTS audio: %s (%d bytes)", wav_path, len(audio_bytes))
        return True

    except Exception as e:
        LOGGER.error("Error generating audio with Gemini TTS: %s", str(e))
        return False


def _wpm_to_speed(tts_rate_wpm: int, baseline_wpm: int = 150) -> float:
    """Convert words-per-minute rate to kokoro-onnx speed multiplier."""
    speed = tts_rate_wpm / baseline_wpm
    return round(max(0.5, min(2.0, speed)), 2)  # Clamp to [0.5, 2.0]


def _ensure_kokoro_models() -> tuple[str, str] | None:
    """Download Kokoro models if they don't exist. Returns (model_path, voices_path) or None if failed."""
    _KOKORO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    
    model_path = _KOKORO_CACHE_DIR / "kokoro-v1.0.onnx"
    voices_path = _KOKORO_CACHE_DIR / "voices-v1.0.bin"
    
    # Check if models already exist
    if model_path.exists() and voices_path.exists():
        print(f"Kokoro models found in cache: {_KOKORO_CACHE_DIR}")
        return (str(model_path), str(voices_path))
    
    # Download models
    print(f"Downloading Kokoro models to {_KOKORO_CACHE_DIR}...")
    try:
        if not model_path.exists():
            print(f"Downloading kokoro model from {_KOKORO_MODEL_URL}")
            urllib.request.urlretrieve(_KOKORO_MODEL_URL, str(model_path))
            print(f"Downloaded: {model_path}")
        
        if not voices_path.exists():
            print(f"Downloading voices from {_KOKORO_VOICES_URL}")
            urllib.request.urlretrieve(_KOKORO_VOICES_URL, str(voices_path))
            print(f"Downloaded: {voices_path}")
        
        return (str(model_path), str(voices_path))
    except Exception as e:
        print(f"Failed to download Kokoro models: {e}")
        return None


def _generate_kokoro_tts(text: str, speaker: str, voice: str, output_path: str, language: str = "en", tts_rate_wpm: int = 150) -> bool:
    """Generate audio using local Kokoro ONNX TTS."""
    if not KOKORO_AVAILABLE:
        print("Kokoro TTS not installed. Install with: pip install kokoro-onnx soundfile")
        return False
    
    try:
        global _kokoro_instance
        
        # Initialize Kokoro TTS if not already done (for performance)
        if _kokoro_instance is None:
            # Ensure models are downloaded
            models = _ensure_kokoro_models()
            if models is None:
                print("Failed to download Kokoro models")
                return False
            
            model_path, voices_path = models
            _kokoro_instance = KokoroOnnx(model_path, voices_path)
        
        # Map language to kokoro-onnx lang code
        lang_code = "nl" if language == "nl" else "en-us"
        if "nl" in voice.lower():
            lang_code = "nl"
        
        # Convert WPM from config to kokoro speed multiplier
        speed = _wpm_to_speed(tts_rate_wpm)
        
        # Generate audio samples
        samples, sample_rate = _kokoro_instance.create(
            text=text,
            voice=voice,
            speed=speed,
            lang=lang_code,
        )
        
        # Save audio to wav file
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        # Use .wav extension for kokoro-onnx output
        wav_path = str(Path(output_path).with_suffix(".wav"))
        sf.write(wav_path, samples, sample_rate)
        
        # If original path was .aiff, update to .wav (ffmpeg handles wav fine)
        if output_path != wav_path:
            import os
            # Rename the segment path to .wav
            output_path = wav_path
        
        return True
    except Exception as e:
        print(f"Error generating audio with Kokoro ONNX TTS: {e}")
        return False


def _generate_parkiet_tts(text: str, speaker: str, voice: str, output_path: str, tts_rate_wpm: int = 65) -> bool:
    """Generate audio using Parkiet Dutch TTS via transformers."""
    if not PARKIET_AVAILABLE:
        print("Parkiet TTS not installed. Install with: pip install transformers torch")
        return False
    
    try:
        import numpy as np
        
        # Load the parkiet TTS pipeline
        # Using the HF transformers version: https://huggingface.co/pevers/parkiet
        tts = transformers_pipeline("text-to-speech", model="pevers/parkiet")
        
        # Map speaker to parkiet speaker tags ([S1] or [S2])
        speaker_tag = "[S1]" if speaker == "SpeakerA" else "[S2]"
        
        # Format text with speaker tag
        formatted_text = f"{speaker_tag} {text}"
        
        # Generate audio
        result = tts(formatted_text)
        
        # Extract audio samples and sample rate
        audio_array = np.array(result.get("audio", []), dtype=np.float32)
        sample_rate = result.get("sampling_rate", 22050)
        
        if audio_array.size == 0:
            print(f"Parkiet generated empty audio for: {text}")
            return False
        
        # Save audio to wav file
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        wav_path = str(Path(output_path).with_suffix(".wav"))
        
        import soundfile as sf
        sf.write(wav_path, audio_array, sample_rate)
        
        return True
    except Exception as e:
        print(f"Error generating audio with Parkiet TTS: {e}")
        return False


def _generate_remote_parkiet_tts(text: str, speaker: str, voice: str, output_path: str, colab_url: str) -> bool:
    """Generate audio using remote Parkiet TTS on Google Colab via ngrok tunnel."""
    if not REMOTE_PARKIET_AVAILABLE:
        LOGGER.error("Remote Parkiet client not available. Install with: pip install requests")
        return False
    
    try:
        # Create client
        client = RemoteParkietClient(colab_url)
        
        # Map speaker to parkiet speaker tags ([S1] or [S2])
        speaker_tag = "[S1]" if speaker == "SpeakerA" else "[S2]"
        
        # Generate audio (client returns bytes)
        audio_bytes = client.generate_speech(text, speaker=speaker_tag)
        
        if not audio_bytes:
            LOGGER.error("Remote Parkiet returned empty audio for: %s", text)
            return False
        
        # Save audio to wav file
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        wav_path = str(Path(output_path).with_suffix(".wav"))
        
        with open(wav_path, "wb") as f:
            f.write(audio_bytes)
        
        LOGGER.debug("Saved remote Parkiet audio to %s", wav_path)
        return True
    
    except Exception as e:
        LOGGER.error("Error generating audio with remote Parkiet TTS: %s", str(e))
        return False


def generate_voice_assets(script: dict[str, Any], output_root: str = "output") -> dict[str, Any]:
    dialogue = script.get("dialogue", [])
    voice_dir = f"{output_root}/audio"
    
    # Create audio directory
    Path(voice_dir).mkdir(parents=True, exist_ok=True)

    segments = []
    speech_cfg = settings.PEDAGOGY_CONFIG.get("speech", {})
    
    # Get language setting
    language = speech_cfg.get("language", "en")  # Get language setting (en or nl)
    
    # Select TTS provider based on language if language_provider_map is defined
    language_provider_map = speech_cfg.get("language_provider_map", {})
    if language_provider_map and language in language_provider_map:
        tts_provider = language_provider_map[language]
    else:
        # Fall back to default tts_provider
        tts_provider = speech_cfg.get("tts_provider") or settings.TTS_PROVIDER
    
    tts_rate_wpm = int(speech_cfg.get("tts_rate_wpm", 105))
    speech_rate = str(tts_rate_wpm)  # Used by macos say (-r flag)
    
    # Get voice map for the selected provider
    voice_maps = speech_cfg.get("voice_map", {})
    provider_voices = voice_maps.get(tts_provider, {})
    
    # Handle nested voice maps (for providers with language-specific voices like Gemini)
    if language in provider_voices:
        # Provider has language-specific voices
        voice_map = provider_voices[language]
    elif isinstance(provider_voices, dict) and all(k in ["SpeakerA", "SpeakerB"] for k in provider_voices.keys()):
        # Simple voice map (non-language-specific)
        voice_map = provider_voices
    else:
        voice_map = {}

    # SPECIAL HANDLING FOR GEMINI TTS: Generate full dialogue at once
    if tts_provider == "gemini":
        LOGGER.info("Gemini TTS: Generating full dialogue (%d lines) as single audio file", len(dialogue))
        
        try:
            global _gemini_client
            
            # Lazy-load Gemini client
            if _gemini_client is None and GEMINI_CLIENT_AVAILABLE:
                _gemini_client = create_gemini_client(settings.GEMINI_API_KEY)
            
            if _gemini_client:
                # Generate full dialogue as single audio file
                dialogue_audio_path = f"{voice_dir}/dialogue_full.wav"
                
                success = _gemini_client.generate_dialogue_audio(
                    dialogue=dialogue,
                    output_path=dialogue_audio_path,
                    language=language
                )
                
                if success:
                    # Create segments array with full dialogue info
                    dialogue_text = " ".join([item.get("line", "") for item in dialogue])
                    total_duration = float(_estimate_duration_seconds(dialogue_text))
                    
                    segments.append({
                        "segment": 0,
                        "type": "full_dialogue",
                        "speakers": list(set(item.get("speaker", "SpeakerA") for item in dialogue)),
                        "line_count": len(dialogue),
                        "audio_file": dialogue_audio_path,
                        "status": "generated",
                        "duration_estimate_sec": total_duration,
                    })
                    
                    LOGGER.info("✓ Gemini TTS generated full dialogue audio")
                    
                    # Return early with full dialogue result
                    return {
                        "provider": tts_provider,
                        "voice_segments": segments,
                        "audio_dir": voice_dir,
                        "dialogue_audio": dialogue_audio_path,
                        "dialogue_type": "full_conversation",
                        "total_duration_sec": total_duration,
                    }
                else:
                    LOGGER.warning("Gemini TTS failed for full dialogue, falling back to segment-by-segment")
                    # Fall through to segment-by-segment generation below
            else:
                LOGGER.warning("Gemini TTS client not available, falling back to segment-by-segment")
                # Fall through to segment-by-segment generation below
        
        except Exception as e:
            LOGGER.error("Gemini TTS error: %s, falling back to segment-by-segment", str(e))
            # Fall through to segment-by-segment generation below

    # SEGMENT-BY-SEGMENT GENERATION (for non-Gemini or Gemini fallback)
    for idx, item in enumerate(dialogue, start=1):
        speaker = item.get("speaker", "SpeakerA")
        text = item.get("line", "")
        # kokoro-onnx and parkiet output wav; macos say outputs aiff
        ext = ".wav" if tts_provider in ["kokoro", "parkiet"] else ".aiff"
        audio_path = f"{voice_dir}/segment_{idx}{ext}"
        status = "planned"

        if text:
            # Select voice based on speaker mapping
            voice = voice_map.get(speaker, list(voice_map.values())[0] if voice_map else "default")
            
            # Generate audio based on provider
            if tts_provider == "macos_say":
                if command_exists("say"):
                    if _generate_macos_say(text, speaker, voice, speech_rate, audio_path):
                        status = "generated"
                    else:
                        status = "failed"
                else:
                    status = "unavailable"
            
            elif tts_provider == "gemini":
                # Try Gemini TTS first, fall back to Parkiet if it fails
                LOGGER.info("Attempting Gemini TTS (will fall back to Parkiet if unavailable)")
                
                if _generate_gemini_tts(text, speaker, voice, audio_path, language=language):
                    status = "generated"
                else:
                    # Fallback to Parkiet if Gemini fails (experimental feature fallback)
                    LOGGER.warning("Gemini TTS failed for segment %d, falling back to Parkiet", idx)
                    colab_url = os.getenv("PARKIET_COLAB_URL") or getattr(settings, "PARKIET_COLAB_URL", None)
                    
                    if colab_url and REMOTE_PARKIET_AVAILABLE:
                        if _generate_remote_parkiet_tts(text, speaker, voice, audio_path, colab_url):
                            status = "generated"
                        else:
                            status = "failed"
                    elif PARKIET_AVAILABLE:
                        if _generate_parkiet_tts(text, speaker, voice, audio_path, tts_rate_wpm=tts_rate_wpm):
                            status = "generated"
                        else:
                            status = "failed"
                    else:
                        status = "failed"
            
            elif tts_provider == "kokoro":
                if _generate_kokoro_tts(text, speaker, voice, audio_path, language=language, tts_rate_wpm=tts_rate_wpm):
                    status = "generated"
                else:
                    status = "failed"
            
            elif tts_provider == "parkiet":
                # Check if using remote Parkiet on Colab
                colab_url = os.getenv("PARKIET_COLAB_URL") or getattr(settings, "PARKIET_COLAB_URL", None)
                
                if colab_url:
                    # Use remote Parkiet on Colab
                    LOGGER.info("Using remote Parkiet at: %s", colab_url)
                    if _generate_remote_parkiet_tts(text, speaker, voice, audio_path, colab_url):
                        status = "generated"
                    else:
                        status = "failed"
                else:
                    # Use local Parkiet
                    if _generate_parkiet_tts(text, speaker, voice, audio_path, tts_rate_wpm=tts_rate_wpm):
                        status = "generated"
                    else:
                        status = "failed"
            
            else:
                status = "unsupported_provider"

        segments.append(
            {
                "segment": idx,
                "speaker": speaker,
                "text": text,
                "audio_file": audio_path,
                "status": status,
                "duration_estimate_sec": _estimate_duration_seconds(text),
            }
        )

    # If using Kokoro or Parkiet and any segment failed, fail the entire run
    if tts_provider in ["kokoro", "parkiet"]:
        failed_segments = [s for s in segments if s["status"] == "failed"]
        if failed_segments:
            raise RuntimeError(f"{tts_provider.capitalize()} TTS generation failed for {len(failed_segments)} segment(s). Cannot continue without successful audio generation.")

    return {
        "provider": tts_provider,
        "voice_segments": segments,
        "audio_dir": voice_dir,
    }


def plan_voice_assets(script: dict[str, Any]) -> dict[str, Any]:
    # Backward compatible helper used by existing callers.
    return generate_voice_assets(script)
