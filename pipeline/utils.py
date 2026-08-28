from __future__ import annotations

import hashlib
import re
import shutil
from datetime import datetime, timezone
from typing import Any


_SPEAKER_KEY_RE = re.compile(r"^Speaker\d+$", re.IGNORECASE)
_SPEAKER_LINE_RE = re.compile(r"^\s*(Speaker\d+)\s*:\s*(.+?)\s*$", re.IGNORECASE)


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
    phrases = sorted(str(p) for p in key_phrases or [])
    source = f"{topic_id}|{title}|{'|'.join(phrases)}"
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


def parse_dialogue_turn(item: Any) -> tuple[str, str] | None:
    """Parse one dialogue item supporting compact and legacy schemas.

    Supported inputs:
    - {"Speaker1": "Hi"}
    - {"speaker": "Speaker1", "line": "Hi"}
    - "Speaker1: Hi"
    """
    if isinstance(item, str):
        text = item.strip()
        if not text:
            return None
        match = _SPEAKER_LINE_RE.match(text)
        if match:
            return match.group(1), match.group(2).strip()
        return "Speaker1", text

    if not isinstance(item, dict):
        return None

    if "speaker" in item or "line" in item:
        speaker = str(item.get("speaker", "Speaker1")).strip() or "Speaker1"
        line = str(item.get("line", "")).strip()
        if line:
            return speaker, line

    for key, value in item.items():
        if isinstance(key, str) and _SPEAKER_KEY_RE.match(key):
            line = str(value).strip()
            if line:
                return key, line

    return None


def iter_dialogue_turns(dialogue: list[Any] | None) -> list[tuple[str, str]]:
    """Return normalized (speaker, line) turns from mixed dialogue schemas."""
    if not dialogue:
        return []

    turns: list[tuple[str, str]] = []
    for item in dialogue:
        parsed = parse_dialogue_turn(item)
        if parsed is None:
            continue
        speaker, line = parsed
        turns.append((speaker, line))
    return turns


def to_compact_dialogue(turns: list[tuple[str, str]]) -> list[dict[str, str]]:
    """Convert normalized turns to compact schema: [{"Speaker1": "..."}, ...]."""
    return [{speaker: line} for speaker, line in turns if line]
