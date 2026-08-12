# Dutch Language Video Generator

Automatically generates A1-A2 level Dutch lesson videos with narrated dialogue, karaoke subtitles, background images, and YouTube publishing.

## Features
- Dialogue and narrated lessons (common words, grammar, vocabulary, dialogue)
- Gemini TTS audio generation with slow A1-A2 pacing
- WhisperX speech-to-text for karaoke subtitle sync
- AI-generated scene images (single or multi-scene per episode)
- FFmpeg video assembly with burned-in subtitles
- YouTube upload with auto-created playlists, title, description, and tags
- Instagram Reels upload (one vertical short per scene via Meta Graph API)
- SQLite topic memory with status tracking (`pending` → `generated` → `done`)
- Single entry point: `pipeline/run_pipeline.py`
- **Web dashboard** for managing topics, triggering the pipeline, and monitoring publishing

## Project Structure

```
pipeline/
  run_pipeline.py       ← single entry point (full pipeline + interactive stage re-runs)
  stages.py             ← pure stage functions shared across all modes
  settings.py           ← config and env vars
  utils.py              ← shared helpers

  core/                 ← DB, topic selection, storage, scheduling
  generate/             ← script, metadata, voice, subtitles, image, QA
  clients/              ← Gemini TTS and Ollama API clients
  publish/              ← YouTube upload, Instagram Reels, render video, publish queue

config/
  playlists.yaml        ← YouTube playlist names by level + category
  topic_backlog.yaml    ← all topics across 4 categories
  pedagogy.yaml         ← pacing, speech rate, timing settings
  scheduling.yaml       ← publish cadence
  visual_style.yaml     ← render resolution, FPS, encoding settings

prompts/
  A1A2/
    common_words.md     ← prompt for common words lessons
    grammar.md          ← prompt for grammar lessons
    vocabulary.md       ← prompt for vocabulary lessons
    dialogue.md         ← prompt for dialogue lessons

webapp/
  backend/              ← FastAPI server (uses the same .venv311 as the pipeline)
  frontend/             ← Next.js 14 + Tailwind CSS dashboard
  scripts/
    start_backend.sh    ← start FastAPI on :8000
    start_frontend.sh   ← start Next.js on :3000
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

> **Tip:** Prefix any long-running command with `caffeinate -s` to prevent macOS from sleeping.

## Database Management

**Topic statuses:** `pending` → *(pipeline runs)* → `generated` → *(upload succeeds)* → `done`

**Reset a topic to pending (re-run it):**
```bash
sqlite3 db/content.db "UPDATE topics SET status = 'pending' WHERE id = 'your_topic_id';"
```

**View all topics and their statuses:**
```bash
sqlite3 db/content.db "SELECT id, status, category, level FROM topics ORDER BY order_index;"
```

## Running the Pipeline

**Generate next pending topic (single video):**
```bash
caffeinate -s python -m pipeline.run_pipeline --level A1A2 --category dialogue
caffeinate -s python -m pipeline.run_pipeline --level A1A2 --category dialogue --no-upload
```

**Generate a specific topic by ID:**
```bash
caffeinate -s python -m pipeline.run_pipeline --topic-id weather_chat --no-upload
```

**Generate only the script (no audio, image, render, upload):**
```bash
caffeinate -s python -m pipeline.run_pipeline --topic-id weather_chat --script-only
```
Creates an artifact with just the script and metadata. Use `--artifact` to add other stages interactively.

**Batch mode — generate N videos:**
```bash
caffeinate -s python -m pipeline.run_pipeline --level A1A2 --category common_words --count 5 --no-upload
caffeinate -s python -m pipeline.run_pipeline --level A1A2 --category dialogue --count 3
```

**Resume a failed run from its checkpoint:**
```bash
caffeinate -s python -m pipeline.run_pipeline --resume output/A1A2/dialogue/.checkpoint_weather_chat.json
```

## Re-running Stages on an Existing Episode

Use `--artifact` to open an interactive menu on any existing episode artifact:

```bash
caffeinate -s python -m pipeline.run_pipeline --artifact output/A1A2/dialogue/episode_xxx.json
```

Menu prompt:

```
📺  talk_about_the_weather_mooi_weer_regen_temperatuur
    Level: A1A2 | Category: dialogue

   1) Script
   2) Image
   3) Audio
   4) Subtitles
   5) Audio QA
   6) Subtitle QA
   7) Render video
   8) Upload YouTube
   9) Upload captions

Select stages to run — space or comma separated (e.g. '3 4 7')
Type 'all' to run every stage, or '0' to exit.

