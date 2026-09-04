from __future__ import annotations

from pathlib import Path

import settings


def _r2_enabled() -> bool:
    return all((settings.R2_ENDPOINT_URL, settings.R2_ACCESS_KEY_ID, settings.R2_SECRET_ACCESS_KEY, settings.R2_BUCKET))


def _client():
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=settings.R2_ENDPOINT_URL,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        region_name="auto",
    )


def save(recording: bytes, object_name: str, fallback_path: Path) -> str:
    if _r2_enabled():
        key = f"private-recordings/{object_name}"
        _client().put_object(Bucket=settings.R2_BUCKET, Key=key, Body=recording)
        return f"r2://{key}"
    fallback_path.parent.mkdir(parents=True, exist_ok=True)
    fallback_path.write_bytes(recording)
    return str(fallback_path)


def read(storage_path: str) -> bytes:
    if storage_path.startswith("r2://"):
        key = storage_path.removeprefix("r2://")
        return _client().get_object(Bucket=settings.R2_BUCKET, Key=key)["Body"].read()
    return Path(storage_path).read_bytes()


def delete(storage_path: str) -> None:
    if storage_path.startswith("r2://"):
        _client().delete_object(Bucket=settings.R2_BUCKET, Key=storage_path.removeprefix("r2://"))
    else:
        Path(storage_path).unlink(missing_ok=True)