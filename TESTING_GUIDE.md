# Dutch Language Video Generation Pipeline - Testing Guide

## Run Individual Stages (One at a Time)

### Stage 1: Generate Script & Dialogue (Fast - 2-3 min)
```bash
source .venv311/bin/activate
# Pick any topic automatically
python -m pipeline.tests.test_stage_1_script_generation

# Test a specific category
python -m pipeline.tests.test_stage_1_script_generation --category dialogue
python -m pipeline.tests.test_stage_1_script_generation --category common_words
python -m pipeline.tests.test_stage_1_script_generation --category vocabulary
python -m pipeline.tests.test_stage_1_script_generation --category grammar

# Test a specific level + category
python -m pipeline.tests.test_stage_1_script_generation --level A2 --category dialogue
```
✓ Creates: `output/test_stage_1_script.json` with dialogue, vocabulary, grammar, image_prompt

### Stage 2: Generate Voice (Gemini TTS - 5-10 min)
```bash
source .venv311/bin/activate
python -m pipeline.tests.test_stage_2_voice_generation
```
✓ Creates: `output/{level}/{category}/audio/episode_{topic_id}_{slug}.wav`
✓ Creates: `output/test_stage_2_voice_plan.json`

### Stage 3a: Speech-to-Text (Gemini STT - 2-5 min)
```bash
source .venv311/bin/activate
python -m pipeline.tests.test_stage_3a_speech_to_text
```
✓ Creates: `output/test_stage_3a_stt_segments.json`

### Stage 3b: Generate Karaoke/SRT from STT Segments (Fast - <1 min)
```bash
source .venv311/bin/activate
python -m pipeline.tests.test_stage_3b_karaoke_generation
```
✓ Creates: `output/{level}/{category}/subtitles/episode_{topic_id}_{slug}.ass`
✓ Creates: `output/test_stage_3_subtitle_plan.json`

### Stage 3c: Generate Background Image (Gemini 2.5 Flash Image - 3-5 min)
> Requires Stage 3b (karaoke/ASS subtitles) to be complete — image generation uses the ASS subtitle file.
```bash
source .venv311/bin/activate
python -m pipeline.tests.test_stage_3c_image_generation
```
✓ Creates: `output/{level}/{category}/visuals/episode_{topic_id}_{slug}.png`

### Stage 4: Render Video (FFmpeg - 10-15 min)
> Requires Stages 2, 3a, 3b, and 3c to be complete.
```bash
source .venv311/bin/activate
python -m pipeline.tests.test_stage_4_video_rendering
```
✓ Creates: `output/{level}/{category}/videos/episode_{topic_id}_{slug}.mp4`

## Run All Stages Sequentially
```bash
source .venv311/bin/activate
python -m pipeline.tests.test_all_stages --all
```

## Recommended Run Order
```
Stage 1   →  python -m pipeline.tests.test_stage_1_script_generation [--level A1] [--category dialogue]
               ↓
Stage 2      python -m pipeline.tests.test_stage_2_voice_generation
               ↓
Stage 3a     python -m pipeline.tests.test_stage_3a_speech_to_text
               ↓
Stage 3b     python -m pipeline.tests.test_stage_3b_karaoke_generation
               ↓
Stage 3c     python -m pipeline.tests.test_stage_3c_image_generation    ← requires ASS subtitles from Stage 3b
               ↓
Stage 4      python -m pipeline.tests.test_stage_4_video_rendering
```

## View Testing Instructions
```bash
python -m pipeline.tests.test_all_stages --help
```

## Key Configuration

