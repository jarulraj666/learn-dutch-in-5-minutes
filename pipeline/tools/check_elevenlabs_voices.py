from __future__ import annotations

import argparse
import json
from typing import Any

import requests

from pipeline import settings


def _extract_error_label(payload: Any) -> str:
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, dict):
            return (
                str(detail.get("code") or detail.get("message") or detail.get("type") or "unknown_error")
            )
        return str(payload.get("message") or payload.get("error") or payload)
    return str(payload)


def _as_voice_list(value: Any) -> list[str]:
    if isinstance(value, str):
        voices = [value]
    elif isinstance(value, list):
        voices = [v for v in value if isinstance(v, str)]
    else:
        voices = []
    return list(dict.fromkeys(v.strip() for v in voices if v.strip()))


def _resolve_plan_map(plan: str) -> dict[str, list[str]]:
    speech_cfg = settings.PEDAGOGY_CONFIG.get("speech", {})
    voice_map = speech_cfg.get("voice_map", {})
    elevenlabs = voice_map.get("elevenlabs", {})
    if not isinstance(elevenlabs, dict):
        elevenlabs = {}

    # Preferred nested format: elevenlabs.{free|paid}.{female|male}
    nested = elevenlabs.get(plan)
    if isinstance(nested, dict):
        return {
            "female": _as_voice_list(nested.get("female", [])),
            "male": _as_voice_list(nested.get("male", [])),
        }

    # Backward-compatible flat format: elevenlabs.{female|male}
    return {
        "female": _as_voice_list(elevenlabs.get("female", [])),
        "male": _as_voice_list(elevenlabs.get("male", [])),
    }


def _probe_voice(api_key: str, voice_id: str, text: str, model_id: str) -> tuple[bool, str, int]:
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
    params = {"output_format": "pcm_24000"}
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "application/octet-stream",
    }
    payload = {
        "text": text,
        "model_id": model_id,
        "voice_settings": {
            "stability": 0.45,
            "similarity_boost": 0.8,
            "style": 0.0,
            "use_speaker_boost": True,
            "speed": 0.9,
        },
    }

    resp = requests.post(url, headers=headers, params=params, json=payload, timeout=120)
    if resp.status_code == 200:
        return True, "usable_on_current_plan", resp.status_code

    label = "unknown_error"
    try:
        label = _extract_error_label(resp.json())
    except json.JSONDecodeError:
        label = (resp.text or "unknown_error")[:200]
    return False, label, resp.status_code


def _iter_plans(requested_plan: str) -> list[str]:
    if requested_plan == "all":
        return ["free", "paid"]
    return [requested_plan]


def main() -> int:
    parser = argparse.ArgumentParser(description="Check ElevenLabs configured voices for plan usability")
    parser.add_argument(
        "--plan",
        choices=["free", "paid", "all"],
        default="all",
        help="Which configured voice pool to test (default: all)",
    )
    parser.add_argument(
        "--model",
        default=settings.ELEVENLABS_MODEL,
        help="ElevenLabs model_id for probing (default: ELEVENLABS_MODEL from settings)",
    )
    parser.add_argument(
        "--text",
        default="Hallo",
        help="Probe text payload (default: Hallo)",
    )
    args = parser.parse_args()

    api_key = settings.ELEVENLABS_API_KEY
    if not api_key:
        print("ERROR: ELEVENLABS_API_KEY is not set.")
        return 2

    rows: list[tuple[str, str, str, str, int]] = []
    for plan in _iter_plans(args.plan):
        plan_map = _resolve_plan_map(plan)
        for gender in ("female", "male"):
            for voice_id in plan_map.get(gender, []):
                ok, label, status = _probe_voice(api_key, voice_id, args.text, args.model)
                state = "OK" if ok else "FAIL"
                rows.append((plan, gender, voice_id, f"{state}:{label}", status))

    if not rows:
        print("No configured voices found for requested plan(s).")
        return 1

    print("plan | gender | voice_id | result | http")
    print("-----|--------|----------|--------|-----")
    ok_count = 0
    for plan, gender, voice_id, result, status in rows:
        if result.startswith("OK"):
            ok_count += 1
        print(f"{plan} | {gender} | {voice_id} | {result} | {status}")

    print(f"\nsummary: {ok_count}/{len(rows)} voices usable on current account plan")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
