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
            result["artifact"] = artifact.get("artifact_path") or artifact_path
        except Exception:
            artifact = None

    # 2. Fall back to file path
    if artifact is None and artifact_path:
        artifact = load_artifact(artifact_path)
        if artifact:
            result["artifact"] = artifact_path

    # 3. Legacy filesystem search
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

        # Video — check multiple locations the pipeline may write to
        for vid in (
            artifact.get("video_file"),
            artifact.get("rendered_video"),
            (artifact.get("render") or {}).get("planned_video_file"),
            (artifact.get("storage") or {}).get("archived_video_file"),
        ):
            if vid and Path(ROOT / vid).exists():
                result["video"] = vid
                break

        # Images (flat list for backward compat)
        imgs = artifact.get("all_image_files") or []
        if not imgs and artifact.get("primary_image"):
            imgs = [artifact["primary_image"]]
        result["images"] = [p for p in imgs if Path(ROOT / p).exists()]

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
                map_16x9[int(m.group(1))] = p
        map_9x16: dict[int, str] = {
            si["scene"]: si["image_path"]
            for si in shorts_imgs
            if "scene" in si and "image_path" in si
        }
        _COMMON_16 = (
            "OUTPUT REQUIREMENT: ONE single continuous 16:9 image. "
            "NEVER split into panels, NEVER tile, NEVER repeat, NEVER show the scene twice. One frame only.\n"
            "ABSOLUTELY NO TEXT, NO WORDS, NO LABELS, NO SIGNS, NO CAPTIONS, "
            "NO WRITING OF ANY KIND anywhere in the generated image. "
            "Any props that would normally have writing must appear blank or decorative only."
        )
        _COMMON_9 = _COMMON_16.replace("16:9 image", "9:16 portrait image")

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
                "prompt": _make_prompt("16:9", _COMMON_16),
                "prompt_9x16": _make_prompt("9:16", _COMMON_9,
                    "FULL-BLEED 9:16 PORTRAIT \u2014 every pixel covered. "
                    "NO white space, NO blank areas, NO borders. "
                    "Place both characters naturally with full bodies visible, facing each other. "
                    "Bottom portion must show actual floor/ground \u2014 NOT a flat colour."
                ),
                "image_16x9": p16 if p16 and Path(ROOT / p16).exists() else None,
                "image_9x16": p96 if p96 and Path(ROOT / p96).exists() else None,
            })
        result["scene_images"] = scene_cards

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
                "instagram_scheduled_at": s.get("instagram_scheduled_at"),
                "youtube": s.get("youtube"),
                "tiktok": s.get("tiktok"),
                "instagram": s.get("instagram"),
                "facebook": s.get("facebook"),
                "facebook_scheduled_at": s.get("facebook_scheduled_at"),
            }
            for s in shorts
            if s.get("video_file") and Path(ROOT / s["video_file"]).exists()
        ]

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
