from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, status

import db
from auth import AdminUser
from models import AdminFeedback, AdminLearner, MockExamGenerateRequest, MockExamSummary

router = APIRouter()
LOGGER = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent.parent.parent
_VALID_SECTIONS = {"reading", "listening", "writing", "speaking", "knm"}
_VALID_STAGES = {"content", "media", "question_audio", "export", "production_sync"}


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


@router.get("/admin/feedback", response_model=list[AdminFeedback])
async def admin_feedback(_: AdminUser, status_filter: str | None = Query(default=None, alias="status")) -> list[AdminFeedback]:
    rows = await db.fetch_all(
        """
        SELECT f.id, f.user_id::text AS user_id, COALESCE(f.display_name, u.name) AS name, u.email,
               f.rating, f.comment, f.status, f.created_at, f.published_at
        FROM feedback f
        LEFT JOIN users u ON u.id = f.user_id
        WHERE %s::text IS NULL OR f.status = %s
        ORDER BY f.created_at DESC
        """,
        (status_filter, status_filter),
    )
    return [AdminFeedback(**row) for row in rows]


@router.patch("/admin/feedback/{feedback_id}/publish")
async def publish_feedback(feedback_id: int, _: AdminUser) -> dict:
    row = await db.fetch_one("SELECT id FROM feedback WHERE id = %s", (feedback_id,))
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Feedback not found")
    await db.execute(
        "UPDATE feedback SET status = 'published', published_at = now() WHERE id = %s",
        (feedback_id,),
    )
    return {"ok": True}


@router.patch("/admin/feedback/{feedback_id}/reject")
async def reject_feedback(feedback_id: int, _: AdminUser) -> dict:
    row = await db.fetch_one("SELECT id FROM feedback WHERE id = %s", (feedback_id,))
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Feedback not found")
    await db.execute(
        "UPDATE feedback SET status = 'rejected', published_at = NULL WHERE id = %s",
        (feedback_id,),
    )
    return {"ok": True}


@router.get("/admin/mock-exams", response_model=list[MockExamSummary])
async def admin_mock_exams(_: AdminUser, section: str | None = None) -> list[MockExamSummary]:
    """Unlike the public /mock-exams endpoint, this returns exams in every status (draft included)."""
    query = (
        "SELECT id, section, level, exam_number, title, time_limit_minutes, total_questions, "
        "parts_count, pass_threshold, max_score, status, is_free_preview FROM mock_exams"
    )
    params: tuple = ()
    if section:
        query += " WHERE section = %s"
        params = (section,)
    query += " ORDER BY section, exam_number"
    rows = await db.fetch_all(query, params)
    return [MockExamSummary(**row) for row in rows]


@router.patch("/admin/mock-exams/{exam_id}/publish")
async def publish_mock_exam(exam_id: str, _: AdminUser) -> dict:
    row = await db.fetch_one("SELECT id FROM mock_exams WHERE id = %s", (exam_id,))
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mock exam not found")
    await db.execute("UPDATE mock_exams SET status = 'published' WHERE id = %s", (exam_id,))
    return {"ok": True}


@router.patch("/admin/mock-exams/{exam_id}/unpublish")
async def unpublish_mock_exam(exam_id: str, _: AdminUser) -> dict:
    row = await db.fetch_one("SELECT id FROM mock_exams WHERE id = %s", (exam_id,))
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mock exam not found")
    await db.execute("UPDATE mock_exams SET status = 'draft' WHERE id = %s", (exam_id,))
    return {"ok": True}


async def _run_generation(section: str, exam_number: int, stage: str) -> None:
    log_dir = ROOT / "output" / "mock_exams" / "generation_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{section}-{exam_number}-{stage}.log"
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "pipeline.tools.generate_and_export_mock_exams",
        "--section", section, "--exam-number", str(exam_number), "--stage", stage,
        cwd=str(ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    output = await proc.stdout.read() if proc.stdout else b""
    log_path.write_bytes(output)
    await proc.wait()
    if proc.returncode != 0:
        LOGGER.error("Mock exam generation failed (%s-%s-%s), see %s", section, exam_number, stage, log_path)
    else:
        LOGGER.info("Mock exam generation finished (%s-%s-%s), log at %s", section, exam_number, stage, log_path)


@router.post("/admin/mock-exams/generate")
async def generate_mock_exam(payload: MockExamGenerateRequest, _: AdminUser) -> dict:
    """Kicks off `pipeline.tools.generate_and_export_mock_exams` in the background.

    Stages run in order (content → media → question_audio → export) and each can take
    from ~30s (content) to several minutes (media), so this returns immediately rather
    than blocking the request; check the log file or re-fetch /admin/mock-exams to see
    the result. Newly exported exams land as status='draft' until explicitly published.
    """
    if payload.section not in _VALID_SECTIONS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid section")
    if payload.stage not in _VALID_STAGES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid stage")
    if not 1 <= payload.exam_number <= 99:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid exam number")

    asyncio.create_task(_run_generation(payload.section, payload.exam_number, payload.stage))
    return {
        "ok": True,
        "message": f"Generation started for {payload.section} #{payload.exam_number} ({payload.stage} stage). "
                   "This can take a few minutes — refresh the exam list shortly to check progress.",
    }
