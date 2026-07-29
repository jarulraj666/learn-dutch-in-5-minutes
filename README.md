# Conversational Dutch Video Generator (MVP)

This project generates A1-level conversational Dutch lesson content with:
- quiz section at the end
- grammar notes in YouTube description
- 2-day publishing cadence
- local SQLite memory for scripts, titles, topics, and multilingual reuse
- playlist assignment metadata
- multi-agent workflow across content and media stages
- 5-minute output target (300s) for each generated lesson video
- 3-minute conversation segment target (about 180s) inside each lesson
- Slow A1 pacing with reduced TTS speech rate and slower dialogue timing assumptions
- Dutch and English subtitles are generated for every episode

## MVP scope implemented
- Local topic selection with anti-repeat checks
- Multi-agent generation using Ollama:
	- Conversation Agent
	- Grammar and Translation Review Agent
	- Vocabulary Agent
	- Quiz Agent
	- Voice Planning Agent
	- Subtitle Planning Agent
	- Video Assembly Planning Agent
	- Upload Preparation Agent
- Metadata generation with required grammar sections
- Publish slot scheduler (every 2 days)
- SQLite persistence for content memory
- Voice generation on macOS via `say`
- Subtitle file generation (`.srt`)
- FFmpeg video assembly (when `ffmpeg` is installed)
- YouTube upload payload generation and optional real upload via OAuth

## Setup
1. Install Python 3.11+.
2. Copy `.env.example` to `.env` and set values.
3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Initialize database schema:

```bash
python -m pipeline.db --init
```

5. Run one generation cycle:

```bash
python -m pipeline.run_pipeline --language nl --level A1
```

6. Optional: run in original single-agent mode:

```bash
python -m pipeline.run_pipeline --language nl --level A1 --single-agent
```

7. Optional: generate render manifest and YouTube upload payload dry-run:

```bash
python -m pipeline.render_video output/episode_1.json
python -m pipeline.upload_youtube output/episode_1.json --dry-run
```

8. Optional: real YouTube upload (after render and OAuth setup):

```bash
python -m pipeline.upload_youtube output/episode_1.json --video-file output/episode_1.mp4
```

9. Process scheduled publish jobs from local DB:

```bash
# Dry-run (works without YouTube secrets)
python -m pipeline.publish_pending

# Real execution (requires YouTube OAuth secrets)
python -m pipeline.publish_pending --execute
```

10. Retry a specific failed upload job:

```bash
python -m pipeline.publish_pending --execute --job-id 12
```

11. Preview generated video locally:

```bash
# Preview by latest publish job
python -m pipeline.preview_video --latest

# Preview by publish job id
python -m pipeline.preview_video --job-id 12

# Preview by artifact path
python -m pipeline.preview_video --artifact output/episode_12.json
```

## Notes
- This MVP writes generated artifacts to `output/`.
- If `ffmpeg` is not installed, a render manifest is produced and video assembly is skipped gracefully.
- If the local `ffmpeg` build has no `subtitles` filter, MP4 is still assembled and subtitles remain as external `output/subtitles.srt`.
- Real YouTube upload requires `YOUTUBE_CLIENT_SECRETS` and first-run OAuth consent.
- Rendered videos are archived to `output/archive/` and their stable paths are stored in DB for later upload retries.
- When generated speech is short, the pipeline expands practice dialogue and pads timeline to ensure a 300-second video.
- Cartoon/paint visual scene is rendered directly by FFmpeg shape filters for each generated episode.
- Older episodes generated before this change may still look plain; generate a new episode and preview latest to see the cartoon style.
- Conversation expansion avoids repeating identical lines by creating unique guided practice turns.
- In real upload mode, Dutch and English subtitle files are uploaded as separate YouTube caption tracks when present.
- Visual backgrounds are generated per episode using `ollama run x/z-image-turbo` and saved as PNG files in `output/visuals/`.
- Visual prompt enforces one male and one female cartoon human in conversation, with background composed from topic title cues.

## Deploy via Docker

### Prerequisites
- Docker and Docker Compose installed
- Ollama running locally (for LLM generation) — accessible via `host.docker.internal:11434` on macOS/Windows
- `.env` file configured with API keys (if using Gemini or YouTube)

### Quick Start with Docker

1. **Build and run with Docker Compose:**
```bash
docker-compose up -d
```

2. **View logs:**
```bash
docker-compose logs -f dutch-video-generator
```

3. **Run a single pipeline cycle:**
```bash
docker-compose exec dutch-video-generator python -m pipeline.run_pipeline --language nl --level A1 --single-agent
```

4. **Access generated files:**
```bash
# Videos are in output/videos/
ls -la output/videos/
```

5. **Stop the container:**
```bash
docker-compose down
```

### Manual Docker Commands

**Build the image:**
```bash
docker build -t dutch-video-generator:kokoro-latest .
```

**Run the container:**
```bash
docker run -it \
  --env TTS_PROVIDER=kokoro \
  --env OLLAMA_BASE_URL=http://host.docker.internal:11434 \
  -v $(pwd)/output:/app/output \
  -v $(pwd)/db:/app/db \
  --env-file .env \
  dutch-video-generator:kokoro-latest \
  python -m pipeline.run_pipeline --language nl --level A1 --single-agent
```

### Docker Configuration

- **Image:** `python:3.11-slim` with FFmpeg and audio libraries
- **TTS Provider:** Kokoro (local, no API key needed)
- **Ollama:** Connects to `host.docker.internal:11434` (macOS/Windows) or `host.docker.internal` (Linux with extra setup)
- **CPU/Memory:** Limited to 2 CPU cores and 4GB RAM (adjustable in docker-compose.yml)
- **Volumes:**
  - `./output:/app/output` — Generated videos, audio, subtitles
  - `./db:/app/db` — SQLite database persistence
  - `./.env:/app/.env:ro` — Environment configuration (read-only)

### Troubleshooting Docker

**If Ollama is not found:**
- Ensure Ollama is running: `ollama serve`
- On Linux, use the Ollama container instead:
  ```bash
  docker run -d --name ollama -p 11434:11434 ollama/ollama
  # Then update docker-compose.yml: OLLAMA_BASE_URL=http://ollama:11434
  ```

**If videos are not generated:**
- Check logs: `docker-compose logs dutch-video-generator`
- Verify FFmpeg is available: `docker-compose exec dutch-video-generator ffmpeg -version`
- Ensure `output/videos/` exists: Created automatically by the container

**To rebuild after code changes:**
```bash
docker-compose build --no-cache
docker-compose up -d
```
