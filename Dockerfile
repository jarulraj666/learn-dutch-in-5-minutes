# Dockerfile for Dutch Language Video Generation with Kokoro TTS

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for FFmpeg, audio processing, and Kokoro
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    build-essential \
    libsndfile1 \
    libsndfile1-dev \
    espeak-ng \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Kokoro TTS from PyPI (kokoro-onnx)
RUN pip install --no-cache-dir kokoro-onnx soundfile

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p output/videos output/audio output/visuals output/scripts db

# Pre-warm Kokoro model (downloads and caches ONNX model into image)
RUN python -c "from kokoro_onnx import Kokoro; Kokoro()" || true

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV TTS_PROVIDER=kokoro
ENV OUTPUT_DIR=output
ENV VIDEO_OUTPUT_DIR=output/videos
ENV LANGUAGE=nl

# Default command
CMD ["python", "-m", "pipeline.run_pipeline", "--language", "nl", "--level", "A1", "--single-agent"]
