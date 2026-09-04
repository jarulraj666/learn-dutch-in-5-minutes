"""Publish scheduled reels to Instagram, TikTok, and Facebook.

Reels are scheduled manually via the webapp (Episodes → Reels → Set Schedule).
This script uploads any reel whose ``reel_scheduled_at`` is in the past and
has not yet been uploaded to all enabled platforms.

Usage
-----
# Dry-run (default) — show what would be uploaded
python -m pipeline.publish.publish_pending_reels

# Execute real uploads for all due reels
python -m pipeline.publish.publish_pending_reels --execute
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from typing import Any

from pipeline import settings
from pipeline.core.db import get_connection
from pipeline.core import artifact_store as _artifact_store

LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Platform helpers
# ---------------------------------------------------------------------------

def _enabled_platforms() -> list[str]:
    """Return platforms enabled via UPLOAD_* env flags."""
    active = []
    if settings.UPLOAD_INSTAGRAM:
        active.append("instagram")
    if settings.UPLOAD_TIKTOK:
        active.append("tiktok")
    if settings.UPLOAD_FACEBOOK:
        active.append("facebook")
    return active


def _is_reel_due(short: dict) -> bool:
    scheduled = short.get("reel_scheduled_at")
    if not scheduled:
        return False
    try:
        return datetime.fromisoformat(scheduled) <= datetime.now(timezone.utc)
    except ValueError:
        return False


def _is_uploaded_to(short: dict, platform: str) -> bool:
    if platform == "instagram":
        return bool(short.get("instagram", {}).get("reel_id"))
    if platform == "tiktok":
        return bool(short.get("tiktok", {}).get("publish_id"))
    if platform == "facebook":
        return bool(short.get("facebook", {}).get("post_id"))
    return False


def _pending_platforms(short: dict, enabled: list[str]) -> list[str]:
    return [p for p in enabled if not _is_uploaded_to(short, p)]


# ---------------------------------------------------------------------------
# Upload a single reel to all pending platforms
# ---------------------------------------------------------------------------

def _upload_reel(
    topic_id: str,
    artifact: dict,
    artifact_path: Path,
    short: dict,
    short_index: int,
    platforms: list[str],
    dry_run: bool,
) -> dict[str, Any]:
    scene = short.get("scene", short_index)
    results: dict[str, Any] = {"scene": scene, "platforms": {}}

    if dry_run:
        for platform in platforms:
            results["platforms"][platform] = {"dry_run": True}
        return results

    if "instagram" in platforms:
        from pipeline.core.db import (
            claim_instagram_reel_upload,
            complete_instagram_reel_upload,
            release_instagram_reel_upload_claim,
        )
        claimed = claim_instagram_reel_upload(topic_id, scene)
        if not claimed:
            results["platforms"]["instagram"] = {"skipped": "already uploaded or being uploaded"}
        else:
            claim_id, claimed_artifact, claimed_short = claimed
            try:
                from pipeline.stages import stage_upload_short_instagram
                ig_result = stage_upload_short_instagram(claimed_artifact, claimed_short)
                if complete_instagram_reel_upload(topic_id, scene, claim_id, ig_result):
                    artifact["shorts"][short_index]["instagram"] = ig_result
                    results["platforms"]["instagram"] = ig_result
                    LOGGER.info("reels.instagram.ok scene=%d reel_id=%s", scene, ig_result.get("reel_id"))
                else:
                    results["platforms"]["instagram"] = {"skipped": "upload claim was superseded"}
            except Exception as exc:
                release_instagram_reel_upload_claim(topic_id, scene, claim_id)
                LOGGER.warning("reels.instagram.failed scene=%d error=%s", scene, exc)
                results["platforms"]["instagram"] = {"error": str(exc)}

    if "tiktok" in platforms:
        try:
            from pipeline.stages import stage_upload_short_tiktok
            tt_result = stage_upload_short_tiktok(artifact, short)
            artifact["shorts"][short_index]["tiktok"] = tt_result
            results["platforms"]["tiktok"] = tt_result
            LOGGER.info("reels.tiktok.ok scene=%d publish_id=%s", scene, tt_result.get("publish_id"))
        except Exception as exc:
            LOGGER.warning("reels.tiktok.failed scene=%d error=%s", scene, exc)
            results["platforms"]["tiktok"] = {"error": str(exc)}

    if "facebook" in platforms:
        from pipeline.core.db import (
            claim_facebook_reel_upload,
            complete_facebook_reel_upload,
            release_facebook_reel_upload_claim,
        )
        claimed = claim_facebook_reel_upload(topic_id, scene)
        if not claimed:
            results["platforms"]["facebook"] = {"skipped": "already uploaded or being uploaded"}
            return results
        claim_id, claimed_artifact, claimed_short = claimed
        try:
            from pipeline.stages import stage_upload_short_facebook
            fb_result = stage_upload_short_facebook(claimed_artifact, claimed_short)
            if not complete_facebook_reel_upload(topic_id, scene, claim_id, fb_result):
                results["platforms"]["facebook"] = {"skipped": "upload claim was superseded"}
                return results
            artifact["shorts"][short_index]["facebook"] = fb_result
            results["platforms"]["facebook"] = fb_result
            LOGGER.info("reels.facebook.ok scene=%d post_id=%s", scene, fb_result.get("post_id"))
        except Exception as exc:
            release_facebook_reel_upload_claim(topic_id, scene, claim_id)
            LOGGER.warning("reels.facebook.failed scene=%d error=%s", scene, exc)
            results["platforms"]["facebook"] = {"error": str(exc)}

    return results


# ---------------------------------------------------------------------------
# Main processing loop
# ---------------------------------------------------------------------------

def process_pending_reels(
    dry_run: bool = True,
    topic_id: str | None = None,
) -> list[dict[str, Any]]:
    """Find and upload all due reels. Reads/writes artifacts from the DB only."""
    enabled = _enabled_platforms()
    if not enabled and not dry_run:
        LOGGER.warning(
            "reels.no_platforms_enabled — set UPLOAD_INSTAGRAM/UPLOAD_TIKTOK/UPLOAD_FACEBOOK=true in .env"
        )
        return []

    # Load all artifacts with artifact_json from DB
    sql = """
        SELECT t.id AS topic_id, pj.id AS job_id, pj.artifact_json
        FROM topics t
        JOIN canonical_scripts cs ON cs.topic_id = t.id
            AND cs.id = (SELECT MAX(id) FROM canonical_scripts WHERE topic_id = t.id)
        JOIN publish_jobs pj ON pj.canonical_script_id = cs.id
            AND pj.id = (SELECT MAX(id) FROM publish_jobs WHERE canonical_script_id = cs.id)
        WHERE pj.artifact_json IS NOT NULL
    """
    params: list = []
    if topic_id:
        sql += " AND t.id = ?"
        params.append(topic_id)

    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()

    all_results: list[dict[str, Any]] = []

    for row in rows:
        tid = row["topic_id"]
        raw = row["artifact_json"]
        try:
            artifact = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            continue

        shorts: list[dict] = artifact.get("shorts", [])
        if not shorts:
            continue

        artifact_changed = False
        for idx, short in enumerate(shorts):
            if not _is_reel_due(short):
                continue
            pending = _pending_platforms(short, enabled)
            if not pending:
                continue

            LOGGER.info(
                "reels.due topic=%s scene=%d platforms=%s dry_run=%s",
                tid, short.get("scene", idx), pending, dry_run,
            )
            result = _upload_reel(tid, artifact, None, short, idx, pending, dry_run)
            result["topic_id"] = tid
            all_results.append(result)
            artifact_changed = True

        if artifact_changed and not dry_run:
            try:
                _artifact_store.save(tid, artifact)
            except KeyError:
                LOGGER.warning("reels.save_failed topic=%s — no publish_job", tid)

    return all_results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Publish manually-scheduled reels to Instagram, TikTok, and Facebook"
    )
    parser.add_argument("--execute", action="store_true", help="Execute real uploads (default: dry-run)")
    parser.add_argument("--topic-id", metavar="TOPIC_ID", help="Process only a specific topic")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    dry_run = not args.execute
    if dry_run:
        print("ℹ️  DRY RUN — pass --execute to upload for real")

    enabled = _enabled_platforms()
    print(f"Enabled platforms: {enabled or ['(none — set UPLOAD_* flags in .env)']}")
    print()

    results = process_pending_reels(dry_run=dry_run, topic_id=args.topic_id)

    if not results:
        print("✅ No due reels found.")
        return

    for r in results:
        scene = r.get("scene", "?")
        artifact = Path(r.get("artifact", "")).name
        print(f"\nScene {scene} ({artifact}):")
        for platform, outcome in r.get("platforms", {}).items():
            if outcome.get("dry_run"):
                print(f"  {platform}: would upload")
            elif "error" in outcome:
                print(f"  {platform}: ❌ {outcome['error']}")
            else:
                print(f"  {platform}: ✅ {outcome}")

    print(f"\n{'DRY RUN' if dry_run else 'Upload'} complete: {len(results)} reel(s) processed.")


if __name__ == "__main__":
    main()

