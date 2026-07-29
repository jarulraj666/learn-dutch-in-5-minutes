# Parkiet TTS Pipeline - Quick Reference

## Run Individual Stages (One at a Time)

### Stage 1: Generate Complete Dialogue (Fast - 2-3 min)
```bash
source .venv311/bin/activate
python -m pipeline.test_stage_1_script_generation
```
✓ Creates: `output/test_stage_1_script.json` with 20-25 dialogue lines (COMPLETE, no expansion)

### Stage 2: Script Expansion (REMOVED - No longer used)

**This stage has been removed.** Dialogue is now generated complete (15-20 lines) in Stage 1.

### Stage 2: Generate Parkiet TTS Audio (Slow - 10-15 min first run)
```bash
source .venv311/bin/activate
python -m pipeline.test_stage_2_voice_generation
```
⚠️ First run downloads Parkiet model (~1.6GB)
⚠️ Requires 10+ GB RAM
✓ Creates: `output/audio/segment_*.wav`, `output/test_stage_2_voice_plan.json`

### Stage 3: Generate Subtitles (Fast - <1 min)
```bash
source .venv311/bin/activate
python -m pipeline.test_stage_3_subtitle_generation
```
✓ Creates: `output/subtitles_bilingual.srt`, `output/test_stage_3_subtitle_plan.json`

### Stage 4: Render Video (Slow - 5-15 min)
```bash
source .venv311/bin/activate
python -m pipeline.test_stage_4_video_rendering
```
✓ Creates: `output/videos/episode_*.mp4`, `output/test_stage_4_render_manifest.json`

## Run All Stages Sequentially
```bash
source .venv311/bin/activate
python -m pipeline.test_all_stages --all
```

## View Testing Instructions
```bash
python -m pipeline.test_all_stages --help
```

## Key Configuration

File: `config/pedagogy.yaml`
```yaml
speech:
  tts_provider: parkiet          # ← Main TTS provider
  language: nl                   # ← Dutch
  language_provider_map:
    en: kokoro                   # English → Kokoro
    nl: parkiet                  # Dutch → Parkiet (HIGH QUALITY)
  voice_map:
    parkiet:
      SpeakerA: default          # → [S1] tag in prompt
      SpeakerB: default          # → [S2] tag in prompt
```

## Troubleshooting

**Stage 1 fails:**
- Check Ollama: `ollama serve`
- Check database: `ls -la db/`

**Stage 3 (Parkiet TTS) fails (most likely):**
- Python version: `python3 --version` (must be 3.11+)
- RAM: `free -h` or Activity Monitor
- Parkiet cache: `ls -lh ~/.cache/huggingface/models/pevers/parkiet/`
- Dependencies: `pip list | grep transformers`

**Stage 4 (Video) fails:**
- FFmpeg: `which ffmpeg`
- Audio files: `ls -la output/audio/`
- Subtitles: `head output/subtitles_bilingual.srt`

## Performance Tips

1. **Close other applications** before Stage 2 & 4 (heavy RAM/CPU)
2. **Use external drive** for large media files if disk full
3. **First Parkiet run** takes longer (model download + cache)
4. **Subsequent runs** much faster (model cached)
5. **Monitor processes**: `top -l 1 | grep python` or Activity Monitor

## System Requirements

| Component | Requirement | Usage Stage |
|-----------|-------------|------------|
| Python | 3.11+ | All |
| RAM | 10+ GB available | Stage 2 (voice), 4 (video) |
| Disk | 5+ GB free | Stage 2 (model), Stage 4 (video) |
| CPU cores | 2+ | Stage 4 (faster encoding) |
| Network | For first run | Stage 2 (model download) |

## Pipeline Changes (No Expansion)

✨ **NEW APPROACH**: Dialogue is generated complete (20-25 lines) in Stage 1.
- ❌ REMOVED: Script expansion stage (was causing JSON corruption)
- ✅ BENEFIT: Single LLM call, higher quality output
- ✅ BENEFIT: Simpler pipeline, fewer failure points
