# Dutch Language Video Generator

Automatically generates A1-level Dutch lesson videos with narrated dialogue, karaoke subtitles, background images, and YouTube publishing.

## Features
- Single-speaker narrated lessons (common words, grammar, vocabulary, dialogue)
- Gemini TTS audio generation with slow A1 pacing
- WhisperX speech-to-text for karaoke subtitle sync
- AI-generated classroom background images
- FFmpeg video assembly with burned-in subtitles
- YouTube upload with auto-created playlists, title, description, and tags
- SQLite topic memory with anti-repeat scheduling
- 2-day publish cadence

## Project Structure

```
pipeline/
  run_pipeline.py       ← main entry point
  settings.py           ← config and env vars
  utils.py              ← shared helpers

  core/                 ← DB, topic selection, storage, scheduling, QA
  generate/             ← script, metadata, voice, subtitles, image generation
  clients/              ← Gemini TTS and Ollama API clients
  publish/              ← YouTube upload, render video, publish queue
  tests/                ← stage-by-stage test runners

config/
  playlists.yaml        ← YouTube playlist names by level + category
  topic_backlog.yaml    ← all topics (40 A1 topics across 4 categories)
  pedagogy.yaml         ← pacing, speech rate, timing settings
  scheduling.yaml       ← publish cadence

prompts/
  A1/
    common_words.md     ← prompt for common words lessons
    grammar.md          ← prompt for grammar lessons
    vocabulary.md       ← prompt for vocabulary lessons
    dialogue.md         ← prompt for dialogue lessons
```

## Setup

1. Install Python 3.11+
2. Copy `.env.example` to `.env` and set values
3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Initialize database:

```bash
python -m pipeline.core.db --init
```

## Running the Pipeline

**Generate all videos for a specific category (batch):**
```bash
python -m pipeline.run_pipeline --language nl --level A1 --category common_words
python -m pipeline.run_pipeline --language nl --level A1 --category grammar
python -m pipeline.run_pipeline --language nl --level A1 --category vocabulary
python -m pipeline.run_pipeline --language nl --level A1 --category dialogue
```

**Generate next pending topic (single video):**
```bash
python -m pipeline.run_pipeline --language nl --level A1
```

## Publishing to YouTube

**Set up OAuth credentials (one-time):**
```bash
export YOUTUBE_CLIENT_SECRETS=/path/to/client_secrets.json
```

**Dry-run — preview upload payload without uploading:**
```bash
python -m pipeline.publish.publish_pending --include-future
```

**Execute real uploads:**
```bash
python -m pipeline.publish.publish_pending --execute --include-future
```

**Upload a specific job:**
```bash
python -m pipeline.publish.publish_pending --execute --job-id 1
```

**Test a single artifact:**
```bash
python -m pipeline.publish.upload_youtube output/episode_X.json --dry-run
```

## Re-run a Specific Stage for an Existing Episode

Use this when something goes wrong and you want to redo just one step, then re-render and re-upload without regenerating the full script/audio.

### Easy Way: Use `rerun_stage.py`

**Interactive mode (easiest):**
```bash
python rerun_stage.py output/A1/common_words/episode_cw_days_of_week_days_of_the_week_maandag_tot_en_met_zondag.json
```
Then select from the menu (1-7). Option 7 runs the complete end-to-end pipeline.

**Auto-detection:**
- `--subtitles`: Automatically finds audio file from `artifact["audio_file"]` if not specified
- `--upload`: Automatically finds video from `_render_manifest.json` or `artifact["video_file"]` if not specified

**Quick commands:**
```bash
# Re-generate script
python rerun_stage.py artifact.json --script

# Re-generate audio
python rerun_stage.py artifact.json --audio-gen

# Re-generate subtitles (auto-detects audio from artifact)
python rerun_stage.py artifact.json --subtitles

# Re-generate background image
python rerun_stage.py artifact.json --image

# Re-render video
python rerun_stage.py artifact.json --render

# Upload to YouTube (auto-detects video from render manifest)
python rerun_stage.py artifact.json --upload

# Run all stages at once (complete end-to-end pipeline)
python rerun_stage.py artifact.json --all
```

**What `--all` does:**
Regenerates the entire episode: script → audio → subtitles → image → video render → YouTube upload. No external files needed.

### Advanced: Manual Commands

**Variables to substitute:**
```
ARTIFACT = output/A1/common_words/episode_cw_days_of_week_days_of_the_week_maandag_tot_en_met_zondag.json
AUDIO    = output/A1/common_words/audio/episode_cw_days_of_week_days_of_the_week_maandag_tot_en_met_zondag.wav
VIDEO    = output/archive/episode_22.mp4
```

**Re-generate subtitles only:**
```python
# Run inside Python (or paste in a script)
from pathlib import Path
from pipeline.generate.generate_subtitles import plan_subtitles
import json

artifact = json.loads(Path("ARTIFACT").read_text())
plan_subtitles(
    "AUDIO",
    output_root="output/A1/common_words",
    level="A1",
    category="common_words",
    topic_id=artifact["topic_id"],
    title_slug=artifact["title_slug"],
    script_dialogue=artifact.get("script", {}).get("dialogue"),
)
```

**Re-generate background image only:**
```bash
python -m pipeline.generate.generate_visual_image --artifact-file ARTIFACT
```

**Re-render video (after subtitles or image are fixed):**
```bash
python -m pipeline.publish.render_video ARTIFACT
```

**Upload to YouTube (after render):**
```bash
python -m pipeline.publish.upload_youtube ARTIFACT --video-file VIDEO
```

---

## Test Stages (run individually)

```bash
python -m pipeline.tests.test_stage_1_script_generation
python -m pipeline.tests.test_stage_2_voice_generation
python -m pipeline.tests.test_stage_3_subtitle_generation
python -m pipeline.tests.test_stage_4_video_rendering
```

## YouTube Playlists

Videos are automatically assigned to the correct playlist:

| Category     | Playlist                         |
|---|---|
| common_words | A1 \| Beginners \| Common Words  |
| grammar      | A1 \| Beginners \| Grammar       |
| vocabulary   | A1 \| Beginners \| Vocabulary    |
| dialogue     | A1 \| Beginners \| Dialogue      |

## Notes
- Requires `ffmpeg` for video assembly. Without it, a render manifest is produced and assembly is skipped gracefully.
- Real YouTube upload requires `YOUTUBE_CLIENT_SECRETS` env var and first-run OAuth browser consent. Token saved to `output/youtube_token.json`.
- Rendered videos are archived to `output/archive/` with stable paths stored in DB for upload retries.
- Dutch subtitle tracks are uploaded as separate YouTube caption tracks when present.
