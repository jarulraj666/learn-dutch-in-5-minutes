from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

import db
from auth import AdminUser
from models import AdminLearner

router = APIRouter()


@router.get("/admin/stats")
async def stats(_: AdminUser) -> dict:
    row = await db.fetch_one(
        """
        SELECT
          (SELECT count(*) FROM users) AS learners,
          (SELECT count(*) FROM users WHERE created_at > now() - interval '7 days') AS learners_new_7d,
          (SELECT count(*) FROM lessons) AS lessons,
          (SELECT count(*) FROM lesson_progress WHERE completed_at IS NOT NULL) AS lessons_completed,
          (SELECT count(*) FROM quiz_attempts) AS quiz_attempts,
          (SELECT count(*) FROM certificates) AS certificates
        """
    )
    return row or {}


@router.get("/admin/learners", response_model=list[AdminLearner])
async def learners(
    _: AdminUser,
    search: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[AdminLearner]:
    rows = await db.fetch_all(
        """
        SELECT u.id, u.email, u.name, u.created_at,
               count(DISTINCT p.lesson_id) FILTER (WHERE p.completed_at IS NOT NULL) AS lessons_completed,
               count(DISTINCT a.id) AS quiz_attempts,
               max(p.updated_at) AS last_active
        FROM users u
        LEFT JOIN lesson_progress p ON p.user_id = u.id
        LEFT JOIN quiz_attempts a ON a.user_id = u.id
        WHERE %s::text IS NULL
           OR u.email ILIKE '%%' || %s || '%%'
           OR u.name ILIKE '%%' || %s || '%%'
        GROUP BY u.id
        ORDER BY u.created_at DESC
        LIMIT %s OFFSET %s
        """,
        (search, search, search, limit, offset),
    )
    return [AdminLearner(**dict(row, id=str(row["id"]))) for row in rows]


@router.get("/admin/learners/{user_id}")
async def learner_detail(user_id: str, _: AdminUser) -> dict:
    user = await db.fetch_one(
        "SELECT id, email, name, plan, role, created_at FROM users WHERE id = %s", (user_id,)
    )
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Learner not found")

    return {
        "user": dict(user, id=str(user["id"])),
        "progress": await db.fetch_all(
            """
            SELECT l.id AS lesson_id, l.title, l.course_id, p.percent,
                   p.completed_at, p.updated_at
            FROM lesson_progress p
            JOIN lessons l ON l.id = p.lesson_id
            WHERE p.user_id = %s
            ORDER BY p.updated_at DESC
            """,
            (user_id,),
        ),
        "quiz_attempts": await db.fetch_all(
            """
            SELECT lesson_id, attempt_no, score, total, created_at
            FROM quiz_attempts WHERE user_id = %s ORDER BY created_at DESC LIMIT 100
            """,
            (user_id,),
        ),
        "certificates": await db.fetch_all(
            "SELECT serial, course_id, issued_at FROM certificates WHERE user_id = %s",
            (user_id,),
        ),
    }
