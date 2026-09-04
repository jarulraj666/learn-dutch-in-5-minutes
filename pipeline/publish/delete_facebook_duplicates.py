"""Delete duplicate Facebook Page Reels while retaining the oldest copy.

Duplicates are defined as reels with identical title and description. Run this
command again after a Meta rate-limit response; it re-reads the current Page
inventory and never deletes the oldest reel in an exact-match group.
"""
from __future__ import annotations

import collections
import os

import requests

from pipeline import settings  # noqa: F401 - loads the project .env

_GRAPH_BASE = "https://graph.facebook.com/v21.0"


def _list_reels(page_id: str, token: str) -> list[dict]:
    url = f"{_GRAPH_BASE}/{page_id}/video_reels"
    params: dict | None = {
        "access_token": token,
        "fields": "id,title,description,created_time",
        "limit": 100,
    }
    reels: list[dict] = []
    while url:
        response = requests.get(url, params=params, timeout=60)
        response.raise_for_status()
        payload = response.json()
        reels.extend(payload.get("data", []))
        url = payload.get("paging", {}).get("next")
        params = None
    return reels


def delete_duplicate_reels() -> tuple[int, int, bool]:
    """Delete newer exact duplicates. Returns deleted, remaining, rate_limited."""
    page_id = os.getenv("FACEBOOK_PAGE_ID", "")
    token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN", "")
    if not page_id or not token:
        raise RuntimeError("FACEBOOK_PAGE_ID and FACEBOOK_PAGE_ACCESS_TOKEN must be set.")

    groups: dict[tuple[str, str], list[dict]] = collections.defaultdict(list)
    for reel in _list_reels(page_id, token):
        groups[(reel.get("title") or "", reel.get("description") or "")].append(reel)

    duplicates: list[dict] = []
    for reels in groups.values():
        reels.sort(key=lambda reel: reel.get("created_time", ""))
        duplicates.extend(reels[1:])

    deleted = 0
    for reel in duplicates:
        response = requests.delete(
            f"{_GRAPH_BASE}/{reel['id']}", params={"access_token": token}, timeout=60
        )
        payload = response.json()
        if response.ok and payload.get("success"):
            deleted += 1
            continue
        error = payload.get("error", {})
        if error.get("code") == 4:
            return deleted, len(duplicates) - deleted, True
        raise RuntimeError(f"Could not delete Facebook Reel {reel['id']}: {payload}")

    return deleted, 0, False


def main() -> None:
    deleted, remaining, rate_limited = delete_duplicate_reels()
    print(f"Deleted {deleted} duplicate Facebook Reel(s).")
    if rate_limited:
        print(f"Meta rate limited the cleanup; {remaining} duplicate Reel(s) remain. Run this command again later.")
    else:
        print("No duplicate Facebook Reels remain.")


if __name__ == "__main__":
    main()