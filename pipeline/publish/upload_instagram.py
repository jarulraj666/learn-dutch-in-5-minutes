"""Upload Short clips to Instagram Reels via the Meta Graph API.

Flow for each scene Short
-------------------------
1. (Optional) Upload the MP4 to GCS and generate a short-lived signed URL.
   Instagram requires a *publicly accessible* video URL — direct file uploads
   are not supported by the Graph API.
2. POST ``/{ig_user_id}/media`` to create a *container* (async processing).
3. Poll ``GET /{container_id}?fields=status_code`` until ``FINISHED`` (or fail).
4. POST ``/{ig_user_id}/media_publish`` to publish the container.

Auth
----
Set ``INSTAGRAM_ACCESS_TOKEN`` and ``INSTAGRAM_ACCOUNT_ID`` in ``.env``.

Private / draft mode
--------------------
Set ``INSTAGRAM_UPLOAD_PRIVATE=true`` to upload Reels as drafts (the video is
processed and held in a container but ``media_publish`` is **not** called).
The returned dict will contain ``{"container_id": "...", "draft": true}``
instead of ``reel_id`` / ``permalink``.  You can publish the draft later via
``POST /{ig_user_id}/media_publish?creation_id={container_id}``.
Tokens expire after 60 days; refresh them manually via the Meta token-refresh
endpoint or use a System User token for longer-lived access.

GCS hosting
-----------
If ``GCS_BUCKET`` is set, the module uploads the MP4 to a temporary GCS object
and returns a signed URL (valid ``GCS_SIGNED_URL_EXPIRY_SECONDS``, default 3600).
If ``INSTAGRAM_VIDEO_BASE_URL`` is set instead, it is used as a prefix for the
video filename (useful if you serve output/ via a web server during development).
At least one of the two must be configured for uploads to work.
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path

import requests

LOGGER = logging.getLogger(__name__)

_GRAPH_BASE = "https://graph.facebook.com/v21.0"
_POLL_INTERVAL_SEC = 5
_POLL_TIMEOUT_SEC = 300


# ---------------------------------------------------------------------------
# Metadata builders
# ---------------------------------------------------------------------------

def _build_reel_caption(artifact: dict, scene_short: dict) -> str:
    """Build the Instagram Reel caption (≤2200 chars, hashtags included)."""
    from pipeline.publish.upload_shorts import build_scene_title  # noqa: PLC0415

    title = build_scene_title(artifact, scene_short)
    scene_desc: str = scene_short.get("description", "")
    key_phrases: list[str] = artifact.get("script", {}).get("key_phrases", [])
    level: str = artifact.get("level", "")
    display_level = level.replace("A1A2", "A1-A2").replace("B1B2", "B1-B2")

    lines: list[str] = []
    if title:
        lines.append(title)
    if scene_desc:
        lines.append(scene_desc)
    lines.append("")
    if key_phrases:
        lines.append("🗣 Key Phrases")
        for phrase in key_phrases[:5]:
            lines.append(f"• {phrase}")
        lines.append("")
    tag_level = display_level.replace("-", "").replace(" ", "")
    hashtags = (
        f"#LearnDutch #Dutch #DutchLesson #DutchLanguage "
        f"#Dutch{tag_level} #LearnDutch{tag_level} "
        f"#Reels #LanguageLearning #DutchConversation"
    )
    lines.append(hashtags)

    caption = "\n".join(lines)
    return caption[:2200]


# ---------------------------------------------------------------------------
# GCS / public URL helpers
# ---------------------------------------------------------------------------

def _gcs_signed_url(video_path: Path) -> str:
    """Upload *video_path* to GCS and return a signed URL.

    Supports three credential types (checked in order):
    1. ``GOOGLE_APPLICATION_CREDENTIALS`` env var pointing to a service account JSON.
    2. ``config/gcloud_token.json`` — detected automatically; handles both service
       account keys and user OAuth2 credentials (produced by ``gcloud auth``).
    3. Application Default Credentials (ADC) as a final fallback.

    User OAuth2 credentials cannot sign URLs directly, so the function falls back
    to making the object publicly readable for the duration of the upload window.
    """
    try:
        from google.cloud import storage  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "google-cloud-storage is required for GCS uploads. "
            "Install it with: pip install google-cloud-storage"
        ) from exc

    bucket_name = os.environ["GCS_BUCKET"]
    expiry_sec = int(os.getenv("GCS_SIGNED_URL_EXPIRY_SECONDS", "3600"))
    blob_name = f"instagram_tmp/{video_path.name}"

    # --- Resolve credentials ---
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    if not creds_path:
        default_path = Path(__file__).resolve().parent.parent.parent / "config" / "gcloud_token.json"
        if default_path.exists():
            creds_path = str(default_path)

    credentials = None
    _is_service_account = False

    if creds_path and Path(creds_path).exists():
        import json as _json
        raw = _json.loads(Path(creds_path).read_text(encoding="utf-8"))
        cred_type = raw.get("type", "")

        if cred_type == "service_account":
            from google.oauth2 import service_account as _sa  # type: ignore[import-untyped]
            credentials = _sa.Credentials.from_service_account_file(
                creds_path,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
            _is_service_account = True
        else:
            # User OAuth2 credential (produced by `gcloud auth application-default login`)
            from google.oauth2.credentials import Credentials  # type: ignore[import-untyped]
            from google.auth.transport.requests import Request  # type: ignore[import-untyped]
            credentials = Credentials(
                token=raw.get("token"),
                refresh_token=raw.get("refresh_token"),
                token_uri=raw.get("token_uri", "https://oauth2.googleapis.com/token"),
                client_id=raw.get("client_id"),
                client_secret=raw.get("client_secret"),
                scopes=raw.get("scopes") or ["https://www.googleapis.com/auth/cloud-platform"],
            )
            # Refresh if expired
            if not credentials.valid:
                credentials.refresh(Request())
                # Persist refreshed token back to file
                raw["token"] = credentials.token
                raw["expiry"] = credentials.expiry.isoformat() if credentials.expiry else None
                Path(creds_path).write_text(
                    _json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8"
                )

    client = storage.Client(credentials=credentials) if credentials else storage.Client()

    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_filename(str(video_path), content_type="video/mp4")
    LOGGER.info("gcs.uploaded bucket=%s blob=%s", bucket_name, blob_name)

    import datetime

    if _is_service_account:
        # Service account can sign URLs directly.
        url = blob.generate_signed_url(
            expiration=datetime.timedelta(seconds=expiry_sec),
            method="GET",
            version="v4",
        )
    else:
        # User credentials cannot sign URLs — make the object temporarily public.
        blob.make_public()
        LOGGER.info(
            "gcs.public_url blob=%s (user credentials; object made public for upload)", blob_name
        )
        url = blob.public_url

    return url


def _public_video_url(video_path: Path) -> str:
    """Return a public URL for *video_path*.

    Checks (in order):
    1. ``GCS_BUCKET`` env var → upload to GCS and return a signed URL.
    2. ``INSTAGRAM_VIDEO_BASE_URL`` env var → ``{base_url}/{filename}``.
    3. Raises ``RuntimeError`` if neither is configured.
    """
    gcs_bucket = os.getenv("GCS_BUCKET", "")
    if gcs_bucket:
        return _gcs_signed_url(video_path)

    base_url = os.getenv("INSTAGRAM_VIDEO_BASE_URL", "").rstrip("/")
    if base_url:
        return f"{base_url}/{video_path.name}"

    raise RuntimeError(
        "Cannot derive a public URL for Instagram upload. "
        "Set GCS_BUCKET (for GCS signed URLs) or "
        "INSTAGRAM_VIDEO_BASE_URL (for a static file server) in .env."
    )


# ---------------------------------------------------------------------------
# Graph API helpers
# ---------------------------------------------------------------------------

def _graph_post(path: str, token: str, **params) -> dict:
    url = f"{_GRAPH_BASE}/{path}"
    resp = requests.post(url, params={"access_token": token, **params}, timeout=60)
    data: dict = resp.json()
    if "error" in data:
        raise RuntimeError(f"Instagram API error: {data['error']}")
    return data


def _graph_get(path: str, token: str, **params) -> dict:
    url = f"{_GRAPH_BASE}/{path}"
    resp = requests.get(url, params={"access_token": token, **params}, timeout=30)
    data: dict = resp.json()
    if "error" in data:
        raise RuntimeError(f"Instagram API error: {data['error']}")
    return data


def _poll_container(container_id: str, token: str) -> None:
    """Block until the media container reports ``FINISHED`` processing."""
    deadline = time.time() + _POLL_TIMEOUT_SEC
    while time.time() < deadline:
        result = _graph_get(container_id, token, fields="status_code,status")
        status_code = result.get("status_code", "")
        LOGGER.debug("instagram.poll container=%s status=%s", container_id, status_code)
        if status_code == "FINISHED":
            return
        if status_code == "ERROR":
            raise RuntimeError(
                f"Instagram media container {container_id!r} failed: {result.get('status')}"
            )
        time.sleep(_POLL_INTERVAL_SEC)
    raise TimeoutError(
        f"Instagram media container {container_id!r} did not finish within "
        f"{_POLL_TIMEOUT_SEC}s."
    )


# ---------------------------------------------------------------------------
# Public upload function
# ---------------------------------------------------------------------------

def upload_short_instagram(
    artifact: dict,
    scene_short: dict,
) -> dict:
    """Upload one Short clip to Instagram as a Reel.

    Args:
        artifact:    Full episode artifact dict.
        scene_short: One entry from ``artifact["shorts"]``.

    Returns:
        Dict with ``reel_id`` and ``permalink``.
    """
    access_token = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
    account_id = os.getenv("INSTAGRAM_ACCOUNT_ID", "")
    if not access_token or not account_id:
        raise RuntimeError(
            "INSTAGRAM_ACCESS_TOKEN and INSTAGRAM_ACCOUNT_ID must be set in .env."
        )

    video_file = Path(scene_short.get("video_file", ""))
    if not video_file.is_absolute():
        ROOT = Path(__file__).resolve().parent.parent.parent
        video_file = ROOT / video_file
    if not video_file.exists():
        raise FileNotFoundError(f"Short video not found: {video_file}")

    caption = _build_reel_caption(artifact, scene_short)
    video_url = _public_video_url(video_file)

    LOGGER.info(
        "instagram.upload.start scene=%d video=%s",
        scene_short.get("scene"), video_file,
    )

    private_mode = os.getenv("INSTAGRAM_UPLOAD_PRIVATE", "").lower() in ("1", "true", "yes")

    # Step 1: Create media container
    container_data = _graph_post(
        f"{account_id}/media",
        access_token,
        media_type="REELS",
        video_url=video_url,
        caption=caption,
    )
    container_id: str = container_data.get("id", "")
    if not container_id:
        raise RuntimeError(f"No container ID returned: {container_data}")
    LOGGER.info("instagram.container_created container_id=%s", container_id)

    # Step 2: Wait for processing
    _poll_container(container_id, access_token)

    if private_mode:
        LOGGER.info(
            "instagram.upload.draft scene=%d container_id=%s (INSTAGRAM_UPLOAD_PRIVATE=true)",
            scene_short.get("scene"), container_id,
        )
        return {
            "container_id": container_id,
            "draft": True,
        }

    # Step 3: Publish
    publish_data = _graph_post(
        f"{account_id}/media_publish",
        access_token,
        creation_id=container_id,
    )
    reel_id: str = publish_data.get("id", "")
    LOGGER.info("instagram.upload.done scene=%d reel_id=%s", scene_short.get("scene"), reel_id)

    # Fetch permalink
    permalink = ""
    if reel_id:
        try:
            info = _graph_get(reel_id, access_token, fields="permalink")
            permalink = info.get("permalink", "")
        except Exception as exc:
            LOGGER.warning("instagram.permalink_fetch_failed: %s", exc)

    return {
        "reel_id": reel_id,
        "permalink": permalink,
    }
