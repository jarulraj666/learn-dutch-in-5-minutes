from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from pipeline import settings  # ensures .env is loaded


SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",  # required for captions API
]


def _sanitize_description(text: str) -> str:
    """Sanitize description for YouTube: remove angle brackets, null bytes, truncate to 5000 chars."""
    text = text.replace("\x00", "")
    text = text.replace("<", "").replace(">", "")
    text = text.strip()
    return text[:5000]


def build_upload_payload(artifact_path: Path) -> dict:
    data = json.loads(artifact_path.read_text(encoding="utf-8"))
    metadata = data.get("metadata", {})

    status = {
        "privacyStatus": "private",
        "selfDeclaredMadeForKids": False,
    }
    scheduled_at = data.get("scheduled_at")
    if scheduled_at:
        status["publishAt"] = scheduled_at

    return {
        "snippet": {
            "title": metadata.get("title", "")[:100],
            "description": _sanitize_description(metadata.get("description", "")),
            "tags": list(metadata.get("tags") or []),
            "categoryId": "27",
            "defaultLanguage": "nl",
            "defaultAudioLanguage": "nl",
        },
        "status": status,
        "playlist": data.get("playlist", ""),
        "playlist_description": data.get("playlist_description", ""),
        "playlist_id": data.get("playlist_id", ""),
        "topic": data.get("topic", {}),
        "thumbnail": data.get("generated_image_file", ""),
    }


def _load_google_clients():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        from google_auth_oauthlib.flow import InstalledAppFlow

        return Request, Credentials, build, MediaFileUpload, InstalledAppFlow
    except Exception as exc:
        raise RuntimeError(
            "Google API dependencies are missing. Install google-api-python-client, "
            "google-auth-oauthlib, and google-auth-httplib2."
        ) from exc


def _get_youtube_client():
    Request, Credentials, build, _, InstalledAppFlow = _load_google_clients()

    secrets_path = os.getenv("YOUTUBE_CLIENT_SECRETS", "")
    token_path = Path(os.getenv("YOUTUBE_TOKEN_PATH", "output/youtube_token.json"))

    if not secrets_path:
        raise RuntimeError("YOUTUBE_CLIENT_SECRETS is not set.")

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(secrets_path, SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")

    return build("youtube", "v3", credentials=creds)


def upload_video(artifact_path: Path, video_file: Path) -> dict:
    _, _, _, MediaFileUpload, _ = _load_google_clients()
    payload = build_upload_payload(artifact_path)
    youtube = _get_youtube_client()

    request = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": payload["snippet"],
            "status": payload["status"],
        },
        media_body=MediaFileUpload(str(video_file), mimetype="video/mp4", chunksize=-1, resumable=True),
    )
    response = request.execute()

    playlist_name = payload.get("playlist", "")
    configured_playlist_id = str(payload.get("playlist_id") or "").strip()
    playlist_id = None
    if response.get("id"):
        if configured_playlist_id:
            playlist_id = configured_playlist_id
            try:
                add_video_to_playlist(youtube, playlist_id, response["id"])
            except Exception:
                # Fallback for stale/invalid configured IDs.
                if playlist_name:
                    playlist_id = ensure_playlist(youtube, playlist_name, payload.get("playlist_description", ""))
                    if playlist_id:
                        add_video_to_playlist(youtube, playlist_id, response["id"])
                else:
                    raise
        elif playlist_name:
            playlist_id = ensure_playlist(youtube, playlist_name, payload.get("playlist_description", ""))
            if playlist_id:
                add_video_to_playlist(youtube, playlist_id, response["id"])

    captions_uploaded = []
    thumbnail_uploaded = False
    video_id = response.get("id")
    if video_id:
        thumbnail = payload.get("thumbnail", "")
        if thumbnail:
            thumb_path = Path(thumbnail)
            if not thumb_path.is_absolute():
                thumb_path = (artifact_path.parent.parent.parent / thumbnail).resolve()
            if thumb_path.exists():
                try:
                    youtube.thumbnails().set(
                        videoId=video_id,
                        media_body=MediaFileUpload(str(thumb_path), mimetype="image/png"),
                    ).execute()
                    thumbnail_uploaded = True
                except Exception as exc:
                    import logging
                    logging.getLogger(__name__).warning("Thumbnail upload failed: %s", exc)

        # Upload English SRT caption track
        artifact_data = json.loads(artifact_path.read_text(encoding="utf-8"))
        srt_en_raw = artifact_data.get("subtitles", {}).get("srt_en", "")
        if srt_en_raw:
            srt_path = Path(srt_en_raw)
            if not srt_path.is_absolute():
                srt_path = artifact_path.parent.parent.parent.parent / srt_en_raw
            try:
                caption_result = upload_captions(youtube, video_id, srt_path)
                if caption_result:
                    captions_uploaded.append({
                        "caption_id": caption_result.get("id"),
                        "language": caption_result.get("snippet", {}).get("language", "en"),
                        "name": caption_result.get("snippet", {}).get("name", "English"),
                        "srt_file": str(srt_path),
                    })
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning("Caption upload failed: %s", exc)

    return {
        "video_id": video_id,
        "playlist_name": playlist_name,
        "playlist_id": playlist_id,
        "captions_uploaded": captions_uploaded,
        "thumbnail_uploaded": thumbnail_uploaded,
    }


