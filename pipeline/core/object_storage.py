"""Upload generated mock-exam media to an S3-compatible public bucket."""
from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import Any

from pipeline import settings


class ObjectStorageError(RuntimeError):
    pass


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ObjectStorageError(f"{name} is required for production media sync")
    return value


def _client() -> tuple[Any, str, str]:
    try:
        import boto3
    except ModuleNotFoundError as exc:
        raise ObjectStorageError("boto3 is required for production media sync") from exc

    endpoint = _required("R2_ENDPOINT_URL")
    bucket = _required("R2_BUCKET")
    public_base_url = _required("R2_PUBLIC_BASE_URL").rstrip("/")
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=_required("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=_required("R2_SECRET_ACCESS_KEY"),
        region_name="auto",
    )
    return client, bucket, public_base_url


def upload_mock_exam_media(artifact: dict[str, Any]) -> int:
    """Upload local mock-exam media and mutate its URLs to public object URLs."""
    client, bucket, public_base_url = _client()
    uploaded = 0

    def upload_url(url: str | None) -> str | None:
        nonlocal uploaded
        if not url or url.startswith(("http://", "https://")):
            return url
        path = Path(url)
        source = path if path.is_absolute() else settings.ROOT / path
        if not source.exists() or not source.is_file():
            raise ObjectStorageError(f"Media file does not exist: {url}")
        try:
            relative_path = source.resolve().relative_to(settings.ROOT.resolve())
        except ValueError as exc:
            raise ObjectStorageError(f"Media file is outside the project: {source}") from exc
        key = f"mock-exams/{artifact['id']}/{relative_path.as_posix()}"
        content_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        client.upload_file(str(source), bucket, key, ExtraArgs={"ContentType": content_type})
        uploaded += 1
        return f"{public_base_url}/{key}"

    for passage in artifact.get("passages", []):
        for media in passage.get("media_urls", []):
            media["url"] = upload_url(media.get("url"))
    for question in artifact.get("questions", []):
        for field in ("question_audio_url", "question_options_audio_url"):
            question[field] = upload_url(question.get(field))
        for field in ("option_audio_urls", "option_media_urls"):
            if question.get(field):
                question[field] = [upload_url(url) for url in question[field]]
    return uploaded