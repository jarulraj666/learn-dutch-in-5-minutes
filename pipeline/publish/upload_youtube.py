from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from pipeline import settings  # ensures .env is loaded


SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
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
    subtitle_files = data.get("subtitles", {}).get("srt_files", {})

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
            "tags": metadata.get("tags", []),
            "categoryId": "27"
        },
        "status": status,
        "playlist": data.get("playlist", ""),
        "playlist_description": data.get("playlist_description", ""),
        "topic": data.get("topic", {}),
        "thumbnail": data.get("generated_image_file", ""),
        "captions": {
            "nl": subtitle_files.get("nl", ""),
            "en": subtitle_files.get("en", ""),
            "bilingual": subtitle_files.get("bilingual", ""),
        },
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
        media_body=MediaFileUpload(str(video_file), chunksize=-1, resumable=True),
    )
    response = request.execute()

    playlist_name = payload.get("playlist", "")
    playlist_id = None
    if playlist_name:
        playlist_id = ensure_playlist(youtube, playlist_name, payload.get("playlist_description", ""))
        if playlist_id and response.get("id"):
            add_video_to_playlist(youtube, playlist_id, response["id"])

    captions_uploaded = []
    thumbnail_uploaded = False
    video_id = response.get("id")
    if video_id:
        captions_uploaded.extend(upload_caption_tracks(youtube, video_id, payload.get("captions", {})))

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

    return {
        "video_id": video_id,
        "playlist_name": playlist_name,
        "playlist_id": playlist_id,
        "captions_uploaded": captions_uploaded,
        "thumbnail_uploaded": thumbnail_uploaded,
    }


def upload_caption_tracks(youtube, video_id: str, captions: dict) -> list[dict]:
    _, _, _, MediaFileUpload, _ = _load_google_clients()
    uploaded = []

    mapping = [
        ("nl", "Dutch"),
        ("en", "English"),
    ]
    for lang, label in mapping:
        p = captions.get(lang, "")
        if not p:
            continue
        file_path = Path(p)
        if not file_path.exists():
            continue

        request = youtube.captions().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": video_id,
                    "language": lang,
                    "name": f"{label} subtitles",
                    "isDraft": False,
                }
            },
            media_body=MediaFileUpload(str(file_path), mimetype="application/x-subrip", resumable=False),
        )
        response = request.execute()
        uploaded.append({"language": lang, "caption_id": response.get("id")})

    return uploaded


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
