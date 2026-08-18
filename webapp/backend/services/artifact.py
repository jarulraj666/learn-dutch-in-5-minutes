"""Resolve artifact JSON + associated media files for a topic.

The DB (publish_jobs.artifact_json) is the single source of truth.
The canonical disk path is a derived cache materialised on demand.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent.parent


# ---------------------------------------------------------------------------
# Core load / save (DB-primary)
# ---------------------------------------------------------------------------

def load_artifact_from_db(topic_id: str) -> dict[str, Any] | None:
    """Load artifact directly from the DB blob.  Returns None if not found."""
    try:
        from services.db import get_connection

        sql = """
            SELECT pj.artifact_json
            FROM publish_jobs pj
            JOIN canonical_scripts cs ON cs.id = pj.canonical_script_id
            WHERE cs.topic_id = ?
            ORDER BY pj.id DESC
            LIMIT 1
        """
        with get_connection() as conn:
            row = conn.execute(sql, [topic_id]).fetchone()
        if row and row["artifact_json"]:
            return json.loads(row["artifact_json"])
    except Exception:
        pass
    return None


def save_artifact(topic_id: str, artifact: dict[str, Any]) -> bool:
    """Persist artifact to DB.  Returns True on success."""
    try:
        from services.db import update_publish_job_artifact_json
        return update_publish_job_artifact_json(topic_id, artifact)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Legacy helpers kept for backward compatibility
# ---------------------------------------------------------------------------

def find_artifact(topic_id: str) -> None:
    """Removed: artifacts are DB-only. Kept as stub for import compatibility."""
    return None


def load_artifact(artifact_path: str | "Path") -> dict | None:  # type: ignore[name-defined]
    """Removed: artifacts are DB-only. Kept as stub for import compatibility."""
    return None



def get_topic_media(
    topic_id: str,
    artifact_path: str | None = None,
    artifact_json_str: str | None = None,
) -> dict:
    """Return available media paths relative to the project root.

    Resolution order:
    1. ``artifact_json_str`` — raw JSON blob from publish_jobs (DB, preferred)
    2. ``artifact_path`` — path to artifact file on disk
    3. filesystem search via ``find_artifact()`` (legacy fallback)
    """
    result: dict[str, Any] = {
        "artifact": None,
        "audio": None,
        "video": None,
        "images": [],
        "scene_images": [],
        "subtitles": {"ass": None, "srt_nl": None, "srt_en": None},
        "shorts": [],
        "platform_status": {"instagram": "pending", "tiktok": "pending", "youtube_shorts": "pending", "facebook": "pending"},
        "checkpoint": None,
    }

    artifact: dict | None = None

    # 1. DB blob (single source of truth when available)
    if artifact_json_str:
        try:
            artifact = json.loads(artifact_json_str)
            result["artifact"] = (
                artifact.get("artifact_path")
                or artifact_path
                or f"db:{topic_id}"
            )
        except Exception:
            artifact = None

    if artifact is None:
        return result

    level_hint = str(artifact.get("level") or "").strip() or None

    def _resolve_media_path(raw_path: str | None) -> str | None:
        """Resolve legacy/relocated artifact paths to an existing project-relative path."""
        if not raw_path:
            return None

        raw = str(raw_path)
        candidates: list[str] = [raw]

        # If legacy absolute paths contain /output/, remap to current workspace-relative output path.
        if "/output/" in raw:
            tail = raw.split("/output/", 1)[1]
            candidates.append(f"output/{tail}")

        # Legacy level paths were often persisted as A1; normalize to current level when known.
        if level_hint:
            normalized: list[str] = []
            for c in candidates:
                normalized.append(c.replace("output/A1/", f"output/{level_hint}/"))
                normalized.append(c.replace("output/A2/", f"output/{level_hint}/"))
                normalized.append(c.replace("/output/A1/", f"/output/{level_hint}/"))
                normalized.append(c.replace("/output/A2/", f"/output/{level_hint}/"))
            candidates.extend(normalized)

        # Common migration path: old artifacts used A1/A2, files now live under A1A2.
        migrated: list[str] = []
        for c in candidates:
            migrated.append(c.replace("output/A1/", "output/A1A2/"))
            migrated.append(c.replace("output/A2/", "output/A1A2/"))
            migrated.append(c.replace("/output/A1/", "/output/A1A2/"))
            migrated.append(c.replace("/output/A2/", "/output/A1A2/"))
        candidates.extend(migrated)

        # Preserve insertion order while de-duping.
        seen: set[str] = set()
        ordered: list[str] = []
        for c in candidates:
            if c not in seen:
                seen.add(c)
                ordered.append(c)

        for c in ordered:
            p = Path(c)
            ap = p if p.is_absolute() else (ROOT / p)
            if ap.exists():
                try:
                    return str(ap.relative_to(ROOT))
                except ValueError:
                    return str(ap)
        return None

    result["artifact"] = result["artifact"] or artifact.get("artifact_path")

    # Audio
    voice = artifact.get("voice_plan", {})
    wav = voice.get("audio_file") or artifact.get("audio_file")
    resolved_audio = _resolve_media_path(wav)
    if resolved_audio:
        result["audio"] = resolved_audio

    # Video — check multiple locations the pipeline may write to
    for vid in (
        artifact.get("video_file"),
        artifact.get("rendered_video"),
        (artifact.get("render") or {}).get("planned_video_file"),
        (artifact.get("storage") or {}).get("archived_video_file"),
    ):
        resolved_video = _resolve_media_path(vid)
        if resolved_video:
            result["video"] = resolved_video
            break

    # Images (flat list for backward compat)
    imgs = artifact.get("all_image_files") or artifact.get("generated_image_files") or []
    if not imgs:
        if artifact.get("primary_image"):
            imgs = [artifact["primary_image"]]
        elif artifact.get("generated_image_file"):
            imgs = [artifact["generated_image_file"]]
    result["images"] = [resolved for p in imgs if (resolved := _resolve_media_path(p))]

    # Scene images — built from script.image_prompts (available post-script)
    import re as _re
    script = artifact.get("script", {}) or {}
    image_prompts = script.get("image_prompts", []) or []
    generated_16x9 = artifact.get("generated_image_files", []) or []
    shorts_imgs = artifact.get("shorts_images", []) or []
    map_16x9: dict[int, str] = {}
    for p in generated_16x9:
        m = _re.search(r"scene(\d+)", Path(p).name, _re.IGNORECASE)
        if m:
            rp = _resolve_media_path(p)
            if rp:
                map_16x9[int(m.group(1))] = rp
    map_9x16: dict[int, str] = {
        si["scene"]: resolved
        for si in shorts_imgs
        if "scene" in si and "image_path" in si and (resolved := _resolve_media_path(si["image_path"]))
    }
    def _output_req_for(prompt: str, ratio: str = "16:9") -> str:
        if "SPLIT-SCREEN" in prompt:
            return (
                f"OUTPUT REQUIREMENT: SPLIT-SCREEN — two side-by-side panels in ONE {ratio} image. "
                "Each panel shows a different character in their own environment. "
                "Do NOT merge them into a single shared scene.\n"
                "ABSOLUTELY NO TEXT, NO WORDS, NO LABELS, NO SIGNS, NO CAPTIONS, "
                "NO WRITING OF ANY KIND anywhere in the generated image. "
                "Any props that would normally have writing must appear blank or decorative only."
            )
        return (
            f"OUTPUT REQUIREMENT: ONE single continuous {ratio} image. "
            "Split into panels only if neccessary, NEVER tile, NEVER repeat, NEVER show the scene twice. One frame only.\n"
            "ABSOLUTELY NO TEXT, NO WORDS, NO LABELS, NO SIGNS, NO CAPTIONS, "
            "NO WRITING OF ANY KIND anywhere in the generated image. "
            "Any props that would normally have writing must appear blank or decorative only."
        )

    scene_cards = []
    for p in image_prompts:
        n = p.get("scene")
        if n is None:
            continue
        p16 = map_16x9.get(n)
        p96 = map_9x16.get(n)
        raw_prompt = p.get("prompt", "")
        description = p.get("description", "")
        trigger = p.get("trigger_sentence", "")

        # Extract structured parts from the raw scene prompt
        env_line = focus_line = emphasis_line = art_style = ""
        for seg in raw_prompt.split(". "):
            s = seg.strip()
            if s.startswith("Environment:"):
                env_line = s + "."
            elif s.startswith("Scene focus:"):
                focus_line = s + "."
            elif s.startswith("Visual emphasis:"):
                emphasis_line = s + "."
        if "Environment:" in raw_prompt:
            art_style = raw_prompt.split("Environment:")[0].strip()

        def _make_prompt(ar: str, common: str, extra: str = "") -> str:
            art = art_style.replace("16:9", ar) if ar != "16:9" else art_style
            parts = []
            if description:
                parts.append(f"SCENE SITUATION: {description}")
            if trigger:
                parts.append(f'The dialogue trigger is: "{trigger}"')
            if env_line:
                parts.append(env_line)
            if focus_line:
                parts.append(focus_line)
            if emphasis_line:
                parts.append(emphasis_line)
            parts.append("")
            parts.append(
                "Reference image 1: the two main characters \u2014 keep faces, hairstyles, "
                "skin tones. "
                "IGNORE the characters\u2019 poses, gestures, and any objects they are holding. "
                "IGNORE any text visible in the reference image."
            )
            parts.append(common)
            if art:
                parts.append(f"Art style: {art}")
            if extra:
                parts.append(extra)
            return "\n".join(parts)

        scene_cards.append({
            "scene": n,
            "description": description,
            "trigger": trigger,
            "prompt": _make_prompt("16:9", _output_req_for(raw_prompt, "16:9")),
            "prompt_9x16": _make_prompt("9:16", _output_req_for(raw_prompt, "9:16"),
                "FULL-BLEED 9:16 PORTRAIT \u2014 every pixel covered. "
                "NO white space, NO blank areas, NO borders. "
                "Place both characters naturally with full bodies visible, facing each other. "
                "Bottom portion must show actual floor/ground \u2014 NOT a flat colour."
            ),
            "image_16x9": p16 if p16 and Path(ROOT / p16).exists() else None,
            "image_9x16": p96 if p96 and Path(ROOT / p96).exists() else None,
        })
    result["scene_images"] = scene_cards

    # For non-dialogue topics (grammar, vocabulary, common_words) image_prompts
    # is empty, so scene_cards will be empty and the UI falls back to the
    # read-only images grid.  Synthesize a single scene card from the primary
    # generated image so the upload button is always available.
    if not scene_cards:
        primary = (
            artifact.get("generated_image_file")
            or (artifact.get("generated_image_files") or [None])[0]
        )
        primary_resolved = _resolve_media_path(primary) if primary else None
        p9x16_raw = (artifact.get("shorts_images") or [{}])[0].get("image_path") if artifact.get("shorts_images") else None
        p9x16_resolved = _resolve_media_path(p9x16_raw) if p9x16_raw else None
        topic_title = (artifact.get("script") or {}).get("topic_title") or artifact.get("title_slug", "")
        result["scene_images"] = [{
            "scene": 1,
            "description": topic_title,
            "trigger": "",
            "prompt": (artifact.get("script") or {}).get("image_prompt", ""),
            "prompt_9x16": "",
            "image_16x9": primary_resolved,
            "image_9x16": p9x16_resolved,
        }]

    # Subtitles — pipeline writes to artifact["subtitles"] with keys:
    #   karaoke_file (ASS), srt_nl (Dutch SRT), srt_en (English SRT)
    # Also check top-level karaoke_file for back-compat.
    sub = artifact.get("subtitles", {}) or artifact.get("subtitle_plan", {}) or {}
    _sub_candidates = [
        ("ass",    sub.get("karaoke_file") or sub.get("ass_file") or artifact.get("karaoke_file")),
        ("srt_nl", sub.get("srt_nl") or sub.get("nl_srt")),
        ("srt_en", sub.get("srt_en")),
    ]
    for key, path in _sub_candidates:
        resolved_sub = _resolve_media_path(path)
        if resolved_sub:
            result["subtitles"][key] = resolved_sub

    # YouTube Shorts
    shorts = artifact.get("shorts", [])
    short_images_by_scene: dict[str, str] = {}
    for si in artifact.get("shorts_images", []) or []:
        key = str(si.get("scene"))
        rp = _resolve_media_path(si.get("image_path"))
        if key and rp:
            short_images_by_scene[key] = rp

    resolved_shorts = []
    for s in shorts:
        rv = _resolve_media_path(s.get("video_file"))
        if not rv:
            continue
        scene_key = str(s.get("scene"))
        short_image = short_images_by_scene.get(scene_key) or _resolve_media_path(s.get("image_path"))
        resolved_shorts.append(
            {
                "scene": s.get("scene"),
                "description": s.get("description"),
                "image_path": short_image,
                "video_file": rv,
                "reel_id": s.get("reel_id"),
                "container_id": s.get("container_id"),
                "permalink": s.get("permalink"),
                "draft": s.get("draft", False),
                "reel_scheduled_at": s.get("reel_scheduled_at"),
                "instagram_scheduled_at": s.get("instagram_scheduled_at"),
                "tiktok_scheduled_at": s.get("tiktok_scheduled_at"),
                "youtube": s.get("youtube"),
                "tiktok": s.get("tiktok"),
                "instagram": s.get("instagram"),
                "facebook": s.get("facebook"),
                "facebook_scheduled_at": s.get("facebook_scheduled_at"),
            }
        )
    result["shorts"] = resolved_shorts

    # Per-platform upload status computed from shorts
    def _platform_status(uploaded_fn) -> str:
        if not shorts:
            return "pending"
        total = len(shorts)
        done = sum(1 for s in shorts if uploaded_fn(s))
        if done == 0:
            return "pending"
        return "done" if done == total else "partial"

    result["platform_status"] = {
        "instagram": _platform_status(
            lambda s: bool(s.get("reel_id") or (s.get("instagram") or {}).get("reel_id"))
        ),
        "tiktok": _platform_status(
            lambda s: bool((s.get("tiktok") or {}).get("publish_id"))
        ),
        "youtube_shorts": _platform_status(
            lambda s: bool((s.get("youtube") or {}).get("short_video_id"))
        ),
        "facebook": _platform_status(
            lambda s: bool((s.get("facebook") or {}).get("post_id"))
        ),
    }

    # Checkpoint
    for cp in ROOT.glob(f"output/**/.checkpoint_{topic_id}.json"):
        result["checkpoint"] = str(cp.relative_to(ROOT))
        break

    return result
