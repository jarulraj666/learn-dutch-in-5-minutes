from __future__ import annotations

from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent.parent.parent

ALLOWED_CONFIGS = {
    "playlists",
    "pedagogy",
    "scheduling",
    "visual_style",
    "topic_backlog",
}

router = APIRouter()


def _config_path(name: str) -> Path:
    return ROOT / "config" / f"{name}.yaml"


@router.get("/config/{name}")
def get_config(name: str):
    if name not in ALLOWED_CONFIGS:
        raise HTTPException(status_code=404, detail="Config not found")
    p = _config_path(name)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Config file missing")
    return {"name": name, "content": p.read_text(encoding="utf-8")}


class ConfigUpdate(BaseModel):
    content: str  # raw YAML string


@router.put("/config/{name}")
def update_config(name: str, req: ConfigUpdate):
    if name not in ALLOWED_CONFIGS:
        raise HTTPException(status_code=404, detail="Config not found")

    # Validate YAML before saving
    try:
        yaml.safe_load(req.content)
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid YAML: {exc}")

    p = _config_path(name)
    p.write_text(req.content, encoding="utf-8")
    return {"ok": True}
