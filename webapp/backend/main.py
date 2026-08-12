"""FastAPI backend for the Dutch Video Generation dashboard."""
from __future__ import annotations

import sys
from pathlib import Path

# Make the project root importable so pipeline.settings etc. work
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from routers import config, health, media, pipeline, publish, topics

app = FastAPI(title="Dutch Video Generation Dashboard", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(topics.router, prefix="/api")
app.include_router(pipeline.router, prefix="/api")
app.include_router(publish.router, prefix="/api")
app.include_router(media.router, prefix="/api")
app.include_router(config.router, prefix="/api")

# Serve output files (audio, video, images) statically
output_dir = ROOT / "output"
if output_dir.exists():
    app.mount("/output", StaticFiles(directory=str(output_dir)), name="output")
