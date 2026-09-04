"""Find (and optionally delete) duplicate Instagram Reels, retaining the oldest copy.

Duplicates are reels with an identical caption. The Instagram Graph API does not
officially expose a media-delete endpoint, so ``--delete`` attempts ``DELETE
/{media_id}`` and reports permalinks for anything Meta refuses to remove.

Usage:
    python -m pipeline.publish.delete_instagram_duplicates            # list only
    python -m pipeline.publish.delete_instagram_duplicates --delete   # attempt deletion
"""
from __future__ import annotations

import argparse
import collections
import os

import requests

from pipeline import settings  # noqa: F401 - loads the project .env

_GRAPH_BASE = "https://graph.facebook.com/v21.0"


def _list_media(account_id: str, token: str) -> list[dict]:
    url: str | None = f"{_GRAPH_BASE}/{account_id}/media"
    params: dict | None = {
        "access_token": token,
        "fields": "id,caption,permalink,timestamp,media_product_type",
        "limit": 100,
    }
    media: list[dict] = []
    while url:
        response = requests.get(url, params=params, timeout=60)
        response.raise_for_status()
        payload = response.json()
        media.extend(payload.get("data", []))
        url = payload.get("paging", {}).get("next")
        params = None
    return media


def find_duplicates(account_id: str, token: str) -> list[dict]:
    """Return the newer copies of every identical-caption group."""
    groups: dict[str, list[dict]] = collections.defaultdict(list)
    for item in _list_media(account_id, token):
        caption = (item.get("caption") or "").strip()
        if caption:
            groups[caption].append(item)

    duplicates: list[dict] = []
    for items in groups.values():
        if len(items) < 2:
            continue
        items.sort(key=lambda item: item.get("timestamp", ""))
        duplicates.extend(items[1:])
    return duplicates


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delete", action="store_true", help="Actually delete the duplicates.")
    args = parser.parse_args()

    account_id = os.getenv("INSTAGRAM_ACCOUNT_ID", "")
    token = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
    if not account_id or not token:
        raise RuntimeError("INSTAGRAM_ACCOUNT_ID and INSTAGRAM_ACCESS_TOKEN must be set.")

    duplicates = find_duplicates(account_id, token)
    if not duplicates:
        print("No duplicate Instagram Reels found.")
        return

    print(f"Found {len(duplicates)} duplicate Reel(s) (oldest copy of each caption is kept):")
    for item in duplicates:
        first_line = (item.get("caption") or "").splitlines()[0][:70]
        print(f"  {item['id']}  {item.get('timestamp', '')}  {item.get('permalink', '')}  {first_line}")

    if not args.delete:
        print("\nDry run. Re-run with --delete to remove them.")
        return

    deleted, failed = 0, []
    for item in duplicates:
        response = requests.delete(
            f"{_GRAPH_BASE}/{item['id']}", params={"access_token": token}, timeout=60
        )
        payload = response.json() if response.content else {}
        if response.ok and payload.get("success"):
            deleted += 1
        else:
            failed.append((item, payload.get("error", payload)))

    print(f"\nDeleted {deleted} duplicate Reel(s).")
    if failed:
        print(f"{len(failed)} could not be deleted via the API — remove these manually in the app:")
        for item, error in failed:
            print(f"  {item.get('permalink', item['id'])}  ({error})")


if __name__ == "__main__":
    main()
