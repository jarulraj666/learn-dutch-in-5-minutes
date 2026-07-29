# Docker Deployment Guide - Kokoro TTS

This guide shows how to deploy and run the Dutch Language Video Generator with Kokoro TTS in Docker.

## Prerequisites

✅ **Required:**
- Docker: https://docs.docker.com/get-docker/
- Docker Compose: https://docs.docker.com/compose/install/
- Ollama running locally: https://ollama.ai/

✅ **Optional:**
- Gemini API key (for Gemini TTS alternative)
- YouTube OAuth credentials (for publishing)

## Quick Start (3 steps)

### Step 1: Set up environment
```bash
cp .env.docker .env
# Edit .env and add your API keys if needed
```

### Step 2: Start Docker container
```bash
docker-compose up -d
```

### Step 3: Generate a video
```bash
docker-compose exec dutch-video-generator \
  python -m pipeline.run_pipeline --language nl --level A1 --single-agent
```

Videos are saved to `output/videos/episode_*.mp4`

---

## Usage Examples

### Generate with English instead of Dutch
```bash
docker-compose exec dutch-video-generator \
  python -m pipeline.run_pipeline --language en --level A1 --single-agent
```

### View logs in real-time
```bash
docker-compose logs -f dutch-video-generator
```

### Run interactive shell inside container
```bash
docker-compose exec dutch-video-generator /bin/bash
```

### Initialize database
```bash
docker-compose exec dutch-video-generator python -m pipeline.db --init
```

### Render a specific episode
```bash
docker-compose exec dutch-video-generator \
  python -m pipeline.render_video output/episode_5.json
```

### Preview generated video
```bash
docker-compose exec dutch-video-generator \
  python -m pipeline.preview_video --latest
```

---

## Configuration

### Default Settings (Docker)
- **TTS Provider:** Kokoro (local, no API key needed)
- **Language:** Dutch (nl)
- **Ollama Base URL:** http://host.docker.internal:11434
- **CPU Limit:** 2 cores
- **Memory Limit:** 4GB

### Customize via .env
Edit `.env` to change:
```env
TTS_PROVIDER=kokoro      # or: macos_say, gemini
LANGUAGE=nl              # or: en
OUTPUT_DIR=output
VIDEO_OUTPUT_DIR=output/videos
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

### Override via environment variable
```bash
docker-compose run -e TTS_PROVIDER=gemini dutch-video-generator \
  python -m pipeline.run_pipeline --language nl --level A1 --single-agent
```

---

## Troubleshooting

### ❌ "Ollama not found"
**Problem:** Connection refused to Ollama
```
Error connecting to http://host.docker.internal:11434
```

**Solution (macOS/Windows):**
```bash
# Ensure Ollama is running
ollama serve

# Verify Ollama is accessible
curl http://localhost:11434/api/tags
```

**Solution (Linux):**
```bash
# Use Ollama Docker container
docker run -d --name ollama -p 11434:11434 ollama/ollama

# Update docker-compose.yml:
# OLLAMA_BASE_URL=http://ollama:11434

# Add network link:
# network_mode: host
```

### ❌ "No space left on device"
**Problem:** Container disk full
```
OSError: [Errno 28] No space left on device
```

**Solution:**
```bash
# Clean up Docker
docker system prune -a

# Check disk space
df -h

# Remove output/archive if needed
rm -rf output/archive/*
```

### ❌ "Audio generation failed"
**Problem:** No audio segments generated
```
"audio_segments_found": 0
```

**Solution:**
```bash
# Check Kokoro is working
docker-compose exec dutch-video-generator python -c "from kokoro import KokoroTTS; tts = KokoroTTS()"

# Check audio directory permissions
docker-compose exec dutch-video-generator ls -la output/audio/
```

### ❌ "Video won't play"
**Problem:** MP4 file is corrupt
```
Video plays but has no audio/subtitles
```

**Solution:**
```bash
# Check render manifest for errors
cat output/render_manifest_*.json | jq .

# Verify FFmpeg
docker-compose exec dutch-video-generator ffmpeg -version

# Re-render video
docker-compose exec dutch-video-generator \
  python -m pipeline.render_video output/episode_5.json
```

---

## Performance Tuning

### Increase resource limits
Edit `docker-compose.yml`:
```yaml
deploy:
  resources:
    limits:
      cpus: '4'          # Increase CPU
      memory: 8G         # Increase RAM
```

### Rebuild after changes
```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

---

## Cleanup

### Stop container
```bash
docker-compose down
```

### Remove container and image
```bash
docker-compose down --rmi all
```

### Remove all Docker data
```bash
docker system prune -a --volumes
```

---

## Performance Notes

- **First run:** ~30-60 seconds (Kokoro model download)
- **Subsequent runs:** ~15-30 seconds (cached model)
- **Video encoding:** 1-3 minutes depending on system
- **Total time:** ~5-10 minutes per episode

---

## Support

For issues or questions:
1. Check logs: `docker-compose logs -f`
2. Verify Ollama is running
3. Ensure `.env` is properly configured
4. Check disk space: `docker system df`
