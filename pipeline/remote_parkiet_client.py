"""
Remote Parkiet TTS Client for Google Colab

This module provides a client to call Parkiet TTS running on Google Colab
via an ngrok tunnel, allowing local machines to use the remote Parkiet model.
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Optional

import requests

LOGGER = logging.getLogger(__name__)


class RemoteParkietClient:
    """Client for remote Parkiet TTS API running on Google Colab."""
    
    def __init__(self, colab_api_url: str, timeout: int = 300):
        """
        Initialize client with Colab API URL.
        
        Args:
            colab_api_url: The public ngrok URL (e.g., https://xxxx-xxxx.ngrok.io)
            timeout: Request timeout in seconds (default: 300 = 5 minutes)
        
        Raises:
            ConnectionError: If unable to connect to the Colab server
        """
        self.api_url = colab_api_url.rstrip("/")
        self.timeout = timeout
        self.health_check()
    
    def health_check(self) -> bool:
        """
        Verify connection to Colab server.
        
        Returns:
            True if server is healthy
        
        Raises:
            ConnectionError: If unable to connect
        """
        try:
            response = requests.get(
                f"{self.api_url}/health",
                timeout=self.timeout
            )
            response.raise_for_status()
            health_info = response.json()
            LOGGER.info(
                "✓ Connected to remote Parkiet at %s (device: %s)",
                self.api_url,
                health_info.get("device", "unknown")
            )
            return True
        except Exception as e:
            LOGGER.error("✗ Cannot connect to Colab Parkiet at %s: %s", self.api_url, str(e))
            raise ConnectionError(f"Failed to connect to Colab: {str(e)}")
    
    def generate_speech(
        self, 
        text: str, 
        speaker: str = "[S1]"
    ) -> bytes:
        """
        Generate speech from Dutch text.
        
        Args:
            text: Dutch text to synthesize
            speaker: Speaker tag ([S1] or [S2]) for two-speaker dialogue
        
        Returns:
            WAV audio data as bytes
        
        Raises:
            ValueError: If text is empty or API returns error
            requests.RequestException: If network request fails
        """
        try:
            if not text or not text.strip():
                raise ValueError("Text cannot be empty")
            
            response = requests.post(
                f"{self.api_url}/generate_voice",
                json={
                    "text": text,
                    "speaker": speaker
                },
                timeout=self.timeout
            )
            response.raise_for_status()
            result = response.json()
            
            if result.get("status") != "success":
                error_msg = result.get("message", "Unknown error")
                raise ValueError(f"API error: {error_msg}")
            
            audio_base64 = result.get("audio_base64")
            if not audio_base64:
                raise ValueError("No audio data in response")
            
            audio_bytes = base64.b64decode(audio_base64)
            duration = result.get("duration_seconds", 0)
            
            LOGGER.debug("Generated %.2fs audio for: %s", duration, text)
            return audio_bytes
        
        except requests.exceptions.RequestException as e:
            LOGGER.error("Network error calling Colab API: %s", str(e))
            raise
        except (ValueError, KeyError) as e:
            LOGGER.error("Error response from Colab: %s", str(e))
            raise
    
    def save_speech(
        self,
        text: str,
        output_path: str,
        speaker: str = "[S1]"
    ) -> bool:
        """
        Generate speech and save to WAV file.
        
        Args:
            text: Dutch text to synthesize
            output_path: Path to save WAV file
            speaker: Speaker tag ([S1] or [S2])
        
        Returns:
            True if successful
        """
        try:
            audio_bytes = self.generate_speech(text, speaker)
            
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_bytes(audio_bytes)
            
            LOGGER.info("✓ Saved %s bytes to %s", len(audio_bytes), output_path)
            return True
        
        except Exception as e:
            LOGGER.error("Failed to save speech: %s", str(e))
            return False


def create_remote_client(colab_url: Optional[str] = None) -> Optional[RemoteParkietClient]:
    """
    Factory function to create remote client if URL is configured.
    
    Args:
        colab_url: Optional override for Colab API URL
    
    Returns:
        RemoteParkietClient instance or None if not configured
    """
    url = colab_url
    
    if not url:
        # Try to get from environment or settings
        import os
        from pipeline import settings
        url = os.getenv("PARKIET_COLAB_URL") or getattr(settings, "PARKIET_COLAB_URL", None)
    
    if not url:
        return None
    
    try:
        return RemoteParkietClient(url)
    except Exception as e:
        LOGGER.warning("Could not create remote Parkiet client: %s", str(e))
        return None
