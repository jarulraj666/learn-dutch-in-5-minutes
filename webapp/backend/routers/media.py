from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

ROOT = Path(__file__).resolve().parent.parent.parent.parent

router = APIRouter()


def _safe_resolve(rel_path: str) -> Path:
    """Resolve a relative path, rejecting anything outside ROOT."""
    p = (ROOT / rel_path).resolve()
    if not str(p).startswith(str(ROOT)):
        raise HTTPException(status_code=403, detail="Access denied")
    if not p.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return p


@router.get("/media/audio")
def serve_audio(path: str):
    p = _safe_resolve(path)
    return FileResponse(p, media_type="audio/wav")


@router.get("/media/video")
def serve_video(path: str):
    p = _safe_resolve(path)
    return FileResponse(p, media_type="video/mp4")


@router.get("/media/image")
def serve_image(path: str):
    p = _safe_resolve(path)
    suffix = p.suffix.lower()
    media_type = {"png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(suffix, "image/png")
    return FileResponse(p, media_type=media_type)


@router.get("/media/subtitle")
def serve_subtitle(path: str):
    p = _safe_resolve(path)
    return FileResponse(p, media_type="text/plain")


@router.get("/media/artifact")
def serve_artifact(path: str):
    p = _safe_resolve(path)
    return FileResponse(p, media_type="application/json")