File: `config/pedagogy.yaml`
```yaml
speech:
  language: nl                   # ← Dutch
  voice_map:
    gemini:
            female: Sulafat            # Voice used when speaker gender is female
            male: Puck                 # Voice used when speaker gender is male
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

**Stage 3b (Karaoke build) fails:**
- Ensure `output/test_stage_3a_stt_segments.json` exists
- Re-run Stage 3a, then Stage 3b

**Stage 3c (Image generation) fails:**
- Image API Key: `echo $GEMINI_IMAGE_CREATION_API_KEY`
- Script file: Verify `output/test_stage_1_script.json` exists and has `image_prompt`
- ASS subtitle file: Verify Stage 3b has run — `ls -la output/{level}/{category}/subtitles/`

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
| GEMINI_IMAGE_CREATION_API_KEY | Valid API key | Stage 3c |

## Pipeline Changes (No Expansion)

✨ **NEW APPROACH**: Dialogue is generated complete (20-25 lines) in Stage 1.
- ❌ REMOVED: Script expansion stage (was causing JSON corruption)
- ✅ BENEFIT: Single LLM call, higher quality output
- ✅ BENEFIT: Simpler pipeline, fewer failure points

---

## Multi-Speaker Validation (Dialogue Category)

### Overview
Multi-speaker support is implemented **only for dialogue category**. Single-speaker categories (common_words, vocabulary, grammar) are completely unaffected.

### Key Features to Validate

#### 1. Speaker Metadata Injection (Stage 1 - Script Generation)
**What to check:**
- Dialogue episodes should have `"speakers"` list in artifact
- Each speaker should have: `id`, `role`, `gender`, `voice_id`
- Non-dialogue categories should NOT have speaker metadata

**Validation command:**
```bash
python -c "
import json
with open('output/test_stage_1_script.json') as f:
    script = json.load(f)
    if script.get('category') == 'dialogue':
        speakers = script.get('speakers', [])
        print(f'Dialogue: Found {len(speakers)} speakers')
        for s in speakers:
            print(f'  - {s.get(\"id\")}: {s.get(\"role\")} ({s.get(\"gender\")}, voice={s.get(\"voice_id\")})')
    else:
        print(f'{script.get(\"category\")}: No speakers (expected)')
"
```

**Expected output for dialogue:**
```
Dialogue: Found 2 speakers
  - Speaker1: teacher (female, voice=Kore)
    - Speaker2: learner (male, voice=Puck)
```

#### 2. Speaker Timestamps (Stage 2 - TTS Voice Generation)
**What to check:**
- TTS client should return speaker timestamps for dialogue
- Timestamps should have: `speaker_id`, `start_time`, `end_time`
- Non-dialogue should return empty timestamp list

**Validation:**
```bash
ls -lh output/A1/dialogue/audio/episode_*.wav
```
Expected: Multi-speaker WAV file with alternating voices

#### 3. Speaker-Aware STT Alignment (Stage 3a/3b - Subtitles)
**What to check:**
- Aligned segments should have `"speaker"` field (Speaker1 or Speaker2)
- Karaoke subtitle file (ASS) should be generated without errors

**Validation:**
```bash
python -c "
import json
with open('output/test_stage_3a_stt_segments.json') as f:
    segments = json.load(f)
    speakers_found = set()
    for seg in segments[:5]:
        speaker = seg.get('speaker', 'UNKNOWN')
        speakers_found.add(speaker)
    print(f'First 5 segments have speakers: {speakers_found}')
"
```

Expected: `{'Speaker1', 'Speaker2'}` for dialogue

#### 4. Dynamic ASS Subtitle Styling (Stage 3b)
**What to check:**
- Dialogue ASS files should have two styles: `SpeakerL` and `SpeakerR`
- Non-dialogue ASS files should have single `Default` style
- Speaker1 → SpeakerL (left-aligned), Speaker2 → SpeakerR (right-aligned)

**Validation:**
```bash
# Check dialogue ASS file
head -30 output/A1/dialogue/subtitles/episode_*.ass | grep -E "^Style:|Dialogue:"

# Check non-dialogue ASS file
head -30 output/A1/common_words/subtitles/episode_*.ass | grep -E "^Style:|Dialogue:"
```

**Expected for dialogue:**
```
Style: SpeakerL,Arial,54,...,1,{left_margin},
Style: SpeakerR,Arial,54,...,9,{right_margin},
Dialogue: ...SpeakerL...
Dialogue: ...SpeakerR...
```

**Expected for non-dialogue:**
```
Style: Default,Arial,54,...,8,550,240,
Dialogue: ...Default...
```

#### 5. Scenario-Aware Image Prompt (Stage 3c - Image Generation)
**What to check:**
- Dialogue image prompt should be enriched from dialogue.md template
- Should include scenario, speaker roles
- Non-dialogue should use original image_prompt

**Validation:**
```bash
python -c "
import json
with open('output/test_stage_1_script.json') as f:
    script = json.load(f)
    prompt = script.get('image_prompt', '')
    category = script.get('category', '')
    if category == 'dialogue':
        print(f'Dialogue prompt snippet: {prompt[:200]}...')
        if 'scenario' in script:
            print(f'Scenario: {script.get(\"scenario\")}')
