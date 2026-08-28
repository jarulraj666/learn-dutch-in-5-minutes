from __future__ import annotations

import secrets

from fastapi import APIRouter, HTTPException, status

import db
import settings
from auth import CurrentUser
from models import Certificate, CertificateEligibility

router = APIRouter()

_ELIGIBILITY_SQL = """
    SELECT
      count(DISTINCT l.id) AS lessons_total,
      count(DISTINCT l.id) FILTER (WHERE p.completed_at IS NOT NULL) AS lessons_completed,
      count(DISTINCT q.lesson_id) AS quizzes_total,
      count(DISTINCT q.lesson_id) FILTER (WHERE best.percent >= %s) AS quizzes_passed
    FROM lessons l
    JOIN modules m ON m.id = l.module_id
    LEFT JOIN lesson_progress p ON p.lesson_id = l.id AND p.user_id = %s
    LEFT JOIN quiz_questions q ON q.lesson_id = l.id
    LEFT JOIN LATERAL (
        SELECT max(round(a.score * 100.0 / NULLIF(a.total, 0))) AS percent
        FROM quiz_attempts a
        WHERE a.lesson_id = l.id AND a.user_id = %s
    ) best ON TRUE
    WHERE l.course_id = %s AND NOT m.is_optional
"""


async def _eligibility(user_id: str, course_id: str) -> dict:
    row = await db.fetch_one(
        _ELIGIBILITY_SQL,
        (settings.CERTIFICATE_PASS_PERCENT, user_id, user_id, course_id),
    )
    return row or {
        "lessons_total": 0, "lessons_completed": 0,
        "quizzes_total": 0, "quizzes_passed": 0,
    }


async def _existing(user_id: str, course_id: str) -> Certificate | None:
    row = await db.fetch_one(
        """
        SELECT ce.serial, ce.course_id, c.title AS course_title,
               COALESCE(u.name, u.email) AS user_name, ce.issued_at
        FROM certificates ce
        JOIN courses c ON c.id = ce.course_id
        JOIN users u ON u.id = ce.user_id
        WHERE ce.user_id = %s AND ce.course_id = %s
        """,
        (user_id, course_id),
    )
    return Certificate(**row) if row else None


@router.get("/courses/{course_id}/certificate", response_model=CertificateEligibility)
async def certificate_status(course_id: str, user: CurrentUser) -> CertificateEligibility:
    counts = await _eligibility(user["id"], course_id)
    eligible = bool(
        counts["lessons_total"]
        and counts["lessons_completed"] == counts["lessons_total"]
        and counts["quizzes_passed"] == counts["quizzes_total"]
    )
    return CertificateEligibility(
        course_id=course_id,
        eligible=eligible,
        pass_percent=settings.CERTIFICATE_PASS_PERCENT,
        certificate=await _existing(user["id"], course_id),
        **counts,
    )


@router.post("/courses/{course_id}/certificate", response_model=Certificate)
async def claim_certificate(course_id: str, user: CurrentUser) -> Certificate:
    existing = await _existing(user["id"], course_id)
    if existing:
        return existing

    counts = await _eligibility(user["id"], course_id)
    if not counts["lessons_total"]:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Course not found")
    if counts["lessons_completed"] != counts["lessons_total"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not all lessons are complete")
    if counts["quizzes_passed"] != counts["quizzes_total"]:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Every quiz must be passed with at least {settings.CERTIFICATE_PASS_PERCENT}%",
        )

    serial = f"{course_id}-{secrets.token_hex(6).upper()}"
    await db.execute(
        "INSERT INTO certificates (user_id, course_id, serial) VALUES (%s, %s, %s)"
        " ON CONFLICT (user_id, course_id) DO NOTHING",
        (user["id"], course_id, serial),
    )
    certificate = await _existing(user["id"], course_id)
    if not certificate:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Could not issue certificate")
    return certificate


@router.get("/certificates/{serial}", response_model=Certificate)
async def public_certificate(serial: str) -> Certificate:
    """Publicly verifiable — exposes only the holder's display name and course."""
    row = await db.fetch_one(
        """
        SELECT ce.serial, ce.course_id, c.title AS course_title,
               COALESCE(u.name, 'Learner') AS user_name, ce.issued_at
        FROM certificates ce
        JOIN courses c ON c.id = ce.course_id
        JOIN users u ON u.id = ce.user_id
        WHERE ce.serial = %s
        """,
        (serial,),
    )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Certificate not found")
    return Certificate(**row)
