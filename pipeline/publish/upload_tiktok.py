"""Upload Short clips to TikTok via the Content Posting API v2.

Flow for each scene Short
-------------------------
Direct Post flow (video file uploaded directly — no public URL needed):

1. ``POST /v2/post/publish/video/init/``  — initialise the upload, get
   ``publish_id`` and an ``upload_url``.
2. ``PUT {upload_url}``                   — upload the raw MP4 bytes in a single
   chunk (files up to 4 GB are supported; chunked multi-part upload is used
   automatically for files > 64 MB).
3. ``GET /v2/post/publish/status/fetch/`` — poll until ``status`` is
   ``PUBLISH_COMPLETE`` (or a terminal error state).

Auth
----
Set the following in ``.env``:

    TIKTOK_CLIENT_KEY=...
    TIKTOK_CLIENT_SECRET=...
    TIKTOK_ACCESS_TOKEN=...      # user OAuth2 access token
    TIKTOK_REFRESH_TOKEN=...     # used to auto-refresh the access token

Tokens are persisted to ``output/tiktok_token.json`` and refreshed
automatically when a 401 / expired-token error is detected.
"""
from __future__ import annotations

import json
import logging
import math
import os
import time
from pathlib import Path

import requests

LOGGER = logging.getLogger(__name__)

_API_BASE = "https://open.tiktokapis.com/v2"
_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
_TOKEN_FILE = Path(os.getenv("OUTPUT_DIR", "output")) / "tiktok_token.json"

_CHUNK_SIZE = 64 * 1024 * 1024  # 64 MB — chunk threshold / size
_POLL_INTERVAL_SEC = 5
_POLL_TIMEOUT_SEC = 300


# ---------------------------------------------------------------------------
# Token management
# ---------------------------------------------------------------------------

