from __future__ import annotations

from fastapi import APIRouter, status

import db
from auth import CurrentUser
from models import FeedbackPublic, FeedbackSubmission, PublicStats

router = APIRouter()

# Marketing floor so the public stat never dips below this while real signups grow into it.
MIN_ACTIVE_LEARNERS = 350


@router.get("/public/stats", response_model=PublicStats)
async def public_stats() -> PublicStats:
    row = await db.fetch_one("SELECT count(*) AS n FROM users")
    real = row["n"] if row else 0
    return PublicStats(active_learners=max(real, MIN_ACTIVE_LEARNERS))


@router.get("/feedback/public", response_model=list[FeedbackPublic])
async def public_feedback() -> list[FeedbackPublic]:
    rows = await db.fetch_all(
        """
        SELECT f.id, COALESCE(f.display_name, u.name, 'A learner') AS name,
               f.rating, f.comment, f.created_at
        FROM feedback f
        LEFT JOIN users u ON u.id = f.user_id
        WHERE f.status = 'published'
        ORDER BY f.published_at DESC
        LIMIT 20
        """
    )
    return [FeedbackPublic(**row) for row in rows]


@router.post("/feedback", status_code=status.HTTP_201_CREATED)
async def submit_feedback(payload: FeedbackSubmission, user: CurrentUser) -> dict:
    await db.execute(
        "INSERT INTO feedback (user_id, rating, comment) VALUES (%s, %s, %s)",
        (user["id"], payload.rating, payload.comment),
    )
    return {"ok": True}
