from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

import db
import settings
from auth import CurrentUser
from models import Dashboard, DashboardCourse, ProgressResult, ProgressUpdate

router = APIRouter()


@router.post("/progress", response_model=ProgressResult)
async def upsert_progress(payload: ProgressUpdate, user: CurrentUser) -> ProgressResult:
    lesson = await db.fetch_one(
        "SELECT id, duration_sec FROM lessons WHERE id = %s", (payload.lesson_id,)
    )
    if not lesson:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lesson not found")

    duration = payload.duration_sec or lesson["duration_sec"] or 0
    percent = min(100, round(payload.watched_sec * 100 / duration)) if duration else 0
    completed = percent >= settings.COMPLETION_PERCENT

    row = await db.fetch_one(
        """
        INSERT INTO lesson_progress
            (user_id, lesson_id, watched_sec, last_position_sec, percent, completed_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, CASE WHEN %s THEN now() END, now())
        ON CONFLICT (user_id, lesson_id) DO UPDATE SET
            watched_sec       = GREATEST(lesson_progress.watched_sec, EXCLUDED.watched_sec),
            last_position_sec = EXCLUDED.last_position_sec,
            percent           = GREATEST(lesson_progress.percent, EXCLUDED.percent),
            completed_at      = COALESCE(lesson_progress.completed_at, EXCLUDED.completed_at),
            updated_at        = now()
        RETURNING percent, (completed_at IS NOT NULL) AS completed
        """,
        (user["id"], payload.lesson_id, payload.watched_sec,
         payload.position_sec, percent, completed),
    )

    await db.execute(
        """
        INSERT INTO enrollments (user_id, course_id)
        SELECT %s, course_id FROM lessons WHERE id = %s
        ON CONFLICT DO NOTHING
        """,
        (user["id"], payload.lesson_id),
    )

    return ProgressResult(
        lesson_id=payload.lesson_id,
        percent=row["percent"],
        completed=row["completed"],
    )


@router.get("/me/dashboard", response_model=Dashboard)
async def dashboard(user: CurrentUser) -> Dashboard:
    course_rows = await db.fetch_all(
        """
        SELECT c.id AS course_id, c.title,
               count(l.id) FILTER (WHERE NOT m.is_optional) AS lessons_total,
               count(p.lesson_id) FILTER (WHERE NOT m.is_optional AND p.completed_at IS NOT NULL)
                   AS lessons_completed,
               count(l.id) FILTER (WHERE m.is_optional) AS optional_total,
               count(p.lesson_id) FILTER (WHERE m.is_optional AND p.completed_at IS NOT NULL)
                   AS optional_completed
        FROM courses c
        JOIN lessons l ON l.course_id = c.id
        JOIN modules m ON m.id = l.module_id
        LEFT JOIN lesson_progress p ON p.lesson_id = l.id AND p.user_id = %s
        WHERE c.status = 'published'
        GROUP BY c.id
        ORDER BY c.order_index
        """,
        (user["id"],),
    )

    courses: list[DashboardCourse] = []
    for row in course_rows:
        resume = await db.fetch_one(
            """
            SELECT l.id, l.title
            FROM lessons l
            JOIN modules m ON m.id = l.module_id
            LEFT JOIN lesson_progress p ON p.lesson_id = l.id AND p.user_id = %s
            WHERE l.course_id = %s AND p.completed_at IS NULL
            ORDER BY m.is_optional, m.order_index, l.order_index, l.id
            LIMIT 1
            """,
            (user["id"], row["course_id"]),
        )
        total = row["lessons_total"] or 0
        done = row["lessons_completed"] or 0
        courses.append(DashboardCourse(
            course_id=row["course_id"],
            title=row["title"],
            lessons_total=total,
            lessons_completed=done,
            percent=round(done * 100 / total) if total else 0,
            optional_total=row["optional_total"] or 0,
            optional_completed=row["optional_completed"] or 0,
            resume_lesson_id=resume["id"] if resume else None,
            resume_lesson_title=resume["title"] if resume else None,
        ))

    due = await db.fetch_one(
        "SELECT count(*) AS n FROM flashcard_reviews WHERE user_id = %s AND due_at <= now()",
        (user["id"],),
    )
    recent = await db.fetch_all(
        """
        SELECT l.id AS lesson_id, l.title, l.course_id, p.percent,
               (p.completed_at IS NOT NULL) AS completed, p.updated_at
        FROM lesson_progress p
        JOIN lessons l ON l.id = p.lesson_id
        WHERE p.user_id = %s
        ORDER BY p.updated_at DESC
        LIMIT 5
        """,
        (user["id"],),
    )

    return Dashboard(
        courses=courses,
        flashcards_due=due["n"] if due else 0,
        recent=recent,
    )
