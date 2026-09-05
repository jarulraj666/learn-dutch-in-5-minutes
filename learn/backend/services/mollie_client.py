"""Thin async wrapper around the Mollie Payments API (v2) using httpx.

No SDK dependency: Mollie's REST API is small enough that a direct client
keeps the dependency footprint down and matches this project's other
services (which call third-party APIs directly over httpx).
"""
from __future__ import annotations

from typing import Any

import httpx

import settings

_BASE_URL = "https://api.mollie.com/v2"


class MollieError(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    if not settings.MOLLIE_API_KEY:
        raise MollieError("MOLLIE_API_KEY is not configured")
    return {"Authorization": f"Bearer {settings.MOLLIE_API_KEY}"}


async def create_payment(
    *,
    amount_cents: int,
    currency: str,
    description: str,
    redirect_url: str,
    webhook_url: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "amount": {"currency": currency, "value": f"{amount_cents / 100:.2f}"},
        "description": description,
        "redirectUrl": redirect_url,
        "webhookUrl": webhook_url,
        "metadata": metadata,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(f"{_BASE_URL}/payments", json=payload, headers=_headers())
    if resp.status_code >= 400:
        raise MollieError(f"Mollie create_payment failed ({resp.status_code}): {resp.text}")
    return resp.json()


async def get_payment(payment_id: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{_BASE_URL}/payments/{payment_id}", headers=_headers())
    if resp.status_code >= 400:
        raise MollieError(f"Mollie get_payment failed ({resp.status_code}): {resp.text}")
    return resp.json()
