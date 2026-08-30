"""Session-token authentication.

Auth.js runs with the database session strategy, so a request is authenticated
by presenting the opaque ``sessionToken`` from the ``sessions`` table. The
Next.js server-side proxy attaches it as a bearer token; it is never exposed to
client-side JavaScript.
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, status

import db
import settings

_SESSION_SQL = """
    SELECT u.id, u.email, u.name, u.image, u.plan, u.role
    FROM sessions s
    JOIN users u ON u.id = s."userId"
    WHERE s."sessionToken" = %s AND s.expires > now()
"""


async def _user_for_token(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    return await db.fetch_one(_SESSION_SQL, (token,))


def _bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()


def is_admin(user: dict[str, Any]) -> bool:
    email = (user.get("email") or "").lower()
    return user.get("role") == "admin" or email in settings.ADMIN_EMAILS


async def optional_user(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any] | None:
    """Resolve the caller if a valid session token is present, else None."""
    return await _user_for_token(_bearer(authorization))


async def current_user(
    user: Annotated[dict[str, Any] | None, Depends(optional_user)],
) -> dict[str, Any]:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in required")
    return user


async def admin_user(
    user: Annotated[dict[str, Any], Depends(current_user)],
) -> dict[str, Any]:
    if not is_admin(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
    return user


CurrentUser = Annotated[dict[str, Any], Depends(current_user)]
OptionalUser = Annotated[dict[str, Any] | None, Depends(optional_user)]
AdminUser = Annotated[dict[str, Any], Depends(admin_user)]


async def delete_session(token: str | None) -> None:
    if token:
        await db.execute('DELETE FROM sessions WHERE "sessionToken" = %s', (token,))