def _load_token_file() -> dict:
    if _TOKEN_FILE.exists():
        try:
            return json.loads(_TOKEN_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_token_file(data: dict) -> None:
    _TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    _TOKEN_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _refresh_access_token(client_key: str, client_secret: str, refresh_token: str) -> dict:
    resp = requests.post(
        _TOKEN_URL,
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data: dict = resp.json()
    if data.get("error"):
        raise RuntimeError(f"TikTok token refresh failed: {data}")
    return data


def _get_access_token() -> str:
    """Return a valid TikTok access token, refreshing via the refresh token if needed."""
    client_key = os.getenv("TIKTOK_CLIENT_KEY", "")
    client_secret = os.getenv("TIKTOK_CLIENT_SECRET", "")

    # Prefer token file over raw env vars (token file is refreshed in-place).
    stored = _load_token_file()
    access_token: str = stored.get("access_token") or os.getenv("TIKTOK_ACCESS_TOKEN", "")
    refresh_token: str = stored.get("refresh_token") or os.getenv("TIKTOK_REFRESH_TOKEN", "")
    expires_at: float = stored.get("expires_at", 0.0)

    if not access_token:
        raise RuntimeError(
            "TIKTOK_ACCESS_TOKEN is not set. Complete the OAuth2 flow first and "
            "add the token to .env or output/tiktok_token.json."
        )

    # Proactively refresh if within 5 minutes of expiry.
    if expires_at and time.time() > expires_at - 300:
        if not refresh_token or not client_key or not client_secret:
            LOGGER.warning(
                "tiktok.token_expiring but no refresh credentials available — proceeding anyway"
            )
        else:
            LOGGER.info("tiktok.token_refreshing")
            token_data = _refresh_access_token(client_key, client_secret, refresh_token)
            access_token = token_data.get("access_token", access_token)
            refresh_token = token_data.get("refresh_token", refresh_token)
            expires_in = int(token_data.get("expires_in", 86400))
            _save_token_file({
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_at": time.time() + expires_in,
            })
            LOGGER.info("tiktok.token_refreshed")

    return access_token


# ---------------------------------------------------------------------------
# Metadata builder
# ---------------------------------------------------------------------------

def _build_tiktok_caption(artifact: dict, scene_short: dict) -> str:
    """Build a TikTok caption (≤2200 chars including hashtags)."""
    from pipeline.publish.upload_shorts import build_scene_title  # noqa: PLC0415

    title = build_scene_title(artifact, scene_short)
    scene_desc: str = scene_short.get("description", "")
    level: str = artifact.get("level", "")
    display_level = level.replace("A1A2", "A1-A2").replace("B1B2", "B1-B2")
    tag_level = display_level.replace("-", "").replace(" ", "")

    parts: list[str] = []
    if title:
        parts.append(title)
    if scene_desc:
        parts.append(scene_desc)
    parts.append(
        f"#LearnDutch #Dutch #DutchLesson #Dutch{tag_level} "
        f"#LearnDutch{tag_level} #LanguageLearning #DutchConversation"
    )
    caption = "\n".join(parts)
    return caption[:2200]


# ---------------------------------------------------------------------------
# Upload helpers
# ---------------------------------------------------------------------------

def _init_upload(access_token: str, video_path: Path, caption: str) -> tuple[str, str]:
    """Initialise a TikTok Direct Post upload.

    Returns:
        (publish_id, upload_url)
    """
    file_size = video_path.stat().st_size
    chunk_size = _CHUNK_SIZE
    total_chunk_count = max(1, math.ceil(file_size / chunk_size))

    resp = requests.post(
        f"{_API_BASE}/post/publish/video/init/",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        json={
            "post_info": {
                "title": caption,
                "privacy_level": "SELF_ONLY",  # start private; change to PUBLIC_TO_EVERYONE when ready
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
                "video_cover_timestamp_ms": 1000,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": file_size,
                "chunk_size": chunk_size,
                "total_chunk_count": total_chunk_count,
            },
        },
        timeout=30,
    )
    resp.raise_for_status()
    data: dict = resp.json()
    if data.get("error", {}).get("code", "ok") != "ok":
        raise RuntimeError(f"TikTok init failed: {data['error']}")
    publish_id: str = data["data"]["publish_id"]
    upload_url: str = data["data"]["upload_url"]
    LOGGER.info("tiktok.init publish_id=%s total_chunks=%d", publish_id, total_chunk_count)
    return publish_id, upload_url


def _upload_chunks(upload_url: str, video_path: Path) -> None:
    """Upload video bytes to the TikTok upload URL in chunks."""
    file_size = video_path.stat().st_size
    with video_path.open("rb") as fh:
        offset = 0
        chunk_index = 0
        while offset < file_size:
            chunk = fh.read(_CHUNK_SIZE)
            if not chunk:
                break
            end = offset + len(chunk) - 1
            resp = requests.put(
                upload_url,
                headers={
                    "Content-Type": "video/mp4",
                    "Content-Range": f"bytes {offset}-{end}/{file_size}",
                    "Content-Length": str(len(chunk)),
                },
                data=chunk,
                timeout=120,
            )
            # TikTok returns 206 for partial content and 200 for the final chunk.
            if resp.status_code not in (200, 206):
                raise RuntimeError(
                    f"TikTok chunk upload failed at chunk {chunk_index}: "
                    f"{resp.status_code} {resp.text[:200]}"
                )
            LOGGER.debug(
                "tiktok.chunk_uploaded index=%d offset=%d/%d",
                chunk_index, end + 1, file_size,
            )
            offset += len(chunk)
            chunk_index += 1


def _poll_publish_status(publish_id: str, access_token: str) -> str:
    """Poll until the publish job completes.

    Returns:
        The final ``publish_id`` (same as input, returned for symmetry).
    """
    deadline = time.time() + _POLL_TIMEOUT_SEC
    while time.time() < deadline:
        resp = requests.post(
            f"{_API_BASE}/post/publish/status/fetch/",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
            },
            json={"publish_id": publish_id},
            timeout=30,
        )
        resp.raise_for_status()
        data: dict = resp.json()
        process_status: str = data.get("data", {}).get("status", "")
        LOGGER.debug("tiktok.poll publish_id=%s status=%s", publish_id, process_status)

        if process_status == "PUBLISH_COMPLETE":
            return publish_id
        if process_status in ("FAILED", "SPAM_RISK_TOO_MANY_POSTS", "SPAM_RISK_USER_BANNED_FROM_POSTING"):
            raise RuntimeError(
                f"TikTok publish failed for {publish_id!r}: status={process_status}"
            )
        time.sleep(_POLL_INTERVAL_SEC)

    raise TimeoutError(
        f"TikTok publish job {publish_id!r} did not complete within {_POLL_TIMEOUT_SEC}s."
    )


# ---------------------------------------------------------------------------
# Public upload function
# ---------------------------------------------------------------------------

def upload_short_tiktok(
    artifact: dict,
    scene_short: dict,
) -> dict:
    """Upload one Short clip to TikTok.

    Args:
        artifact:    Full episode artifact dict.
        scene_short: One entry from ``artifact["shorts"]``.

    Returns:
        Dict with ``publish_id``.
    """
    access_token = _get_access_token()

    video_file = Path(scene_short.get("video_file", ""))
    if not video_file.is_absolute():
        ROOT = Path(__file__).resolve().parent.parent.parent
        video_file = ROOT / video_file
    if not video_file.exists():
        raise FileNotFoundError(f"Short video not found: {video_file}")

    caption = _build_tiktok_caption(artifact, scene_short)

    LOGGER.info(
        "tiktok.upload.start scene=%d video=%s",
        scene_short.get("scene"), video_file,
    )

    publish_id, upload_url = _init_upload(access_token, video_file, caption)
    _upload_chunks(upload_url, video_file)
    _poll_publish_status(publish_id, access_token)

    LOGGER.info("tiktok.upload.done scene=%d publish_id=%s", scene_short.get("scene"), publish_id)
    return {"publish_id": publish_id}
