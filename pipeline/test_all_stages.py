#!/usr/bin/env python3
"""
MODULAR PIPELINE TESTING GUIDE
================================

Test each stage independently to verify Parkiet TTS integration and manage system resources.
Run stages sequentially, one at a time.

SYSTEM REQUIREMENTS:
- Python 3.11+ (required for Parkiet/transformers compatibility)
- 10+ GB RAM (Parkiet model inference can use significant memory)
- 5+ GB disk space (Parkiet model cache + audio files)
- Internet connection (first run downloads Parkiet model ~1.6GB)

TESTING SEQUENCE:
"""

import json
import logging
import os
import psutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
LOGGER = logging.getLogger(__name__)


def check_system_resources():
    """Check available system resources."""
    LOGGER.info("=== SYSTEM RESOURCE CHECK ===")
    
    # Memory
    mem = psutil.virtual_memory()
    LOGGER.info("Memory: %.1f GB total, %.1f GB available (%.1f%% used)",
               mem.total / (1024**3), mem.available / (1024**3), mem.percent)
    
    if mem.available < 8 * (1024**3):
        LOGGER.warning("⚠️ Low memory (<8GB available). Rendering may be slow.")
    
    # Disk space
    disk = psutil.disk_usage("/")
    LOGGER.info("Disk: %.1f GB total, %.1f GB available (%.1f%% used)",
               disk.total / (1024**3), disk.free / (1024**3), disk.percent)
    
    if disk.free < 5 * (1024**3):
        LOGGER.error("❌ Critical: Less than 5GB disk space available")
        return False
    
    # CPU
    LOGGER.info("CPU cores: %d", psutil.cpu_count())
    LOGGER.info("CPU usage: %.1f%%", psutil.cpu_percent(interval=1))
    
    return True


def check_ollama_running():
    """Check if Ollama is running on localhost:11434."""
    try:
        import requests
        response = requests.get("http://localhost:11434/api/tags", timeout=2)
        if response.status_code == 200:
            LOGGER.info("✓ Ollama is running")
            return True
    except Exception as e:
        LOGGER.error("❌ Ollama is not running on localhost:11434")
        LOGGER.info("Start Ollama with: ollama serve")
        return False


def run_stage(stage_num: int, module_name: str, stage_name: str) -> bool:
    """Run a test stage in a subprocess."""
    LOGGER.info("\n" + "="*60)
    LOGGER.info("RUNNING: Stage %d - %s", stage_num, stage_name)
    LOGGER.info("="*60)
    
    try:
        result = subprocess.run(
            ["python", "-m", f"pipeline.{module_name}"],
            cwd=Path(__file__).parent.parent,
            check=True,
        )
        LOGGER.info("✅ Stage %d completed successfully", stage_num)
        return True
    except subprocess.CalledProcessError as e:
        LOGGER.error("❌ Stage %d failed with exit code %d", stage_num, e.returncode)
        return False
    except KeyboardInterrupt:
        LOGGER.warning("⚠️ Stage %d interrupted by user", stage_num)
        return False