>
```

Pick any combination: `3 4 7` runs Audio → Subtitles → Render. Each stage updates the artifact in place.

## Pipeline Arguments Reference

**`--artifact PATH`**
Load an existing episode artifact and show the interactive stage menu. Skips full pipeline.

**`--topic-id TOPIC_ID`**
Run the full pipeline for a specific topic ID instead of auto-selecting the next pending one. Required when used with `--script-only`.

**`--script-only`**
Generate only the script and create an artifact (skip audio, subtitles, image, render, upload). Requires `--topic-id`. Useful for reviewing/tweaking scripts before full generation.

**`--level`** (default: `A1A2`, choices: `A1A2`, `B1`, `B2`)
CEFR language proficiency level.

**`--category`** (choices: `common_words`, `grammar`, `vocabulary`, `dialogue`)
Filter topics by category.

**`--count N`**
Generate exactly N videos in sequence.

**`--single`**
Generate only 1 video (equivalent to `--count 1`).

**`--no-upload`**
Skip YouTube upload. Topic is marked `generated` (not `done`) until uploaded.

**`--resume CHECKPOINT`**
Resume a failed pipeline run from a checkpoint file (`output/{level}/{category}/.checkpoint_{topic_id}.json`).

**`--language`** (default: `nl`)
Language code for the target content.

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

## YouTube Playlists

Videos are automatically assigned to the correct playlist:

| Category     | Playlist                         |
|---|---|
| common_words | A1 \| Beginners \| Common Words  |
| grammar      | A1 \| Beginners \| Grammar       |
| vocabulary   | A1 \| Beginners \| Vocabulary    |
| dialogue     | A1 \| Beginners \| Dialogue      |

## Web Dashboard

A local web app for managing topics, triggering the pipeline, previewing media, and managing YouTube/Instagram publishing.

### Dashboard Setup

**Backend** (FastAPI — reuses the pipeline's `.venv311`):
```bash
./webapp/scripts/start_backend.sh
# → http://localhost:8000
```

**Frontend** (Next.js — separate terminal):
```bash
./webapp/scripts/start_frontend.sh
# → http://localhost:3000
```

Open **http://localhost:3000** in your browser.

### Dashboard Pages

| Page | URL | Description |
|---|---|---|
| Dashboard | `/` | Stats cards, active pipeline jobs, recent activity, system health banner |
| Topics | `/topics` | Filterable table — filter by level, category, status, search by name |
| Topic Detail | `/topics/[id]` | 6-tab view: Overview, Script, Media, Pipeline, YouTube, Instagram |
| Run Pipeline | `/run` | Launch the pipeline with a form + live SSE log streaming terminal |
| Publish Queue | `/publish` | YouTube publish queue — dry-run preview and execute uploads |
| Config | `/config` | Edit YAML config files in-browser with validation before save |

### Topic Detail Tabs

- **Overview** — metadata, status, playlist, publish dates
- **Script** — speaker-coloured dialogue, grammar notes, quiz questions
- **Media** — audio player, video player, scene image gallery, subtitle download links; checkpoint warning if a run was interrupted
- **Pipeline** — stage-by-stage status indicators; select any combination of stages and re-run them (mirrors `--artifact` CLI mode)
- **YouTube** — embedded YouTube player, video ID, scheduled/published dates
- **Instagram** — per-scene Reels grid with video preview, draft/published status, "Publish Draft" button

### System Health

The dashboard banner at `/` checks:
- SQLite database accessible
- `ffmpeg` present
- `GEMINI_TTS_API_KEYS` set
- `YOUTUBE_CLIENT_SECRETS` set + `youtube_token.json` present
- `INSTAGRAM_ACCESS_TOKEN`, `INSTAGRAM_ACCOUNT_ID`, and video hosting configured

### Backend API Reference

```
GET  /api/topics                         list topics (filter: level, category, status, search)
GET  /api/topics/:id                     topic detail + artifact media
PATCH /api/topics/:id/status             reset status (e.g. back to pending)
GET  /api/stats                          counts by status / level / category

POST /api/pipeline/run                   start pipeline run → returns job_id
POST /api/pipeline/run-stages            re-run specific stages on an artifact
POST /api/pipeline/abort/:job_id         SIGTERM a running job
GET  /api/pipeline/jobs                  list all jobs
GET  /api/pipeline/jobs/:job_id          job detail + full log buffer
GET  /api/pipeline/logs/:job_id          SSE stream of live log output

GET  /api/publish/queue                  publish_jobs table
POST /api/publish/dry-run                preview upload payloads
POST /api/publish/execute                trigger real YouTube uploads
PATCH /api/publish/:job_id/reschedule    update scheduled_at
GET  /api/publish/instagram/:id/shorts   list scene shorts + Reel status
POST /api/publish/instagram/:id/publish-draft  publish a held Instagram container

GET  /api/media/audio?path=…             stream WAV file
GET  /api/media/video?path=…             stream MP4 file
GET  /api/media/image?path=…             serve generated image
GET  /api/media/subtitle?path=…          serve SRT/ASS subtitle file

GET  /api/config/:name                   read YAML config
PUT  /api/config/:name                   write YAML config (validates before save)
GET  /api/health                         system readiness checks
```

## Notes
- Requires `ffmpeg` for video assembly. Without it, a render manifest is produced and assembly is skipped gracefully.
- Real YouTube upload requires `YOUTUBE_CLIENT_SECRETS` env var and first-run OAuth browser consent. Token saved to `output/youtube_token.json`.
- Rendered videos are archived to `output/archive/` with stable paths stored in DB for upload retries.
- Dutch subtitle tracks are uploaded as separate YouTube caption tracks when present.
- The artifact JSON is written incrementally after each stage — if the pipeline fails, a partial artifact exists on disk and can be resumed via `--artifact`.
