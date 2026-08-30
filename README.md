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

learn/                  ← public learner app (separate from the internal dashboard)
  backend/              ← FastAPI learner API (own venv at learn/.venv)
  frontend/             ← Next.js + Auth.js (Google sign-in)
  db/schema.sql         ← PostgreSQL schema (content + users + progress)
  scripts/
    apply_schema.sh     ← apply schema.sql to $DATABASE_URL
    start_backend.sh    ← start learner API on :8001
    start_frontend.sh   ← start learner frontend on :3001
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
sqlite3 db/content.db "UPDATE topics SET status = 'pending' WHERE id = 'hotel_checkin';"
```

**Delete all local files for an episode (audio, subtitles, images, video, shorts, scripts) and reset topic to pending:**
```bash
python -m pipeline.run_pipeline --cleanup output/A1A2/dialogue/episode_<topic_id>_<title_slug>.json
```

> This does **not** delete anything from YouTube. It only removes local output files and resets the DB status to `pending` so the episode can be regenerated from scratch.

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

**`--category`** (choices: `course_intro`, `common_words`, `grammar`, `vocabulary`, `dialogue`)
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

**Stop the servers:**
```bash
lsof -ti :8000 | xargs kill -9
lsof -ti :3000 | xargs kill -9
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

## Learner Web App

The public, Udemy-style course site your learners use. It is a **separate application**
from the internal dashboard above — different ports, different database, its own auth.
The internal dashboard has no login and can trigger the pipeline and publish to social
media, so the two must never share a process.

|  | Internal dashboard | Learner app |
|---|---|---|
| Backend | `:8000` | `:8001` |
| Frontend | `:3000` | `:3001` |
| Database | SQLite `db/content.db` | PostgreSQL |
| Auth | none | Google sign-in (Auth.js) |

### Start the learner app

After completing the first-time setup below, start the learner backend and frontend in separate terminals:

```bash
./learn/scripts/start_backend.sh
# Learner API: http://localhost:8001
```

```bash
./learn/scripts/start_frontend.sh
# Learner app: http://localhost:3001
```

