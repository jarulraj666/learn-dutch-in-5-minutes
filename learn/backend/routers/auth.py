from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

import db
import settings
from auth import _bearer, delete_session, is_admin
from services.auth_email import send_auth_email

router = APIRouter(prefix="/auth")

_PASSWORD_SCRYPT_N = 2**14
_PASSWORD_SCRYPT_R = 8
_PASSWORD_SCRYPT_P = 1


class PasswordSignupRequest(BaseModel):
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=254)


class PasswordLoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class PasswordResetRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(min_length=8, max_length=128)


_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if not _EMAIL_PATTERN.fullmatch(normalized):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Enter a valid email address")
    return normalized


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_PASSWORD_SCRYPT_N, r=_PASSWORD_SCRYPT_R, p=_PASSWORD_SCRYPT_P)
    return "$".join(("scrypt", str(_PASSWORD_SCRYPT_N), str(_PASSWORD_SCRYPT_R), str(_PASSWORD_SCRYPT_P), salt.hex(), digest.hex()))


def _verify_password(password: str, encoded: str | None) -> bool:
    try:
        algorithm, n, r, p, salt_hex, digest_hex = (encoded or "").split("$", 5)
        if algorithm != "scrypt":
            return False
        candidate = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=int(n), r=int(r), p=int(p))
        return hmac.compare_digest(candidate, bytes.fromhex(digest_hex))
    except (ValueError, TypeError):
        return False


async def _create_session(user: dict) -> dict:
    session_token = secrets.token_urlsafe(32)
    await db.execute(
        "INSERT INTO sessions (\"userId\", expires, \"sessionToken\") VALUES (%s, %s, %s)",
        (user["id"], datetime.now(timezone.utc) + timedelta(days=30), session_token),
    )
    return {"token": session_token, "user": user}


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def _issue_email_token(identifier: str, expires: datetime) -> str:
    token = secrets.token_urlsafe(48)
    await db.execute("DELETE FROM verification_token WHERE identifier = %s", (identifier,))
    await db.execute(
        "INSERT INTO verification_token (identifier, token, expires) VALUES (%s, %s, %s)",
        (identifier, _token_hash(token), expires),
    )
    return token


async def _send_verification_email(email: str, name: str | None, token: str) -> None:
    link = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    await send_auth_email(
        email,
        "Verify your Learn Dutch account",
        f"Hi {name or 'there'},\n\nVerify your email address to activate your account:\n{link}\n\nThis link expires in 24 hours.",
    )


async def _send_reset_email(email: str, name: str | None, token: str) -> None:
    link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    await send_auth_email(
        email,
        "Reset your Learn Dutch password",
        f"Hi {name or 'there'},\n\nReset your password here:\n{link}\n\nThis link expires in 1 hour. If you did not request this, you can ignore this email.",
    )


@router.post("/password/signup")
async def password_signup(payload: PasswordSignupRequest) -> dict:
    email = _normalize_email(payload.email)
    try:
        user = await db.fetch_one(
            """
            INSERT INTO users (password_hash, name, email, "emailVerified", role)
            VALUES (%s, %s, %s, now(), 'learner')
            RETURNING id, email, name, image, plan, role
            """,
            (_hash_password(payload.password), payload.name.strip(), email),
        )
    except Exception as exc:
        if "duplicate key" in str(exc).lower():
            raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists") from None
        raise
    return {"signup_completed": True}


@router.post("/password/login")
async def password_login(payload: PasswordLoginRequest) -> dict:
    email = _normalize_email(payload.email)
    user = await db.fetch_one(
        "SELECT id, email, name, image, plan, role, password_hash, \"emailVerified\" "
        "FROM users WHERE lower(email) = %s",
        (email,),
    )
    if not user or not _verify_password(payload.password, user.get("password_hash")):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    return await _create_session({key: user[key] for key in ("id", "email", "name", "image", "plan", "role")})


@router.post("/password/verify-email")
async def verify_email(token: str = Query(min_length=20, max_length=200)) -> dict[str, bool]:
    row = await db.fetch_one(
        """
        SELECT u.id FROM verification_token vt
        JOIN users u ON u.id::text = replace(vt.identifier, 'verify:', '')
        WHERE vt.identifier LIKE 'verify:%' AND vt.token = %s AND vt.expires > now()
        """,
        (_token_hash(token),),
    )
    if not row:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Verification link is invalid or expired")
    await db.execute('UPDATE users SET "emailVerified" = now() WHERE id = %s', (row["id"],))
    await db.execute("DELETE FROM verification_token WHERE identifier = %s", (f"verify:{row['id']}",))
    return {"verified": True}


@router.post("/password/request-reset")
async def request_password_reset(payload: PasswordResetRequest) -> dict[str, str]:
    email = _normalize_email(payload.email)
    user = await db.fetch_one(
        'SELECT id, email, name FROM users WHERE lower(email) = %s AND password_hash IS NOT NULL',
        (email,),
    )
    if user:
        token = await _issue_email_token(f"reset:{user['id']}", datetime.now(timezone.utc) + timedelta(hours=1))
        try:
            await _send_reset_email(email, user["name"], token)
        except Exception:
            pass
    return {"message": "If an account exists for that email, recovery instructions have been sent."}


@router.post("/password/reset")
async def reset_password(payload: PasswordResetConfirmRequest) -> dict[str, bool]:
    row = await db.fetch_one(
        """
        SELECT u.id FROM verification_token vt
        JOIN users u ON u.id::text = replace(vt.identifier, 'reset:', '')
        WHERE vt.identifier LIKE 'reset:%' AND vt.token = %s AND vt.expires > now()
        """,
        (_token_hash(payload.token),),
    )
    if not row:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Reset link is invalid or expired")
    await db.execute("UPDATE users SET password_hash = %s WHERE id = %s", (_hash_password(payload.password), row["id"]))
    await db.execute('DELETE FROM sessions WHERE "userId" = %s', (row["id"],))
    await db.execute("DELETE FROM verification_token WHERE identifier = %s", (f"reset:{row['id']}",))
    return {"reset": True}


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