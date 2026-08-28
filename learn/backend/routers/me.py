from __future__ import annotations

from fastapi import APIRouter, Response, status

import db
from auth import CurrentUser
from models import UserProfile, UserSettings

router = APIRouter()


async def _settings(user_id: str) -> UserSettings:
    row = await db.fetch_one(
        "SELECT locale, email_opt_in FROM user_settings WHERE user_id = %s", (user_id,)
    )
    return UserSettings(**row) if row else UserSettings()


@router.get("/me", response_model=UserProfile)
async def get_profile(user: CurrentUser) -> UserProfile:
    return UserProfile(
        id=str(user["id"]),
        email=user["email"],
        name=user["name"],
        image=user["image"],
        plan=user["plan"],
        role=user["role"],
        settings=await _settings(user["id"]),
    )


@router.patch("/me/settings", response_model=UserSettings)
async def update_settings(payload: UserSettings, user: CurrentUser) -> UserSettings:
    await db.execute(
        """
        INSERT INTO user_settings (user_id, locale, email_opt_in, updated_at)
        VALUES (%s, %s, %s, now())
        ON CONFLICT (user_id) DO UPDATE SET
            locale = EXCLUDED.locale, email_opt_in = EXCLUDED.email_opt_in, updated_at = now()
        """,
        (user["id"], payload.locale, payload.email_opt_in),
    )
    return payload


@router.get("/me/export")
async def export_my_data(user: CurrentUser) -> dict:
    """GDPR data export — everything this app stores about the caller."""
    return {
        "profile": (await get_profile(user)).model_dump(mode="json"),
        "progress": await db.fetch_all(
            "SELECT lesson_id, watched_sec, percent, completed_at, updated_at"
            " FROM lesson_progress WHERE user_id = %s ORDER BY updated_at",
            (user["id"],),
        ),
        "quiz_attempts": await db.fetch_all(
            "SELECT lesson_id, attempt_no, score, total, answers, created_at"
            " FROM quiz_attempts WHERE user_id = %s ORDER BY created_at",
            (user["id"],),
        ),
        "flashcards": await db.fetch_all(
            "SELECT vocab_id, ease, interval_days, reps, lapses, due_at"
            " FROM flashcard_reviews WHERE user_id = %s",
            (user["id"],),
        ),
        "certificates": await db.fetch_all(
            "SELECT serial, course_id, issued_at FROM certificates WHERE user_id = %s",
            (user["id"],),
        ),
    }


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(user: CurrentUser) -> Response:
    """Cascades to progress, attempts, flashcards, certificates and auth rows."""
    await db.execute("DELETE FROM users WHERE id = %s", (user["id"],))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
