"""Resolve artifact JSON + associated media files for a topic."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent.parent


def find_artifact(topic_id: str) -> Path | None:
    """Search output dirs for the most recent artifact JSON for a topic."""
    for path in sorted(ROOT.glob(f"output/**/episode_{topic_id}*.json"), reverse=True):
        # Skip render manifests and checkpoints
        if "render_manifest" in path.name or path.name.startswith("."):
            continue
        return path
    return None


def load_artifact(artifact_path: str | Path) -> dict[str, Any] | None:
    p = Path(artifact_path)
    if not p.is_absolute():
        p = ROOT / p
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def get_topic_media(topic_id: str, artifact_path: str | None = None) -> dict:
    """Return available media paths relative to the project root."""
    result: dict[str, Any] = {
        "artifact": None,
        "audio": None,
        "video": None,
        "images": [],
        "subtitles": {"ass": None, "srt_nl": None, "srt_en": None},
        "shorts": [],
        "checkpoint": None,
    }

    artifact: dict | None = None
    if artifact_path:
        artifact = load_artifact(artifact_path)
    if artifact is None:
        found = find_artifact(topic_id)
        if found:
            result["artifact"] = str(found.relative_to(ROOT))
            artifact = load_artifact(found)

    if artifact:
        result["artifact"] = result["artifact"] or artifact.get("artifact_path")

        # Audio
        voice = artifact.get("voice_plan", {})
        wav = voice.get("audio_file") or artifact.get("audio_file")
        if wav and Path(ROOT / wav).exists():
            result["audio"] = wav

        # Video
        for key in ("video_file", "rendered_video"):
            vid = artifact.get(key)
            if vid and Path(ROOT / vid).exists():
                result["video"] = vid
                break

        # Images
        imgs = artifact.get("all_image_files") or []
        if not imgs and artifact.get("primary_image"):
            imgs = [artifact["primary_image"]]
        result["images"] = [p for p in imgs if Path(ROOT / p).exists()]

        # Subtitles
        sub = artifact.get("subtitle_plan", {})
        for key, field in [("ass", "ass_file"), ("srt_nl", "nl_srt"), ("srt_en", "srt_en")]:
            path = sub.get(field)
            if path and Path(ROOT / path).exists():
                result["subtitles"][key] = path

        # YouTube Shorts
        shorts = artifact.get("shorts", [])
        result["shorts"] = [
            {
                "scene": s.get("scene"),
                "description": s.get("description"),
                "video_file": s.get("video_file"),
                "reel_id": s.get("reel_id"),
                "container_id": s.get("container_id"),
                "permalink": s.get("permalink"),
                "draft": s.get("draft", False),
            }
            for s in shorts
            if s.get("video_file") and Path(ROOT / s["video_file"]).exists()
        ]

    # Checkpoint
    for cp in ROOT.glob(f"output/**/.checkpoint_{topic_id}.json"):
        result["checkpoint"] = str(cp.relative_to(ROOT))
        break

    return result
