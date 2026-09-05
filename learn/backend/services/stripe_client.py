"""Thin async wrapper around the Stripe API using httpx (no SDK dependency).

Stripe's REST API takes form-encoded (not JSON) bodies with bracket-style
nested keys, e.g. `line_items[0][price_data][unit_amount]=900`. `_flatten`
converts a nested dict/list payload into that form.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import urlencode

import httpx

import settings

_BASE_URL = "https://api.stripe.com/v1"
_WEBHOOK_TOLERANCE_SECONDS = 300


class StripeError(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    if not settings.STRIPE_SECRET_KEY:
        raise StripeError("STRIPE_SECRET_KEY is not configured")
    return {
        "Authorization": f"Bearer {settings.STRIPE_SECRET_KEY}",
        "Content-Type": "application/x-www-form-urlencoded",
    }


def _flatten(data: dict[str, Any], parent: str = "") -> list[tuple[str, Any]]:
    items: list[tuple[str, Any]] = []
    for key, value in data.items():
        full_key = f"{parent}[{key}]" if parent else key
        if isinstance(value, dict):
            items.extend(_flatten(value, full_key))
        elif isinstance(value, list):
            if value and isinstance(value[0], dict):
                for i, item in enumerate(value):
                    items.extend(_flatten(item, f"{full_key}[{i}]"))
            else:
                items.extend((f"{full_key}[]", item) for item in value)
        else:
            items.append((full_key, value))
    return items


async def create_checkout_session(
    *,
    amount_cents: int,
    currency: str,
    description: str,
    success_url: str,
    cancel_url: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "mode": "payment",
        "payment_method_types": ["card", "ideal"],
        "success_url": success_url,
        "cancel_url": cancel_url,
        "metadata": metadata,
        "line_items": [
            {
                "quantity": 1,
                "price_data": {
                    "currency": currency.lower(),
                    "unit_amount": amount_cents,
                    "product_data": {"name": description},
                },
            }
        ],
    }
    async with httpx.AsyncClient(timeout=15) as client:
        # httpx 0.28's AsyncClient mishandles data= as a list of tuples (needed for
        # repeated keys like payment_method_types[]), so encode the body ourselves.
        body = urlencode(_flatten(payload), doseq=False).encode()
        resp = await client.post(f"{_BASE_URL}/checkout/sessions", content=body, headers=_headers())
    if resp.status_code >= 400:
        raise StripeError(f"Stripe create_checkout_session failed ({resp.status_code}): {resp.text}")
    return resp.json()


async def retrieve_checkout_session(session_id: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{_BASE_URL}/checkout/sessions/{session_id}", headers=_headers())
    if resp.status_code >= 400:
        raise StripeError(f"Stripe retrieve_checkout_session failed ({resp.status_code}): {resp.text}")
    return resp.json()


def verify_and_parse_webhook(payload: bytes, sig_header: str) -> dict[str, Any]:
    """Verify the Stripe-Signature header per Stripe's documented HMAC scheme, then parse the event."""
    if not settings.STRIPE_WEBHOOK_SECRET:
        raise StripeError("STRIPE_WEBHOOK_SECRET is not configured")

    parts = dict(item.split("=", 1) for item in sig_header.split(",") if "=" in item)
    timestamp = parts.get("t")
    signature = parts.get("v1")
    if not timestamp or not signature:
        raise StripeError("Malformed Stripe-Signature header")
    if abs(time.time() - int(timestamp)) > _WEBHOOK_TOLERANCE_SECONDS:
        raise StripeError("Stripe webhook timestamp outside tolerance")

    signed_payload = f"{timestamp}.".encode() + payload
    expected = hmac.new(settings.STRIPE_WEBHOOK_SECRET.encode(), signed_payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise StripeError("Stripe webhook signature mismatch")

    return json.loads(payload)
