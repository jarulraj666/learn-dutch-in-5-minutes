#!/usr/bin/env python3
"""
Test script to verify remote Parkiet connection from Google Colab.

Usage:
    python test_remote_parkiet.py
"""

import sys
import os
from pathlib import Path

# Add pipeline to path
sys.path.insert(0, str(Path(__file__).parent))

from pipeline.remote_parkiet_client import RemoteParkietClient


def main():
    print("="*70)
    print("Remote Parkiet TTS Connection Tester")
    print("="*70)
    
    # Get URL from environment or prompt
    colab_url = os.getenv("PARKIET_COLAB_URL", "").strip()
    
    if not colab_url:
        print("\nPARKIET_COLAB_URL not set. Please provide it:")
        colab_url = input("Enter Colab API URL (e.g., https://xxxx-xxxx.ngrok.io): ").strip()
    
    if not colab_url:
        print("❌ No URL provided. Exiting.")
        return False
    
    print(f"\nTesting connection to: {colab_url}\n")
    
    # Try to connect
    try:
        print("1. Connecting to Colab server...")
        client = RemoteParkietClient(colab_url)
        print("   ✓ Connection successful!\n")
    except Exception as e:
        print(f"   ❌ Connection failed: {e}\n")
        return False
    
    # Test speech generation
    print("2. Testing speech generation...")
    test_texts = [
        ("Hallo, hoe gaat het?", "[S1]"),
        ("Goedemorgen!", "[S2]"),
    ]
    
    for text, speaker in test_texts:
        try:
            print(f"   Generating: '{text}' ({speaker})...", end=" ", flush=True)
            audio_bytes = client.generate_speech(text, speaker=speaker)
            size_kb = len(audio_bytes) / 1024
            print(f"✓ ({size_kb:.1f} KB)")
        except Exception as e:
            print(f"❌ Error: {e}")
            return False
    
    print("\n" + "="*70)
    print("✓ All tests passed!")
    print("="*70)
    print("\nYou can now use Parkiet in your pipeline:")
    print(f"  export PARKIET_COLAB_URL='{colab_url}'")
    print("  python -m pipeline.test_stage_2_voice_generation")
    
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
