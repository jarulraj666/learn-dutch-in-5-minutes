"""Upload Short clips to Facebook Pages as Reels via the Meta Graph API.

Flow for each scene Short
-------------------------
Unlike Instagram, Facebook Reels supports **direct file upload** — no public
URL or GCS bucket is required.

1. POST ``/{page_id}/video_reels`` with ``upload_phase=start`` and
   ``video_size`` → returns ``{video_id, upload_url}``.
2. POST the raw MP4 bytes to ``upload_url`` with the correct Authorization
   and byte-range headers.
3. POST ``/{page_id}/video_reels`` with ``upload_phase=finish``,
   ``video_state=PUBLISHED``, ``video_id``, ``title``, ``description``
   → returns ``{success, post_id}``.

Auth / Setup
------------
You need a **Facebook Page Access Token** (not a User token) with:
  - ``pages_manage_posts``
  - ``pages_read_engagement``

How to get one (one-time setup):
1. Go to https://developers.facebook.com and create an App (Business type).
2. Add the "Facebook Login for Business" product.
3. In Graph API Explorer, select your App and your Page, then generate a
   token with the above permissions.
4. Exchange for a long-lived token:
   GET /oauth/access_token?grant_type=fb_exchange_token&
       client_id={app_id}&client_secret={app_secret}&
       fb_exchange_token={short_lived_token}
5. Set FACEBOOK_PAGE_ID and FACEBOOK_PAGE_ACCESS_TOKEN in .env.

Tokens expire after 60 days. Use a System User token from Business Manager
for non-expiring access.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import requests

LOGGER = logging.getLogger(__name__)

_GRAPH_BASE = "https://graph.facebook.com/v21.0"


# ---------------------------------------------------------------------------
# Caption builder
# ---------------------------------------------------------------------------

def _build_reel_description(artifact: dict, scene_short: dict) -> str:
    """Build a Facebook Reel description (≤ 2200 chars)."""
    topic_title_en: str = artifact.get("script", {}).get("topic_title_en", "")
    scene_desc: str = scene_short.get("description", "")
    key_phrases: list[str] = artifact.get("script", {}).get("key_phrases", [])
    level: str = artifact.get("level", "A1A2")
    display_level = level.replace("A1A2", "A1-A2").replace("B1B2", "B1-B2")
    tag_level = display_level.replace("-", "").replace(" ", "")

    lines: list[str] = []
    if topic_title_en:
        lines.append(topic_title_en)
    if scene_desc:
        lines.append(scene_desc)
    lines.append("")
    if key_phrases:
        lines.append("🗣 Key Phrases")
        for phrase in key_phrases[:5]:
            lines.append(f"• {phrase}")
        lines.append("")
    lines.append(
        f"#LearnDutch #Dutch #DutchLesson #DutchLanguage "
        f"#Dutch{tag_level} #LearnDutch{tag_level} "
        f"#Reels #LanguageLearning #DutchConversation"
    )
    return "\n".join(lines)[:2200]


# ---------------------------------------------------------------------------
# Graph API helpers
# ---------------------------------------------------------------------------

def _graph_post(path: str, token: str, **params) -> dict:
    url = f"{_GRAPH_BASE}/{path}"
    resp = requests.post(url, params={"access_token": token, **params}, timeout=60)
    data: dict = resp.json()
    if "error" in data:
        raise RuntimeError(f"Facebook API error: {data['error']}")
    return data


# ---------------------------------------------------------------------------
# Public upload function
# ---------------------------------------------------------------------------

def upload_short_facebook(
    artifact: dict,
    scene_short: dict,
) -> dict:
    """Upload one Short clip to a Facebook Page as a Reel.

    Args:
        artifact:    Full episode artifact dict.
        scene_short: One scene entry from ``artifact["shorts"]``.

    Returns:
        Dict with ``post_id`` and ``video_id``.
    """
    page_id = os.getenv("FACEBOOK_PAGE_ID", "")
    page_token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN", "")
    if not page_id or not page_token:
        raise RuntimeError(
            "FACEBOOK_PAGE_ID and FACEBOOK_PAGE_ACCESS_TOKEN must be set in .env."
        )

    video_file = Path(scene_short.get("video_file", ""))
    if not video_file.is_absolute():
        ROOT = Path(__file__).resolve().parent.parent.parent
        video_file = ROOT / video_file
    if not video_file.exists():
        raise FileNotFoundError(f"Short video not found: {video_file}")

    video_bytes = video_file.read_bytes()
    video_size = len(video_bytes)
    title = artifact.get("script", {}).get("topic_title_en", artifact.get("title_slug", ""))
    description = _build_reel_description(artifact, scene_short)

    LOGGER.info(
        "facebook.upload.start scene=%s page=%s video=%s size=%d bytes",
        scene_short.get("scene"), page_id, video_file.name, video_size,
    )

    # Step 1 — initialise upload session
    init_data = _graph_post(
        f"{page_id}/video_reels",
        page_token,
        upload_phase="start",
        video_size=video_size,
    )
    video_id: str = init_data["video_id"]
    upload_url: str = init_data["upload_url"]
    LOGGER.info("facebook.upload.session video_id=%s", video_id)

    # Step 2 — upload raw bytes
    upload_resp = requests.post(
        upload_url,
        headers={
            "Authorization": f"OAuth {page_token}",
            "offset": "0",
            "file_size": str(video_size),
            "Content-Type": "video/mp4",
        },
        data=video_bytes,
        timeout=300,
    )
    if not upload_resp.ok:
        raise RuntimeError(
            f"Facebook video upload failed: {upload_resp.status_code} {upload_resp.text[:500]}"
        )
    LOGGER.info("facebook.upload.bytes_sent video_id=%s status=%s", video_id, upload_resp.status_code)

    # Step 3 — finish and publish
    finish_data = _graph_post(
        f"{page_id}/video_reels",
        page_token,
        upload_phase="finish",
        video_state="PUBLISHED",
        video_id=video_id,
        title=title[:100],
        description=description,
    )
    post_id: str = finish_data.get("post_id", "")
    LOGGER.info(
        "facebook.upload.done scene=%s video_id=%s post_id=%s",
        scene_short.get("scene"), video_id, post_id,
    )

    promo_comment_id = _post_promo_comment(post_id, page_token) if post_id else None

    return {"video_id": video_id, "post_id": post_id, "promo_comment_id": promo_comment_id}
