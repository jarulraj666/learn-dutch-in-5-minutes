from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import APIRouter, Form, HTTPException, Request, Response, status

import db
import settings
from auth import CurrentUser
from models import CheckoutRequest, CheckoutResponse, Entitlement
from services import mollie_client, stripe_client
from services.entitlements import ENTITLEMENT_DAYS, PRICES_CENTS, list_active_entitlements

router = APIRouter()
LOGGER = logging.getLogger(__name__)

_VALID_SECTIONS = {"reading", "listening", "writing", "speaking", "knm"}


@router.post("/billing/checkout", response_model=CheckoutResponse)
async def create_checkout(payload: CheckoutRequest, user: CurrentUser) -> CheckoutResponse:
    if payload.product not in PRICES_CENTS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown product")
    if payload.product == "section" and payload.section not in _VALID_SECTIONS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A valid section is required")
    section = payload.section if payload.product == "section" else None
    amount_cents = PRICES_CENTS[payload.product]

    purchase_id = uuid4()
    description = (
        f"Inburgering exams — {section} section (3 months)"
        if section
        else "Inburgering exams — complete package (3 months)"
    )

    provider = settings.PAYMENT_PROVIDER
    if provider == "stripe":
        try:
            session = await stripe_client.create_checkout_session(
                amount_cents=amount_cents,
                currency="EUR",
                description=description,
                success_url=f"{settings.FRONTEND_URL}/pricing?checkout=pending",
                cancel_url=f"{settings.FRONTEND_URL}/pricing?checkout=canceled",
                metadata={"purchase_id": str(purchase_id)},
            )
        except stripe_client.StripeError as exc:
            LOGGER.error("Stripe checkout failed: %s", exc)
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Payments are temporarily unavailable") from exc
        checkout_url = session.get("url")
        provider_payment_id = session.get("id")
    elif provider == "mollie":
        try:
            payment = await mollie_client.create_payment(
                amount_cents=amount_cents,
                currency="EUR",
                description=description,
                redirect_url=f"{settings.FRONTEND_URL}/pricing?checkout=pending",
                webhook_url=f"{settings.API_BASE_URL}/api/billing/webhook/mollie",
                metadata={"purchase_id": str(purchase_id)},
            )
        except mollie_client.MollieError as exc:
            LOGGER.error("Mollie checkout failed: %s", exc)
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Payments are temporarily unavailable") from exc
        checkout_url = payment.get("_links", {}).get("checkout", {}).get("href")
        provider_payment_id = payment.get("id")
    else:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "No payment provider configured")

    if not checkout_url or not provider_payment_id:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Payments are temporarily unavailable")

    await db.execute(
        "INSERT INTO premium_purchases (id, user_id, product, section, amount_cents, currency, provider, provider_payment_id, status) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'open')",
        (purchase_id, user["id"], payload.product, section, amount_cents, "EUR", provider, provider_payment_id),
    )

    return CheckoutResponse(checkout_url=checkout_url)


@router.post("/billing/webhook/mollie")
async def mollie_webhook(payment_id: str = Form(alias="id")) -> Response:
    """Mollie calls back with only a payment id; we re-fetch the payment to trust its status."""
    try:
        payment = await mollie_client.get_payment(payment_id)
    except mollie_client.MollieError as exc:
        LOGGER.error("Mollie webhook lookup failed for %s: %s", payment_id, exc)
        return Response(status_code=status.HTTP_200_OK)

    status_map = {"paid": "paid", "failed": "failed", "expired": "expired", "canceled": "canceled"}
    new_status = status_map.get(payment.get("status"))
    if new_status is None:
        return Response(status_code=status.HTTP_200_OK)
    await _apply_status("mollie", payment_id, new_status)
    return Response(status_code=status.HTTP_200_OK)


@router.post("/billing/webhook/stripe")
async def stripe_webhook(request: Request) -> Response:
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    try:
        event = stripe_client.verify_and_parse_webhook(payload, sig_header)
    except stripe_client.StripeError as exc:
        LOGGER.warning("Stripe webhook rejected: %s", exc)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid signature") from exc

    session = event.get("data", {}).get("object", {})
    session_id = session.get("id")
    if not session_id:
        return Response(status_code=status.HTTP_200_OK)

    event_type = event.get("type")
    if event_type == "checkout.session.completed" and session.get("payment_status") == "paid":
        await _apply_status("stripe", session_id, "paid")
    elif event_type == "checkout.session.expired":
        await _apply_status("stripe", session_id, "expired")
    return Response(status_code=status.HTTP_200_OK)


async def _apply_status(provider: str, provider_payment_id: str, new_status: str) -> None:
    if new_status == "paid":
        await db.execute(
            "UPDATE premium_purchases SET status = 'paid', paid_at = now(), "
            f"expires_at = now() + interval '{ENTITLEMENT_DAYS} days' "
            "WHERE provider = %s AND provider_payment_id = %s AND status != 'paid'",
            (provider, provider_payment_id),
        )
    else:
        await db.execute(
            "UPDATE premium_purchases SET status = %s WHERE provider = %s AND provider_payment_id = %s AND status = 'open'",
            (new_status, provider, provider_payment_id),
        )


@router.get("/billing/me", response_model=list[Entitlement])
async def my_entitlements(user: CurrentUser) -> list[Entitlement]:
    rows = await list_active_entitlements(user["id"])
    return [Entitlement(**row) for row in rows]

