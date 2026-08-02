# Dutch Language Video Generation Pipeline - Testing Guide

## Run Individual Stages (One at a Time)

### Stage 1: Generate Script & Dialogue (Fast - 2-3 min)
```bash
source .venv311/bin/activate
python -m pipeline.test_stage_1_script_generation
```
✓ Creates: `output/test_stage_1_script.json` with dialogue, vocabulary, grammar, image_prompt

### Stage 2: Generate Voice (Gemini TTS - 5-10 min)
```bash
source .venv311/bin/activate
python -m pipeline.test_stage_2_voice_generation
```
✓ Creates: `output/{level}/{category}/audio/episode_{topic_id}_{slug}.wav`
✓ Creates: `output/test_stage_2_voice_plan.json`

### Stage 3a: Speech-to-Text (Gemini STT - 2-5 min)
```bash
source .venv311/bin/activate
python -m pipeline.test_stage_3a_speech_to_text
```
✓ Creates: `output/test_stage_3a_stt_segments.json`

### Stage 3c: Generate Karaoke/SRT from STT Segments (Fast - <1 min)
```bash
source .venv311/bin/activate
python -m pipeline.test_stage_3c_karaoke_generation
```
✓ Creates: `output/{level}/{category}/subtitles/episode_{topic_id}_{slug}.ass`
✓ Creates: `output/test_stage_3_subtitle_plan.json`

### Stage 3b: Generate Background Image (Gemini 2.5 Flash Image - 3-5 min)
> Can run in parallel with Stages 2 & 3 — only requires Stage 1 output.
```bash
source .venv311/bin/activate
python -m pipeline.test_stage_3b_image_generation
```
✓ Creates: `output/{level}/{category}/visuals/episode_{topic_id}_{slug}.png`

### Stage 4: Render Video (FFmpeg - 10-15 min)
> Requires Stages 2, 3a, 3c, and 3b to be complete.
```bash
source .venv311/bin/activate
python -m pipeline.test_stage_4_video_rendering
```
✓ Creates: `output/{level}/{category}/videos/episode_{topic_id}_{slug}.mp4`

## Run All Stages Sequentially
```bash
source .venv311/bin/activate
python -m pipeline.test_all_stages --all
```

## Recommended Parallel Run Order
```
Stage 1   →  python -m pipeline.test_stage_1_script_generation
               ↓                          ↓
Stage 2   python -m pipeline.test_stage_2_voice_generation
Stage 3a  python -m pipeline.test_stage_3a_speech_to_text
Stage 3c  python -m pipeline.test_stage_3c_karaoke_generation
Stage 3b  python -m pipeline.test_stage_3b_image_generation    ← runs in parallel with 2 & 3
               ↓
Stage 4   python -m pipeline.test_stage_4_video_rendering
```

## View Testing Instructions
```bash
python -m pipeline.test_all_stages --help
```

## Key Configuration

File: `config/pedagogy.yaml`
```yaml
speech:
  tts_provider: gemini           # ← Main TTS provider (Gemini 3.1 Flash)
  language: nl                   # ← Dutch
  language_provider_map:
    en: gemini                   # English → Gemini TTS
    nl: gemini                   # Dutch → Gemini TTS
  voice_map:
    gemini:
      Speaker1: Kore             # Dutch voice
      Speaker2: Puck             # Dutch voice
```

## Troubleshooting

**Stage 1 fails:**
- Check Ollama: `ollama serve`
- Check database: `ls -la db/`

**Stage 2 (Gemini TTS) fails:**
- API Key: `echo $GEMINI_API_KEY`
- Network: Test with `curl https://generativelanguage.googleapis.com/`

**Stage 3 (Subtitles) fails:**
- Check audio file exists: `ls -la output/{level}/{category}/audio/`
- Check Ollama is running for translation: `ollama serve`

**Stage 3a (Speech-to-Text) fails:**
- Check API Key: `echo $GEMINI_API_KEY`
- Check network access to Gemini APIs

**Stage 3c (Karaoke build) fails:**
- Ensure `output/test_stage_3a_stt_segments.json` exists
- Re-run Stage 3a, then Stage 3c

**Stage 3b (Image generation) fails:**
- Image API Key: `echo $GEMINI_IMAGE_CREATION_API_KEY`
- Script file: Verify `output/test_stage_1_script.json` exists and has `image_prompt`

**Stage 4 (Video) fails:**
- FFmpeg: `which ffmpeg`
- Audio file: `ls -la output/{level}/{category}/audio/`
- Image file: `ls -la output/{level}/{category}/visuals/`
- Subtitles: `ls -la output/{level}/{category}/subtitles/`

## Performance Tips

1. **Close other applications** before stages 2, 5, 7 (API/GPU intensive)
2. **Set API keys** in `.env` file before running
3. **Monitor quota**: Gemini API has rate limits; space out large batch operations
4. **Test with smaller batches** before publishing playlists
5. **Monitor processes**: `top -l 1 | grep python` or Activity Monitor

## System Requirements

| Component | Requirement | Usage Stage |
|-----------|-------------|------------|
| Python | 3.10+ | All |
| RAM | 4+ GB available | All stages |
| Disk | 10+ GB free | Stage 4 (video output) |
| CPU cores | 2+ | Stage 4 (faster encoding) |
| Network | Required | All stages (Gemini APIs) |
| GEMINI_API_KEY | Valid API key | Stages 2, 4 |
| GEMINI_IMAGE_CREATION_API_KEY | Valid API key | Stage 3b |

## Pipeline Changes (No Expansion)

✨ **NEW APPROACH**: Dialogue is generated complete (20-25 lines) in Stage 1.
- ❌ REMOVED: Script expansion stage (was causing JSON corruption)
- ✅ BENEFIT: Single LLM call, higher quality output
- ✅ BENEFIT: Simpler pipeline, fewer failure points
