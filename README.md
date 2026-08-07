# Dutch Language Video Generator

Automatically generates A1-A2 level Dutch lesson videos with narrated dialogue, karaoke subtitles, background images, and YouTube publishing.

## Features
- Single-speaker narrated lessons (common words, grammar, vocabulary, dialogue)
- Gemini TTS audio generation with slow A1-A2 pacing
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
  topic_backlog.yaml    ← all topics (109 A1-A2 topics across 4 categories)
  pedagogy.yaml         ← pacing, speech rate, timing settings
  scheduling.yaml       ← publish cadence

prompts/
  A1A2/
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
caffeinate -s pip install -r requirements.txt
```

4. Initialize database:

```bash
caffeinate -s python -m pipeline.core.db --init
```

## Database Management

**Reset a topic status to pending (re-run it):**
```bash
sqlite3 db/content.db "UPDATE topics SET status = 'pending' WHERE id = 'your_topic_id';"
```

**View all topics and their statuses:**
```bash
sqlite3 db/content.db "SELECT id, status, category, level FROM topics ORDER BY order_index;"
```

> **Tip:** Prefix any long-running command with `caffeinate -s` to prevent macOS from sleeping while it runs.

## Running the Pipeline

**Generate all videos for a specific category (batch):**
```bash
caffeinate -s python -m pipeline.run_pipeline --language nl --level A1A2 --category common_words --no-upload
caffeinate -s python -m pipeline.run_pipeline --language nl --level A1A2 --category grammar --no-upload
caffeinate -s python -m pipeline.run_pipeline --language nl --level A1A2 --category vocabulary --no-upload
caffeinate -s python -m pipeline.run_pipeline --language nl --level A1A2 --category dialogue --no-upload
```

**Generate a specific number of videos in batch mode:**
```bash
caffeinate -s python -m pipeline.run_pipeline --language nl --level A1A2 --category common_words --count 5 --no-upload
caffeinate -s python -m pipeline.run_pipeline --language nl --level A1A2 --category grammar --count 3
```

**Generate next pending topic (single video):**
```bash
caffeinate -s python -m pipeline.run_pipeline --language nl --level A1A2
caffeinate -s python -m pipeline.run_pipeline --language nl --level A1A2 --single
caffeinate -s python -m pipeline.run_pipeline --language nl --level A1A2 --count 1
```

## Publishing to YouTube

**Set up OAuth credentials (one-time):**
```bash
export YOUTUBE_CLIENT_SECRETS=/path/to/client_secrets.json
```

**Dry-run — preview upload payload without uploading:**
```bash
caffeinate -s python -m pipeline.publish.publish_pending --include-future
```

**Execute real uploads:**
```bash
caffeinate -s python -m pipeline.publish.publish_pending --execute --include-future
```

**Upload a specific job:**
```bash
caffeinate -s python -m pipeline.publish.publish_pending --execute --job-id 1
```

**Test a single artifact:**
```bash
caffeinate -s python -m pipeline.publish.upload_youtube output/episode_X.json --dry-run
```

## Pipeline Arguments Reference

**`--language`** (default: `nl`)
Language code for the target content.

**`--level`** (default: `A1A2`, choices: `A1A2`, `B1`, `B2`)
CEFR language proficiency level.

**`--category`** (choices: `common_words`, `grammar`, `vocabulary`, `dialogue`, default: `None`)
Filter topics by category. When combined with `--count` or without `--single`, runs in batch mode.

**`--count N`** (optional integer)
Generate exactly N videos in sequence. When set, runs in batch mode until N videos are completed or all topics are exhausted.
- `--count 1`: Generate 1 video
- `--count 5`: Generate 5 videos
- `--count 100`: Generate 100 videos (or fewer if fewer topics remain)

**`--single`** (optional flag)
Generate only 1 video (equivalent to `--count 1`). Kept for backward compatibility.

**`--no-upload`** (optional flag)
Skip YouTube upload after rendering. Useful for testing or when upload will be done separately.

**` CHECKPOINT`** (optional path)
Resume a failed pipeline run from the last completed stage using a checkpoint file.


## Re-run a Specific Stage for an Existing Episode

Use this when something goes wrong and you want to redo just one step, then re-render and re-upload without regenerating the full script/audio.

### Easy Way: Use `rerun_stage.py`

**Interactive mode (easiest):**
```bash--resume
caffeinate -s python rerun_stage.py output/A1A2/common_words/episode_cw_days_of_week_days_of_the_week_maandag_tot_en_met_zondag.json
```
Then select from the menu (1-7). Option 7 runs the complete end-to-end pipeline.

**Auto-detection:**
- `--subtitles`: Automatically finds audio file from `artifact["audio_file"]` if not specified
- `--upload`: Automatically finds video from `_render_manifest.json` or `artifact["video_file"]` if not specified

**Quick commands:**
```bash
# Re-generate script
caffeinate -s python rerun_stage.py artifact.json --script

# Re-generate audio
caffeinate -s python rerun_stage.py artifact.json --audio-gen

# Re-generate subtitles (auto-detects audio from artifact)
caffeinate -s python rerun_stage.py artifact.json --subtitles

# Re-generate background image
caffeinate -s python rerun_stage.py artifact.json --image

# Re-render video
caffeinate -s python rerun_stage.py artifact.json --render

# Upload to YouTube (auto-detects video from render manifest)
caffeinate -s python rerun_stage.py artifact.json --upload

# Run all stages at once (complete end-to-end pipeline)
caffeinate -s python rerun_stage.py artifact.json --all
```

**What `--all` does:**
Regenerates the entire episode: script → audio → subtitles → image → video render → YouTube upload. No external files needed.

### Advanced: Manual Commands

**Variables to substitute:**
```
ARTIFACT = output/A1A2/common_words/episode_cw_days_of_week_days_of_the_week_maandag_tot_en_met_zondag.json
AUDIO    = output/A1A2/common_words/audio/episode_cw_days_of_week_days_of_the_week_maandag_tot_en_met_zondag.wav
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
    output_root="output/A1A2/common_words",
    level="A1A2",
    category="common_words",
    topic_id=artifact["topic_id"],
    title_slug=artifact["title_slug"],
    script_dialogue=artifact.get("script", {}).get("dialogue"),
)
```

**Re-generate background image only:**
```bash
caffeinate -s python -m pipeline.generate.generate_visual_image --artifact-file ARTIFACT
```

**Re-render video (after subtitles or image are fixed):**
```bash
caffeinate -s python -m pipeline.publish.render_video ARTIFACT
```

**Upload to YouTube (after render):**
```bash
caffeinate -s python -m pipeline.publish.upload_youtube ARTIFACT --video-file VIDEO
```

---

## Test Stages (run individually)

```bash
caffeinate -s python -m pipeline.tests.test_stage_1_script_generation
caffeinate -s python -m pipeline.tests.test_stage_2_voice_generation
caffeinate -s python -m pipeline.tests.test_stage_3_subtitle_generation
caffeinate -s python -m pipeline.tests.test_stage_4_video_rendering
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