def ensure_playlist(youtube, title: str, description: str = "") -> str:
    request = youtube.playlists().list(
        part="snippet",
        mine=True,
        maxResults=50,
    )
    while request is not None:
        response = request.execute()
        for item in response.get("items", []):
            if item.get("snippet", {}).get("title", "").strip().lower() == title.strip().lower():
                return item.get("id")
        request = youtube.playlists().list_next(request, response)

    create = youtube.playlists().insert(
        part="snippet,status",
        body={
            "snippet": {"title": title, "description": description or "Auto-created by Dutch video pipeline"},
            "status": {"privacyStatus": "public"},
        },
    )
    created = create.execute()
    return created.get("id")


def add_video_to_playlist(youtube, playlist_id: str, video_id: str) -> None:
    youtube.playlistItems().insert(
        part="snippet",
        body={
            "snippet": {
                "playlistId": playlist_id,
                "resourceId": {
                    "kind": "youtube#video",
                    "videoId": video_id,
                },
            }
        },
    ).execute()


def upload_captions(
    youtube,
    video_id: str,
    srt_path: Path,
    language: str = "en",
    name: str = "English",
) -> dict | None:
    """Upload an SRT caption file to a YouTube video.

    Checks for an existing caption track with the same language first.
    If one already exists, logs a warning and returns its snippet without re-uploading.

    Args:
        youtube: Authorised YouTube API client (requires youtube.force-ssl scope).
        video_id: YouTube video ID to attach the caption to.
        srt_path: Path to the .srt file to upload.
        language: BCP-47 language code, e.g. "en".
        name: Human-readable caption track name shown in YouTube Studio.

    Returns:
        Caption resource dict on success, None if the SRT file is missing.
    """
    import logging
    from googleapiclient.http import MediaFileUpload as _MediaFileUpload

    logger = logging.getLogger(__name__)

    if not srt_path.exists():
        logger.warning("Caption SRT file not found, skipping upload: %s", srt_path)
        return None

    # Check for an existing caption track with the same language — update it if found
    existing = youtube.captions().list(
        part="snippet",
        videoId=video_id,
    ).execute()

    existing_id = None
    for item in existing.get("items", []):
        if item.get("snippet", {}).get("language") == language:
            existing_id = item.get("id")
            break

    if existing_id:
        logger.info(
            "Caption track for language=%r already exists on video %s (id=%s); updating.",
            language,
            video_id,
            existing_id,
        )
        response = youtube.captions().update(
            part="snippet",
            body={
                "id": existing_id,
                "snippet": {
                    "videoId": video_id,
                    "language": language,
                    "name": name,
                    "isDraft": False,
                },
            },
            media_body=_MediaFileUpload(str(srt_path), mimetype="application/octet-stream"),
        ).execute()
        logger.info(
            "✓ Caption updated: video=%s language=%s caption_id=%s",
            video_id,
            language,
            response.get("id"),
        )
        return response

    response = youtube.captions().insert(
        part="snippet",
        body={
            "snippet": {
                "videoId": video_id,
                "language": language,
                "name": name,
                "isDraft": False,
            }
        },
        media_body=_MediaFileUpload(str(srt_path), mimetype="application/octet-stream"),
    ).execute()

    logger.info(
        "✓ Caption uploaded: video=%s language=%s caption_id=%s",
        video_id,
        language,
        response.get("id"),
    )
    return response


def main() -> None:
    parser = argparse.ArgumentParser(description="YouTube upload dry-run payload generator")
    parser.add_argument("artifact", help="Path to episode artifact JSON")
    parser.add_argument("--video-file", help="Path to rendered mp4 for upload")
    parser.add_argument("--dry-run", action="store_true", help="Print payload without uploading")
    args = parser.parse_args()

    artifact_path = Path(args.artifact)
    payload = build_upload_payload(artifact_path)

    if args.dry_run or not args.video_file:
        print("Dry-run upload payload:")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    video_file = Path(args.video_file)
    if not video_file.exists():
        raise FileNotFoundError(f"Video file not found: {video_file}")

    result = upload_video(artifact_path, video_file)
    print("Upload completed:")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
