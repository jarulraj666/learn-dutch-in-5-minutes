from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from fastapi import APIRouter

ROOT = Path(__file__).resolve().parent.parent.parent.parent

router = APIRouter()


def _check_env(key: str) -> bool:
    import os
    return bool(os.getenv(key))


def _check_file(path: str) -> bool:
    return (ROOT / path).exists()


@router.get("/health")
def health_check():
    import os

    checks: dict[str, dict] = {}

    # Database
    db = ROOT / "db" / "content.db"
    checks["database"] = {"ok": db.exists(), "path": str(db)}

    # ffmpeg
    ffmpeg_path = shutil.which("ffmpeg")
    checks["ffmpeg"] = {"ok": bool(ffmpeg_path), "path": ffmpeg_path}

    # Gemini TTS keys
    gemini_keys = os.getenv("GEMINI_TTS_API_KEYS") or os.getenv("GEMINI_API_KEYS")
    checks["gemini_tts"] = {"ok": bool(gemini_keys), "hint": "GEMINI_TTS_API_KEYS"}

    # YouTube
    yt_secrets = os.getenv("YOUTUBE_CLIENT_SECRETS")
    yt_token = (ROOT / "output" / "youtube_token.json").exists()
    checks["youtube_secrets"] = {
        "ok": bool(yt_secrets),
        "hint": "YOUTUBE_CLIENT_SECRETS",
    }
    checks["youtube_token"] = {
        "ok": yt_token,
        "hint": "output/youtube_token.json",
        "action": None if yt_token else "reauthorize",
    }

    # Instagram
    ig_token = _check_env("INSTAGRAM_ACCESS_TOKEN")
    ig_account = _check_env("INSTAGRAM_ACCOUNT_ID")
    ig_hosting = _check_env("GCS_BUCKET") or _check_env("INSTAGRAM_VIDEO_BASE_URL")
    checks["instagram_token"] = {"ok": ig_token, "hint": "INSTAGRAM_ACCESS_TOKEN"}
    checks["instagram_account"] = {"ok": ig_account, "hint": "INSTAGRAM_ACCOUNT_ID"}
    checks["instagram_hosting"] = {
        "ok": bool(ig_hosting),
        "hint": "GCS_BUCKET or INSTAGRAM_VIDEO_BASE_URL",
    }

    # .env file
    checks["env_file"] = {"ok": (ROOT / ".env").exists(), "path": ".env"}

    all_ok = all(v["ok"] for v in checks.values())
    return {"ok": all_ok, "checks": checks}
