from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipeline import settings
from pipeline.ollama_client import call_ollama, extract_json_object
from pipeline.utils import srt_timestamp


def _translate_lines_with_ollama(lines: list[str]) -> list[str]:
    prompt = (
        "Translate the following Dutch dialogue lines to natural beginner-friendly English. "
        "Return strict JSON only with shape: {\"translations\":[\"...\"]}.\n\n"
        f"Lines:\n{json.dumps(lines, ensure_ascii=False)}"
    )
    try:
        text = call_ollama(prompt)
        obj = extract_json_object(text)
        translated = obj.get("translations", [])
        if isinstance(translated, list) and len(translated) == len(lines):
            return [str(x) for x in translated]
    except Exception:
        pass
    return [f"{line} (English translation pending)" for line in lines]


def _english_lines(script: dict[str, Any], dutch_lines: list[str]) -> list[str]:
    translations = script.get("translations", [])
    if isinstance(translations, list) and len(translations) == len(dutch_lines):
        extracted: list[str] = []
        for item in translations:
            if isinstance(item, dict):
                extracted.append(str(item.get("en", "")).strip())
            else:
                extracted.append(str(item).strip())
        if all(extracted):
            return extracted
    return _translate_lines_with_ollama(dutch_lines)


def _write_srt_block(srt_path: Path, subtitle_rows: list[tuple[str, str, str]]) -> None:
    lines: list[str] = []
    for idx, (start_ts, end_ts, text) in enumerate(subtitle_rows, start=1):
        lines.append(str(idx))
        lines.append(f"{start_ts} --> {end_ts}")
        lines.append(text)
        lines.append("")
    srt_path.write_text("\n".join(lines), encoding="utf-8")


def generate_srt(script: dict[str, Any], output_root: str = "output") -> dict[str, str]:
    dialogue = script.get("dialogue", [])
    out_dir = Path(output_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    srt_nl_path = out_dir / "subtitles_nl.srt"
    srt_en_path = out_dir / "subtitles_en.srt"
    srt_bi_path = out_dir / "subtitles_bilingual.srt"

    current_start = 0.0
    subtitle_rows_nl: list[tuple[str, str, str]] = []
    subtitle_rows_en: list[tuple[str, str, str]] = []
    subtitle_rows_bi: list[tuple[str, str, str]] = []

    dutch_lines = [str(item.get("line", "")) for item in dialogue]
    english_lines = _english_lines(script, dutch_lines)

    for idx, item in enumerate(dialogue, start=1):
        text = item.get("line", "")
        text_en = english_lines[idx - 1] if idx - 1 < len(english_lines) else ""
        words = max(1, len(text.split()))
        speech_cfg = settings.PEDAGOGY_CONFIG.get("speech", {})
        words_per_second = float(speech_cfg.get("estimated_words_per_second", 1.6))
        duration = max(1.4, words / words_per_second + 0.35)
        end = current_start + duration

        start_ts = srt_timestamp(current_start)
        end_ts = srt_timestamp(end)
        subtitle_rows_nl.append((start_ts, end_ts, text))
        subtitle_rows_en.append((start_ts, end_ts, text_en))
        subtitle_rows_bi.append((start_ts, end_ts, f"{text}\\N{text_en}"))

        current_start = end + 0.15

    _write_srt_block(srt_nl_path, subtitle_rows_nl)
    _write_srt_block(srt_en_path, subtitle_rows_en)
    _write_srt_block(srt_bi_path, subtitle_rows_bi)
    return {
        "nl": str(srt_nl_path),
        "en": str(srt_en_path),
        "bilingual": str(srt_bi_path),
    }


def plan_subtitles(script: dict[str, Any]) -> dict[str, Any]:
    dialogue = script.get("dialogue", [])
    subtitles = []
    for idx, item in enumerate(dialogue, start=1):
        subtitles.append(
            {
                "index": idx,
                "speaker": item.get("speaker", "Speaker1"),
                "text": item.get("line", ""),
            }
        )

    srt_files = generate_srt(script)
    return {
        "subtitles": subtitles,
        "srt_file": srt_files.get("bilingual", ""),
        "srt_files": srt_files,
    }
