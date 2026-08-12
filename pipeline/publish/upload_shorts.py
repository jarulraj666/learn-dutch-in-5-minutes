"""Upload YouTube Shorts generated from episode scenes.

Each Short is uploaded as a separate private video with:
- Title derived from the scene description (≤100 chars, ending with #Shorts).
- Description linking back to the full episode via ``full_video_id``.
- Scene image used as thumbnail.
- Added to a per-level dedicated Shorts playlist.

Auth and playlist helpers are reused from ``upload_youtube``.
"""
from __future__ import annotations

import logging
from pathlib import Path

LOGGER = logging.getLogger(__name__)

_SUFFIX = " #Shorts"


# ---------------------------------------------------------------------------
# Metadata builders
# ---------------------------------------------------------------------------

def _shorts_playlist_name(level: str) -> str:
    """Return the dedicated Shorts playlist name for *level*.

    E.g. ``"A1A2"`` → ``"A1-A2 | Dutch Shorts"``
    """
    display = level.replace("A1A2", "A1-A2").replace("B1B2", "B1-B2")
    return f"{display} | Dutch Shorts"


def _build_short_title(artifact: dict, scene_short: dict) -> str:
    """Build a YouTube Short title (≤100 chars, ends with ``#Shorts``)."""
    topic_title_en: str = artifact.get("script", {}).get("topic_title_en", "")
    scene_n: int = scene_short.get("scene", 1)
    level: str = artifact.get("level", "")
    display_level = level.replace("A1A2", "A1-A2").replace("B1B2", "B1-B2")

    base = f"{topic_title_en} (Scene {scene_n}) | Dutch {display_level}"
    full = base + _SUFFIX
    if len(full) <= 100:
        return full
    # Truncate base to fit
    max_base = 100 - len(_SUFFIX)
    return base[:max_base].rstrip() + _SUFFIX


def _build_short_description(
    artifact: dict,
    scene_short: dict,
    full_video_id: str,
) -> str:
    """Build the Short description with a full-episode back-link."""
    from pipeline.publish.upload_youtube import _sanitize_description  # noqa: PLC0415

    scene_desc: str = scene_short.get("description", "")
    key_phrases: list[str] = artifact.get("script", {}).get("key_phrases", [])
    level: str = artifact.get("level", "")
    display_level = level.replace("A1A2", "A1-A2").replace("B1B2", "B1-B2")

    lines: list[str] = []
    if scene_desc:
        lines.append(scene_desc)
        lines.append("")
    lines.append(f"📺 Full episode: https://youtu.be/{full_video_id}")
    lines.append("")
    if key_phrases:
        lines.append("🗣 Key Phrases")
        for phrase in key_phrases[:5]:
            lines.append(f"• {phrase}")
        lines.append("")
    hashtags = (
        f"#LearnDutch #Dutch #DutchShorts #Shorts "
        f"#Dialogue #Conversation #DutchConversation "
        f"#DutchIn5Minutes #Dutch{display_level.replace('-', '').replace(' ', '')} "
        f"#LearnDutch{display_level.replace('-', '').replace(' ', '')}"
    )
    lines.append(hashtags)

    return _sanitize_description("\n".join(lines))


def _episode_tags(artifact: dict) -> list[str]:
    base_tags: list[str] = list(artifact.get("metadata", {}).get("tags") or [])
    short_tags = ["Shorts", "Dutch Shorts", "Learn Dutch Short", "Dialogue", "Dutch", "Conversation", "Dutch Conversation"]
    seen: set[str] = set()
    result: list[str] = []
    for t in base_tags + short_tags:
        if t.lower() not in seen:
            seen.add(t.lower())
            result.append(t)
    return result[:500]  # YouTube tag list limit


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

def upload_short(
    artifact: dict,
    artifact_path: Path,
    scene_short: dict,
    full_video_id: str,
) -> dict:
    """Upload one Short clip to YouTube.

    Args:
        artifact:       Full episode artifact dict.
        artifact_path:  Path to the artifact JSON (used to resolve thumbnail path).
        scene_short:    One entry from ``artifact["shorts"]`` (scene clip dict).
        full_video_id:  YouTube video ID of the already-uploaded full episode.

    Returns:
        Dict with ``short_video_id``, ``playlist_id``, ``thumbnail_uploaded``.
    """
    from pipeline.publish.upload_youtube import (  # noqa: PLC0415
        _get_youtube_client,
        _load_google_clients,
        add_video_to_playlist,
        ensure_playlist,
    )

    _, _, _, MediaFileUpload, _ = _load_google_clients()
    youtube = _get_youtube_client()

    title = _build_short_title(artifact, scene_short)
    description = _build_short_description(artifact, scene_short, full_video_id)
    tags = _episode_tags(artifact)

    scheduled_at = artifact.get("scheduled_at")
    status: dict = {"privacyStatus": "private", "selfDeclaredMadeForKids": False}
    if scheduled_at:
        status["publishAt"] = scheduled_at

    video_file = Path(scene_short.get("video_file", ""))
    if not video_file.exists():
        raise FileNotFoundError(f"Short video not found: {video_file}")

    LOGGER.info(
        "upload_short.start scene=%d title=%r video=%s",
        scene_short.get("scene"), title, video_file,
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": "27",
                "defaultLanguage": "nl",
                "defaultAudioLanguage": "nl",
            },
            "status": status,
        },
        media_body=MediaFileUpload(str(video_file), mimetype="video/mp4", chunksize=-1, resumable=True),
    )
    response = request.execute()
    short_video_id: str = response.get("id", "")
    LOGGER.info("upload_short.uploaded short_video_id=%s", short_video_id)

    # Add to dedicated Shorts playlist
    level = artifact.get("level", "")
    playlist_name = _shorts_playlist_name(level)
    playlist_id: str | None = None
    if short_video_id:
        try:
            playlist_id = ensure_playlist(youtube, playlist_name, "Dutch language learning Short clips")
            add_video_to_playlist(youtube, playlist_id, short_video_id)
            LOGGER.info("upload_short.playlist short_video_id=%s playlist=%s", short_video_id, playlist_name)
        except Exception as exc:
            LOGGER.warning("upload_short.playlist_failed: %s", exc)

    # Upload scene image as thumbnail
    thumbnail_uploaded = False
    if short_video_id:
        thumb_str = scene_short.get("image_path", "")
        if thumb_str:
            workspace = artifact_path.parent.parent.parent.parent
            thumb_path = Path(thumb_str)
            if not thumb_path.is_absolute():
                thumb_path = (workspace / thumb_path).resolve()
            if thumb_path.exists():
                try:
                    youtube.thumbnails().set(
                        videoId=short_video_id,
                        media_body=MediaFileUpload(str(thumb_path), mimetype="image/png"),
                    ).execute()
                    thumbnail_uploaded = True
                    LOGGER.info("upload_short.thumbnail_uploaded short_video_id=%s", short_video_id)
                except Exception as exc:
                    LOGGER.warning("upload_short.thumbnail_failed: %s", exc)

    return {
        "short_video_id": short_video_id,
        "playlist_id": playlist_id,
        "playlist_name": playlist_name,
        "thumbnail_uploaded": thumbnail_uploaded,
    }