def print_instructions():
    """Print detailed instructions."""
    instructions = """
╔════════════════════════════════════════════════════════════════════════════╗
║                    PARKIET TTS PIPELINE TESTING                            ║
║              (Dutch A1 Lesson Video Generation with Parkiet)               ║
╚════════════════════════════════════════════════════════════════════════════╝

STAGE 1: Script Generation (Complete Dialogue)
─────────────────────────────────────────────
Run: python -m pipeline.test_stage_1_script_generation

What it does:
- Loads a random topic from the database
- Calls Ollama LLM to generate COMPLETE dialogue in Dutch (A1 level, 20-25 lines)
- Creates a JSON script with dialogue, vocabulary, quiz, and grammar notes
- Saves to: output/test_stage_1_script.json

Expected output: A full dialogue with 20-25 lines in Dutch (complete, no expansion)
Resource usage: Low (LLM only, ~2-3 minutes)
Can fail due to: Ollama not running, network issues with LLM


STAGE 2: Voice Generation (Parkiet TTS) ⚠️ MAIN TEST
────────────────────────────────────────────────────
(Replaces script expansion - dialogue now generated complete in Stage 1)
Run: python -m pipeline.test_stage_2_voice_generation

What it does:
- Loads the complete script from Stage 1 (no expansion phase needed)
- Generates audio segments using Parkiet Dutch TTS
- Maps dialogue speakers to Parkiet speaker tags [S1] and [S2]
- Saves .wav files to: output/audio/segment_1.wav, segment_2.wav, etc.
- Saves voice plan to: output/test_stage_2_voice_plan.json

⚠️  FIRST RUN WARNING:
   - Downloads Parkiet model (~1.6GB) to ~/.cache/huggingface/models/
   - Will take 10-15 minutes on first run
   - Subsequent runs use cached model (much faster)
   - Requires 10+ GB RAM for inference

Expected output: N .wav audio files (one per dialogue line) + voice plan JSON
Resource usage: HIGH
  - Memory: 8-12 GB peak
  - Disk I/O: Moderate to High
  - Time: 10-15 minutes (first run), 2-5 minutes (cached)
  - CPU: Used for model inference
  
Can fail due to: 
  - Insufficient RAM
  - Network timeout during model download
  - Disk full
  - Incompatible Python version (requires 3.11+)


STAGE 3: Subtitle Generation
─────────────────────────────
Run: python -m pipeline.test_stage_3_subtitle_generation

What it does:
- Loads the complete script from Stage 1
- Generates bilingual SRT subtitle file (Dutch + English)
- Calculates timing based on dialogue and voice speeds
- Saves to: output/subtitles_bilingual.srt
- Saves subtitle plan to: output/test_stage_3_subtitle_plan.json

Expected output: SRT file with timestamps and bilingual subtitles
Resource usage: Very low (CPU only, <30 seconds)
Can fail due to: Missing or invalid voice segments


STAGE 4: Video Rendering
────────────────────────
Run: python -m pipeline.test_stage_4_video_rendering

What it does:
- Loads voice segments from Stage 2 (test_stage_2_voice_plan.json)
- Loads subtitles from Stage 3
- Uses FFmpeg to assemble:
  * Audio tracks (dialogue + background music + sound effects)
  * Subtitle overlay
  * Images/animations
- Renders to: output/videos/episode_*.mp4
- Saves render manifest to: output/test_stage_4_render_manifest.json

Expected output: MP4 video file (3-5 minutes long, varies by content)
Resource usage: HIGH
  - CPU: Intensive during encoding
  - Disk I/O: High (reading audio, writing MP4)
  - Time: 5-15 minutes depending on content length
  
Can fail due to:
  - Missing FFmpeg
  - Audio/subtitle timing issues
  - Insufficient disk space


╔════════════════════════════════════════════════════════════════════════════╗
║                            TESTING WORKFLOW                               ║
╚════════════════════════════════════════════════════════════════════════════╝

QUICK TEST (30 minutes):
  1. python -m pipeline.test_stage_1_script_generation
  2. python -m pipeline.test_stage_2_voice_generation  ⚠️ (10-15 min)
  3. python -m pipeline.test_stage_3_subtitle_generation
  
FULL TEST (1-2 hours):
  (Run all stages including video rendering)
  1. Stage 1 (script generation)
  2. Stage 2 (voice generation)  ⚠️
  3. Stage 3 (subtitles)
  4. Stage 4 (video rendering)  ⚠️ (5-15 min)
  
Note: Script expansion (Stage 2) has been removed. Dialogue is now generated complete in Stage 1.

ISOLATE ISSUES:
  - To test just Parkiet TTS: Run stages 1-3
  - To test just video rendering: Run stages 1-5
  - To test just dialogue: Run stages 1-2


╔════════════════════════════════════════════════════════════════════════════╗
║                          TROUBLESHOOTING                                  ║
╚════════════════════════════════════════════════════════════════════════════╝

If Stage 1 fails (Script Generation):
  - Check Ollama: ollama serve
  - Check language setting in config/pedagogy.yaml
  - Check database is initialized

If Stage 3 fails (Voice Generation):
  ❌ MAIN ISSUE AREA
  
  Check 1: Python version
    python3 --version  # Must be 3.11+
    
  Check 2: Memory availability
    Free up RAM, close other applications
    
  Check 3: Model download
    ls -lh ~/.cache/huggingface/models/pevers/parkiet/
    
  Check 4: Configuration
    - Verify config/pedagogy.yaml has:
      tts_provider: parkiet
      language: nl
      language_provider_map.nl: parkiet
      
  Check 5: Dependencies
    pip list | grep -E 'transformers|torch|soundfile'
    Reinstall if needed: pip install transformers torch soundfile

If Stage 5 fails (Video Rendering):
  - Check FFmpeg installation: which ffmpeg
  - Check audio files generated in Stage 3
  - Check subtitle file generated in Stage 4


╔════════════════════════════════════════════════════════════════════════════╗
║                        ONE-STAGE RUNNER SCRIPT                            ║
╚════════════════════════════════════════════════════════════════════════════╝

Run all stages manually:

  # Stage 1: Quick
  python -m pipeline.test_stage_1_script_generation
  
# Stage 2 removed: Script expansion integrated into Stage 1 (15-20 lines generated directly)
  
  # Stage 2: Slow (grab coffee ☕)
  python -m pipeline.test_stage_2_voice_generation
  
  # Stage 3: Quick
  python -m pipeline.test_stage_3_subtitle_generation
  
  # Stage 4: Medium
  python -m pipeline.test_stage_4_video_rendering

Or use this script to run all stages sequentially:
  python -m pipeline.test_all_stages


For questions or issues, check the logs in output/ directory.
"""
    print(instructions)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--help":
        print_instructions()
        return

    if len(sys.argv) > 1 and sys.argv[1] in ["all", "--all", "-a"]:
        LOGGER.info("Running ALL stages sequentially...")
        
        if not check_system_resources():
            LOGGER.error("System resources check failed")
            return
        
        if not check_ollama_running():
            LOGGER.error("Ollama is not running. Start with: ollama serve")
            return
        
        stages = [
            (1, "test_stage_1_script_generation", "Script Generation (20-25 lines)"),
            (2, "test_stage_2_voice_generation", "Voice Generation (Parkiet)"),
            (3, "test_stage_3_subtitle_generation", "Subtitle Generation"),
            (4, "test_stage_4_video_rendering", "Video Rendering"),
        ]
        
        for stage_num, module_name, stage_name in stages:
            success = run_stage(stage_num, module_name, stage_name)
            if not success:
                LOGGER.error("\n❌ Pipeline stopped at stage %d", stage_num)
                return
            
            # Resource check between stages
            if stage_num < 5:
                check_system_resources()
        
        LOGGER.info("\n" + "="*60)
        LOGGER.info("✅ ALL STAGES COMPLETED SUCCESSFULLY!")
        LOGGER.info("="*60)
    else:
        print_instructions()


if __name__ == "__main__":
    main()
