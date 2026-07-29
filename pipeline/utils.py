from __future__ import annotations

import hashlib
import re
import shutil
from datetime import datetime, timezone


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def tokenize(text: str) -> set[str]:
    cleaned = re.sub(r"[^a-zA-Z0-9 ]", " ", text.lower())
    return {p for p in cleaned.split() if p}


def jaccard_similarity(a: str, b: str) -> float:
    sa = tokenize(a)
    sb = tokenize(b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def content_fingerprint(topic_id: str, title: str, key_phrases: list[str]) -> str:
    source = f"{topic_id}|{title}|{'|'.join(sorted(key_phrases))}"
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def srt_timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    ms_total = int(round(seconds * 1000))
    hours = ms_total // 3600000
    minutes = (ms_total % 3600000) // 60000
    secs = (ms_total % 60000) // 1000
    millis = ms_total % 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
