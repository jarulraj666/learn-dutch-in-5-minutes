from __future__ import annotations

import json
import re
from typing import Any

import requests

from pipeline import settings


def call_ollama(prompt: str, model: str | None = None, timeout: int = 180) -> str:
    payload = {
        "model": model or settings.OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "keep_alive": "0",  # Unload model immediately after request to free resources
    }
    url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/generate"
    response = requests.post(url, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json().get("response", "")


def extract_json_object(text: str) -> dict[str, Any]:
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError(f"No JSON object found in model output: {text[:200]}")
    json_str = match.group(0)
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON from model output: {str(e)}\nJSON text: {json_str[:500]}")