Open [http://localhost:3001](http://localhost:3001) in your browser. To stop the local services:

```bash
lsof -ti :8001 | xargs kill -9
lsof -ti :3001 | xargs kill -9
```

### Course structure

The learner course is **not** organised by generation category. Lessons are arranged into
progressive units that deliberately mix vocabulary, high-frequency words and grammar, so
grammar arrives at the point the learner needs it rather than in a block at the end.

| # | Unit | Required | Lessons |
|---|---|---|---|
| 0 | Start Here | yes | 15 — sounds, greetings and enough grammar to speak on day one |
| 1 | People and Possessions | yes | 11 |
| 2 | Describing Things | yes | 9 |
| 3 | Time and Daily Routine | yes | 13 |
| 4 | Food, Shopping and Money | yes | 10 |
| 5 | Out and About | yes | 12 |
| 6 | Work, Health and Free Time | yes | 8 |
| 7 | Grammar | yes | 7 |
| 8 | Advanced Grammar | yes | 10 |
| — | More Lessons | yes | catch-all, hidden while empty |
| — | Dialogue & Listening | **optional add-on** | 13 |

Grammar sits inside a themed unit whenever it has a natural home — modal verbs with ordering
food, prepositions of place with directions, separable verbs with daily routine. Grammar that
belongs to no single situation goes to **Grammar** (past tenses, diminutives, comparatives) or
**Advanced Grammar** (subordinate clauses, future, conditional) rather than being forced into
a themed unit where it does not fit.

Present tense lands in **unit 0, lesson 8** — the learner conjugates a regular verb before
meeting any themed vocabulary. Only required units count toward progress and the certificate.

The curriculum lives in `UNITS` at the top of `pipeline/tools/export_learning_content.py`.
Each entry has a `key`, `title`, `description` and an ordered `lessons` list of topic ids.
To reorder the course, edit that list and re-export — no schema or code change needed.

Supporting constants in the same file:

- `OPTIONAL_MODULES` — units excluded from progress and certificates
- `START_HERE_MAX` — onboarding cap (15), enforced on every run
- `FALLBACK_UNIT` — catches topics missing from `UNITS` so an edit can never drop a lesson
- `DIALOGUE_UNIT` — all `dialogue` topics, ordered by `topics.order_index`

Every export validates the curriculum and reports duplicates, unplaced topics, unknown ids
and cap violations before writing anything:

```bash
python -m pipeline.tools.export_learning_content --dry-run
```

Units with no published lessons are hidden from the learner app, so you can plan a unit
before its videos exist. Modules from a previous curriculum version are pruned automatically.

**The `course_intro` category** holds orientation content — the course welcome and
pronunciation primers. It is English-narrated meta content with its own prompt at
`prompts/A1A2/course_intro.md`, and it has no unit of its own: episodes are placed
individually in `UNITS`.

```bash
caffeinate -s python -m pipeline.run_pipeline --level A1A2 --category course_intro --count 2
```

### First-time setup

**1. Start PostgreSQL** (any instance works — Neon, Supabase, or local Docker):
```bash
docker run -d --name learn-pg \
  -e POSTGRES_USER=learn -e POSTGRES_PASSWORD=learn -e POSTGRES_DB=learn \
  -p 55432:5432 postgres:16-alpine
```

**2. Apply the schema:**
```bash
export DATABASE_URL='postgresql://learn:learn@localhost:55432/learn'
./learn/scripts/apply_schema.sh
```

**3. Create the two env files** from `learn/.env.example`:

| File | Used by | Keys |
|---|---|---|
| `learn/.env` | backend (loaded automatically) | `DATABASE_URL`, `ADMIN_EMAILS`, `LEARN_ALLOWED_ORIGINS`, `LEARN_COMPLETION_PERCENT`, `LEARN_CERTIFICATE_PASS_PERCENT` |
| `learn/frontend/.env.local` | frontend | `DATABASE_URL`, `AUTH_SECRET`, `NEXTAUTH_URL`, `LEARN_API_URL`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `ADMIN_EMAILS` |

Both need `DATABASE_URL` — the frontend uses it for the Auth.js session tables, the backend
for everything else. Generate a real `AUTH_SECRET` with `openssl rand -base64 33`.
Set `DATABASE_SSL=false` for a local Postgres without TLS.

**4. Create a Google OAuth client** — Google Cloud Console → APIs & Services → Credentials
→ **OAuth client ID** → *Web application*:

| Field | Value |
|---|---|
| Authorized JavaScript origins | `http://localhost:3001` |
| Authorized redirect URIs | `http://localhost:3001/api/auth/callback/google` |

On the **OAuth consent screen**, add your own address under *Test users* while the app is
in Testing mode — otherwise sign-in fails with "Access blocked". Put the client ID and
secret into `learn/frontend/.env.local`.

> A placeholder `GOOGLE_CLIENT_ID` produces `Error 401: invalid_client`.
> A wrong redirect URI produces `redirect_uri_mismatch`.

**5. Set `ADMIN_EMAILS`** in both env files to your email so you get the `admin` role on
first sign-in (required for `/admin`).

### Publish content to the learner app

The learner app never reads `db/content.db`. This export is the only bridge — run it
after each batch of uploads:

```bash
# Preview without writing:
python -m pipeline.tools.export_learning_content --dry-run

# Push published episodes to PostgreSQL:
DATABASE_URL='postgresql://…' python -m pipeline.tools.export_learning_content --prune
```

Only episodes with a YouTube video ID are exported. `--prune` removes lessons that are no
longer exported — always use it after changing module structure, or stale rows linger.

Every lesson should have a quiz before publishing:
```bash
python -m pipeline.tools.backfill_quiz --dry-run   # report gaps
python -m pipeline.tools.backfill_quiz             # generate the missing ones
```

### Run it

Four things must be in place before the app starts: **Postgres running**, **schema applied**,
**`learn/.env` present**, **`learn/frontend/.env.local` present**. Check them in that order if
anything fails.

**1. Postgres** — start it if it isn't already up:
```bash
docker start learn-pg          # existing container
docker ps --filter name=learn-pg   # confirm it's running
```

**2. Backend** — reads `learn/.env`, creates its own venv on first run:
```bash
./learn/scripts/start_backend.sh
# → http://localhost:8001
```
Confirm it is healthy (should report `"ok": true` and a lesson count):
```bash
curl -s localhost:8001/api/health
```

**3. Frontend** — separate terminal, reads `learn/frontend/.env.local`:
```bash
./learn/scripts/start_frontend.sh
# → http://localhost:3001
```

Open **http://localhost:3001**.

**Stop the servers:**
```bash
lsof -ti :8001 | xargs kill -9
lsof -ti :3001 | xargs kill -9
docker stop learn-pg
```

### Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `RuntimeError: DATABASE_URL is not set` | `learn/.env` missing | Create it from `learn/.env.example` — the backend loads `learn/.env`, not `learn/frontend/.env.local` |
| `connection refused` on port 55432 | Postgres not running | `docker start learn-pg` |
| `relation "lessons" does not exist` | Schema not applied | `./learn/scripts/apply_schema.sh` |
| `/api/health` reports `lessons: 0` | No content exported | `python -m pipeline.tools.export_learning_content --prune` |
| `Error 401: invalid_client` | Placeholder `GOOGLE_CLIENT_ID` | Add real credentials to `learn/frontend/.env.local`, then restart the frontend |
| `redirect_uri_mismatch` | Redirect URI mismatch | Must be exactly `http://localhost:3001/api/auth/callback/google` |
| "Access blocked" after choosing an account | Consent screen in Testing mode | Add your email under *Test users* in Google Cloud Console |
| Env change has no effect | Next.js reads env at boot | Restart the frontend |

### Learner app pages

| Page | URL | Description |
|---|---|---|
| Landing | `/` | Marketing page, course list, Google sign-in |
| Courses | `/courses` | One card per CEFR level; B1/B2 shown as "coming soon" |
| Course | `/courses/[level]` | Curriculum — required modules, then the optional add-on |
| Lesson | `/courses/[level]/lessons/[id]` | Video player + playlist sidebar; tabs for overview, vocabulary, grammar, transcript and quiz |
| My learning | `/dashboard` | Progress per course, resume link, recent activity |
| Flashcards | `/flashcards` | SM-2 spaced repetition over vocabulary from completed lessons |
| Certificate | `/courses/[level]/certificate` | Eligibility + claim |
| Profile | `/profile` | Settings, data export, account deletion |
| Admin | `/admin` | Learner list and per-learner progress (`ADMIN_EMAILS` only) |

Progress is tracked with the YouTube IFrame API: a lesson auto-completes at 90% watched and
resumes where you left off. Quizzes are graded server-side — correct answers are never sent
to the browser before submission. A certificate requires every required lesson completed and
every quiz passed at ≥70%.

### Verify the learner API

```bash
DATABASE_URL='postgresql://…' learn/.venv/bin/python learn/backend/tests/smoke.py
```
End-to-end checks covering auth enforcement, progress, quiz grading, certificate gating,
flashcard scheduling and admin access control.

## Notes
- Requires `ffmpeg` for video assembly. Without it, a render manifest is produced and assembly is skipped gracefully.
- Real YouTube upload requires `YOUTUBE_CLIENT_SECRETS` env var and first-run OAuth browser consent. Token saved to `output/youtube_token.json`.
- Rendered videos are archived to `output/archive/` with stable paths stored in DB for upload retries.
- Dutch subtitle tracks are uploaded as separate YouTube caption tracks when present.
- The artifact JSON is written incrementally after each stage — if the pipeline fails, a partial artifact exists on disk and can be resumed via `--artifact`.
