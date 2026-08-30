from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

import db
import settings
from auth import _bearer, delete_session, is_admin

router = APIRouter(prefix="/auth")


def _state_payload(return_to: str) -> str:
    if not settings.AUTH_STATE_SECRET:
        raise HTTPException(500, "AUTH_STATE_SECRET is not configured")
    payload = {"return_to": return_to, "exp": int(time.time()) + 600, "nonce": secrets.token_urlsafe(16)}
    raw = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    signature = hmac.new(settings.AUTH_STATE_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()
    return f"{raw}.{signature}"


def _read_state(state: str) -> dict:
    try:
        raw, signature = state.split(".", 1)
        expected = hmac.new(settings.AUTH_STATE_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        payload = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        if int(payload["exp"]) < int(time.time()):
            raise ValueError
        return payload
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise HTTPException(400, "Invalid or expired OAuth state") from None


def _safe_return_to(value: str) -> str:
    if not value.startswith("/") or value.startswith("//"):
        return "/dashboard"
    return value


@router.get("/google/start")
async def google_start(return_to: str = Query("/dashboard")) -> RedirectResponse:
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(500, "Google OAuth is not configured")
    query = urlencode({
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": _state_payload(_safe_return_to(return_to)),
        "nonce": secrets.token_urlsafe(16),
        "access_type": "online",
        "prompt": "select_account",
    })
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{query}")


@router.get("/google/callback")
async def google_callback(code: str, state: str) -> dict:
    payload = _read_state(state)
    async with httpx.AsyncClient(timeout=15) as client:
        token_response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        if token_response.is_error:
            raise HTTPException(400, "Google token exchange failed")
        access_token = token_response.json().get("access_token")
        if not access_token:
            raise HTTPException(400, "Google did not return an access token")
        user_response = await client.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if user_response.is_error:
        raise HTTPException(400, "Google user lookup failed")
    google_user = user_response.json()
    subject = str(google_user.get("sub") or "")
    email = str(google_user.get("email") or "").strip().lower()
    if not subject or not email or google_user.get("email_verified") is not True:
        raise HTTPException(400, "Google account has no verified email")

    user = await db.fetch_one(
        """
        INSERT INTO users (email, name, image, \"emailVerified\", role)
        VALUES (%s, %s, %s, now(), CASE WHEN %s = ANY(%s) THEN 'admin' ELSE 'learner' END)
        ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name, image = EXCLUDED.image,
          \"emailVerified\" = EXCLUDED.\"emailVerified\",
          role = CASE WHEN users.role = 'admin' OR EXCLUDED.role = 'admin' THEN 'admin' ELSE users.role END
        RETURNING id, email, name, image, plan, role
        """,
        (email, google_user.get("name"), google_user.get("picture"), email, list(settings.ADMIN_EMAILS)),
    )
    await db.execute(
        """
        INSERT INTO accounts (\"userId\", type, provider, \"providerAccountId\", access_token)
        VALUES (%s, 'oidc', 'google', %s, %s)
        ON CONFLICT (provider, \"providerAccountId\") DO UPDATE SET \"userId\" = EXCLUDED.\"userId\",
          access_token = EXCLUDED.access_token
        """,
        (user["id"], subject, access_token),
    )
    session_token = secrets.token_urlsafe(32)
    await db.execute(
        "INSERT INTO sessions (\"userId\", expires, \"sessionToken\") VALUES (%s, %s, %s)",
        (user["id"], datetime.now(timezone.utc) + timedelta(days=30), session_token),
    )
    return {"token": session_token, "user": user, "return_to": _safe_return_to(payload["return_to"])}


@router.get("/session")
async def session(request: Request) -> dict | None:
    user = await db.fetch_one(_SESSION_SQL, (_bearer(request.headers.get("authorization")),))
    return {"user": dict(user, is_admin=is_admin(user))} if user else None


@router.post("/logout", status_code=204)
async def logout(request: Request) -> None:
    await delete_session(_bearer(request.headers.get("authorization")))


_SESSION_SQL = """
SELECT u.id, u.email, u.name, u.image, u.plan, u.role
FROM sessions s JOIN users u ON u.id = s.\"userId\"
WHERE s.\"sessionToken\" = %s AND s.expires > now()
"""