"
```

#### 6. Render Manifest Documentation (Stage 4 - Video)
**What to check:**
- Render manifest should include note about subtitle styling
- ASS subtitle file path should be present

**Validation:**
```bash
python -c "
import json
from pathlib import Path
manifest_file = list(Path('output/A1/dialogue').glob('*_render_manifest.json'))[0]
with open(manifest_file) as f:
    manifest = json.load(f)
    print(f'Note: {manifest.get(\"note_subtitle_styling\", \"MISSING\")}')
    print(f'ASS file: {manifest.get(\"ass_subtitle_file\", \"MISSING\")}')
"
```

### Category-Based Testing Matrix

| Stage | Category | Expected Behavior |
|-------|----------|-------------------|
| **1 (Script)** | dialogue | Speakers list + scenario included |
| **1 (Script)** | other | NO speakers field |
| **2 (TTS)** | dialogue | Multi-speaker timestamps returned |
| **2 (TTS)** | other | Single speaker (no timestamps) |
| **3a/3b (STT)** | dialogue | Segments tagged with Speaker1/Speaker2 |
| **3a/3b (STT)** | other | No speaker field (or same speaker) |
| **3b (ASS)** | dialogue | Styles: SpeakerL, SpeakerR |
| **3b (ASS)** | other | Style: Default (center-aligned) |
| **3c (Image)** | dialogue | ASS subtitles (from 3b) + scenario-enriched prompt |
| **3c (Image)** | other | ASS subtitles (from 3b) + original image_prompt |
| **4 (Render)** | dialogue | SpeakerL/SpeakerR subtitles in video |
| **4 (Render)** | other | Default center-aligned subtitles |

### Full Multi-Speaker Test Run

**Test all stages with dialogue:**
```bash
# Stage 1: Script (with dialogue category)
python -m pipeline.tests.test_stage_1_script_generation --category dialogue

# Stage 2: TTS (multi-speaker audio)
python -m pipeline.tests.test_stage_2_voice_generation

# Stage 3a: STT (extract speaker segments)
python -m pipeline.tests.test_stage_3a_speech_to_text

# Stage 3b: ASS karaoke (with speaker styling)
python -m pipeline.tests.test_stage_3b_karaoke_generation

# Stage 3c: Image (uses ASS subtitle file from Stage 3b)
python -m pipeline.tests.test_stage_3c_image_generation

# Stage 4: Render (combine with speaker-aware subtitles)
python -m pipeline.tests.test_stage_4_video_rendering
```

### Quick Validation Script
```bash
# Check multi-speaker features are working
python << 'EOF'
import json
from pathlib import Path

def check_category(level, category):
    artifact = Path(f"output/{level}/{category}").glob("episode_*.json")
    for f in artifact:
        with open(f) as fp:
            data = json.load(fp)
            has_speakers = "speakers" in data
            print(f"{category:15} | speakers={has_speakers:5} | roles={len(data.get('speakers', []))} speakers")
        break

print("Category Validation:")
print("-" * 60)
check_category("A1", "dialogue")
check_category("A1", "common_words")
check_category("A1", "vocabulary")
EOF
```

### Backward Compatibility Checks

**Single-speaker categories should be UNCHANGED:**
```bash
# Compare old vs new subtitles (should look identical)
git diff output/A1/common_words/subtitles/
git diff output/A1/vocabulary/subtitles/
git diff output/A1/grammar/subtitles/
```

Expected: No subtitle styling changes for non-dialogue categories

### Known Limitations & Workarounds

| Issue | Cause | Workaround |
|-------|-------|-----------|
| Dialogue prompt not enriched | dialogue.md not found | Check: `ls prompts/{level}/dialogue.md` |
| Speaker mismatch in ASS | Timestamps misaligned | Re-run Stage 2 (TTS) + Stage 3a (STT) |
| Video shows single speaker | ASS styles not applied | Check FFmpeg version + ASS support |
| Margins incorrect | visual_style.yaml outdated | Update margins in config → re-run Stage 3b |

---
