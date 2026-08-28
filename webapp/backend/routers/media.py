from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, Form
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


@router.get("/media/subtitle-vtt")
def serve_subtitle_vtt(path: str):
    """Convert an SRT file to WebVTT on-the-fly and serve with correct MIME type.

    Browsers require text/vtt for <track> elements to render subtitles.
    """
    from fastapi.responses import Response

    p = _safe_resolve(path)
    srt_text = p.read_text(encoding="utf-8")

    # SRT → WebVTT conversion:
    # 1. Replace "," decimal separator in timestamps with "."
    # 2. Prepend the WEBVTT header
    import re
    vtt = re.sub(
        r"(\d{2}:\d{2}:\d{2}),(\d{3})",
        r"\1.\2",
        srt_text,
    )
    vtt = "WEBVTT\n\n" + vtt.lstrip()

    return Response(content=vtt, media_type="text/vtt")


@router.get("/media/artifact")
def serve_artifact(path: str):
    p = _safe_resolve(path)
    return FileResponse(p, media_type="application/json")


@router.post("/media/upload-scene-image")
async def upload_scene_image(
    topic_id: str = Form(...),
    scene_num: int = Form(...),
    format: str = Form(...),
    file: UploadFile = Form(...),
):
    """Upload a manually generated scene image and update the artifact.

    format: "16x9" or "9x16"
    """
    from services.artifact import load_artifact_from_db, save_artifact

    artifact = load_artifact_from_db(topic_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail=f"Artifact not found for topic {topic_id}")

    level = artifact.get("level", "A1A2")
    category = artifact.get("category", "dialogue")
    title_slug = artifact.get("title_slug", topic_id)
    script = artifact.get("script", {}) or {}
    topic_title = (
        artifact.get("topic_title") or script.get("topic_title", title_slug)
    ).lower().replace(" ", "_")

    suffix = Path(file.filename or "").suffix.lower() or ".png"
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(status_code=400, detail="Unsupported image format")
    content = await file.read()

    if format == "16x9":
        dest_dir = ROOT / "output" / level / category / "visuals" / f"episode_{topic_id}_{topic_title}"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"episode_{topic_id}_scene{scene_num}{suffix}"
        dest.write_bytes(content)
        rel = str(dest.relative_to(ROOT))

        existing = artifact.get("generated_image_files", []) or []
        pattern = re.compile(rf"scene{scene_num}\.", re.IGNORECASE)
        updated = [f for f in existing if not pattern.search(Path(f).name)]
        updated.append(rel)
        updated.sort(key=lambda p: int(m.group(1)) if (m := re.search(r"scene(\d+)", Path(p).name, re.IGNORECASE)) else 0)
        artifact["generated_image_files"] = updated
        if scene_num == 1 or not artifact.get("generated_image_file"):
            artifact["generated_image_file"] = rel

    elif format == "9x16":
        dest_dir = ROOT / "output" / level / category / "shorts" / f"episode_{topic_id}_{title_slug}" / "images"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"scene_{scene_num}_vertical{suffix}"
        dest.write_bytes(content)
        rel = str(dest.relative_to(ROOT))

        shorts_images = artifact.get("shorts_images", []) or []
        updated_si = False
        for si in shorts_images:
            if si.get("scene") == scene_num:
                si["image_path"] = rel
                updated_si = True
                break
        if not updated_si:
            shorts_images.append({"scene": scene_num, "image_path": rel})
        artifact["shorts_images"] = shorts_images

    else:
        raise HTTPException(status_code=400, detail="format must be '16x9' or '9x16'")

    save_artifact(topic_id, artifact)
    return {"path": rel, "scene": scene_num, "format": format}
