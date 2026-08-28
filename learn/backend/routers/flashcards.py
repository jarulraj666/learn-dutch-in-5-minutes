from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

import db
from auth import CurrentUser
from models import FlashcardDue, FlashcardReview, FlashcardState

router = APIRouter()


def _sm2(ease: float, interval_days: int, reps: int, quality: int) -> tuple[float, int, int]:
    """SuperMemo-2. Quality < 3 resets the interval; ease never drops below 1.3."""
    if quality < 3:
        return max(1.3, ease - 0.2), 1, 0

    ease = max(1.3, ease + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)))
    reps += 1
    if reps == 1:
        interval_days = 1
    elif reps == 2:
        interval_days = 6
    else:
        interval_days = max(1, round(interval_days * ease))
    return ease, interval_days, reps


@router.get("/flashcards/due", response_model=list[FlashcardDue])
async def due_cards(
    user: CurrentUser,
    course_id: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[FlashcardDue]:
    """Cards scheduled for review, topped up with unseen words from completed lessons."""
    rows = await db.fetch_all(
        """
        SELECT v.id AS vocab_id, v.nl, v.en, l.id AS lesson_id, l.title AS lesson_title,
               COALESCE(f.reps, 0) AS reps
        FROM lesson_vocabulary v
        JOIN lessons l ON l.id = v.lesson_id
        JOIN lesson_progress p ON p.lesson_id = l.id AND p.user_id = %s
        LEFT JOIN flashcard_reviews f ON f.vocab_id = v.id AND f.user_id = %s
        WHERE p.completed_at IS NOT NULL
          AND (%s::text IS NULL OR l.course_id = %s)
          AND (f.vocab_id IS NULL OR f.due_at <= now())
        ORDER BY (f.vocab_id IS NOT NULL) DESC, f.due_at NULLS LAST, v.id
        LIMIT %s
        """,
        (user["id"], user["id"], course_id, course_id, limit),
    )
    return [FlashcardDue(**row) for row in rows]


@router.post("/flashcards/review", response_model=FlashcardState)
async def review_card(payload: FlashcardReview, user: CurrentUser) -> FlashcardState:
    exists = await db.fetch_one(
        "SELECT id FROM lesson_vocabulary WHERE id = %s", (payload.vocab_id,)
    )
    if not exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vocabulary item not found")

    state = await db.fetch_one(
        "SELECT ease, interval_days, reps, lapses FROM flashcard_reviews"
        " WHERE user_id = %s AND vocab_id = %s",
        (user["id"], payload.vocab_id),
    )
    ease = state["ease"] if state else 2.5
    interval_days = state["interval_days"] if state else 0
    reps = state["reps"] if state else 0
    lapses = state["lapses"] if state else 0

    ease, interval_days, reps = _sm2(ease, interval_days, reps, payload.quality)
    if payload.quality < 3:
        lapses += 1

    row = await db.fetch_one(
        """
        INSERT INTO flashcard_reviews
            (user_id, vocab_id, ease, interval_days, reps, lapses, due_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, now() + make_interval(days => %s), now())
        ON CONFLICT (user_id, vocab_id) DO UPDATE SET
            ease = EXCLUDED.ease, interval_days = EXCLUDED.interval_days,
            reps = EXCLUDED.reps, lapses = EXCLUDED.lapses,
            due_at = EXCLUDED.due_at, updated_at = now()
        RETURNING vocab_id, ease, interval_days, reps, due_at
        """,
        (user["id"], payload.vocab_id, ease, interval_days, reps, lapses, interval_days),
    )
    return FlashcardState(**row)
