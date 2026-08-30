"""Post the promo comment on existing (already-uploaded) YouTube videos.

Usage:
    # Post on specific video IDs (comma-separated):
    python -m pipeline.tools.backfill_promo_comment --video-ids abc123,def456

    # Post on the N most recently uploaded videos on the channel:
    python -m pipeline.tools.backfill_promo_comment --limit 5

    # Post on every video on the channel:
    python -m pipeline.tools.backfill_promo_comment --all

    # Preview without posting:
    python -m pipeline.tools.backfill_promo_comment --limit 5 --dry-run
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
LOGGER = logging.getLogger(__name__)


def _all_video_ids(youtube) -> list[str]:
    channels = youtube.channels().list(part="contentDetails", mine=True).execute()
    items = channels.get("items", [])
    if not items:
        raise RuntimeError("No channel found for the authorised account.")
    uploads_playlist_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

    video_ids: list[str] = []
    request = youtube.playlistItems().list(
        part="contentDetails", playlistId=uploads_playlist_id, maxResults=50
    )
    while request is not None:
        response = request.execute()
        for item in response.get("items", []):
            video_ids.append(item["contentDetails"]["videoId"])
        request = youtube.playlistItems().list_next(request, response)
    return video_ids


def _recent_video_ids(youtube, limit: int) -> list[str]:
    channels = youtube.channels().list(part="contentDetails", mine=True).execute()
    items = channels.get("items", [])
    if not items:
        raise RuntimeError("No channel found for the authorised account.")
    uploads_playlist_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

    video_ids: list[str] = []
    request = youtube.playlistItems().list(
        part="contentDetails", playlistId=uploads_playlist_id, maxResults=min(limit, 50)
    )
    while request is not None and len(video_ids) < limit:
        response = request.execute()
        for item in response.get("items", []):
            video_ids.append(item["contentDetails"]["videoId"])
            if len(video_ids) >= limit:
                break
        request = youtube.playlistItems().list_next(request, response)
    return video_ids


def _already_has_promo_comment(youtube, video_id: str, promo_text: str) -> bool:
    try:
        response = youtube.commentThreads().list(
            part="snippet", videoId=video_id, maxResults=50, textFormat="plainText"
        ).execute()
    except Exception as exc:
        LOGGER.warning("youtube.comment_list_failed video_id=%s error=%s", video_id, exc)
        return False
    for item in response.get("items", []):
        text = item["snippet"]["topLevelComment"]["snippet"].get("textOriginal", "")
        if text.strip() == promo_text.strip():
            return True
    return False


def run(video_ids: list[str], dry_run: bool = False) -> None:
    from pipeline.publish.upload_youtube import PROMO_COMMENT_TEXT, _get_youtube_client, post_promo_comment

    if dry_run:
        for vid in video_ids:
            LOGGER.info("DRY   %-15s  would post promo comment", vid)
        return

    youtube = _get_youtube_client()
    ok = skip = fail = 0

    for vid in video_ids:
        if _already_has_promo_comment(youtube, vid, PROMO_COMMENT_TEXT):
            LOGGER.info("SKIP  %-15s  promo comment already present", vid)
            skip += 1
            continue
        comment_id = post_promo_comment(youtube, vid)
        if comment_id:
            LOGGER.info("OK    %-15s  comment_id=%s", vid, comment_id)
            ok += 1
        else:
            LOGGER.warning("FAIL  %-15s  see log above for error", vid)
            fail += 1

    LOGGER.info("Done. posted=%d  skipped=%d  failed=%d", ok, skip, fail)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--video-ids", help="Comma-separated list of YouTube video IDs")
    parser.add_argument("--limit", type=int, help="Post on the N most recently uploaded videos")
    parser.add_argument("--all", action="store_true", help="Post on every video on the channel")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without posting")
    args = parser.parse_args()

    if args.video_ids:
        video_ids = [v.strip() for v in args.video_ids.split(",") if v.strip()]
    elif args.all:
        from pipeline.publish.upload_youtube import _get_youtube_client
        youtube = _get_youtube_client()
        video_ids = _all_video_ids(youtube)
    elif args.limit:
        from pipeline.publish.upload_youtube import _get_youtube_client
        youtube = _get_youtube_client()
        video_ids = _recent_video_ids(youtube, args.limit)
    else:
        parser.error("Provide either --video-ids, --limit, or --all")
        return

    run(video_ids, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
