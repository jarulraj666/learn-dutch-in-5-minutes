from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from psycopg.types.json import Jsonb

import db
from auth import CurrentUser
from models import QuizAnswerResult, QuizResult, QuizSubmission

router = APIRouter()


@router.post("/lessons/{lesson_id}/quiz/submit", response_model=QuizResult)
async def submit_quiz(lesson_id: str, payload: QuizSubmission, user: CurrentUser) -> QuizResult:
    """Grade server-side. Correct answers never leave the backend before grading."""
    questions = await db.fetch_all(
        "SELECT id, answer, explanation FROM quiz_questions WHERE lesson_id = %s ORDER BY order_index",
        (lesson_id,),
    )
    if not questions:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This lesson has no quiz")

    unknown = set(payload.answers) - {q["id"] for q in questions}
    if unknown:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown question id submitted")

    results: list[QuizAnswerResult] = []
    score = 0
    for question in questions:
        given = payload.answers.get(question["id"], "")
        correct = given == question["answer"]
        score += correct
        results.append(QuizAnswerResult(
            id=question["id"],
            correct=correct,
            given=given,
            answer=question["answer"],
            explanation=question["explanation"],
        ))

    total = len(questions)
    row = await db.fetch_one(
        """
        INSERT INTO quiz_attempts (user_id, lesson_id, attempt_no, score, total, answers)
        SELECT %s, %s,
               COALESCE(max(attempt_no), 0) + 1, %s, %s, %s
        FROM quiz_attempts WHERE user_id = %s AND lesson_id = %s
        RETURNING attempt_no
        """,
        (user["id"], lesson_id, score, total, Jsonb(payload.answers), user["id"], lesson_id),
    )

    return QuizResult(
        lesson_id=lesson_id,
        score=score,
        total=total,
        percent=round(score * 100 / total),
        attempt_no=row["attempt_no"],
        results=results,
    )


@router.get("/lessons/{lesson_id}/quiz/attempts")
async def list_attempts(lesson_id: str, user: CurrentUser) -> list[dict]:
    return await db.fetch_all(
        """
        SELECT attempt_no, score, total, created_at
        FROM quiz_attempts
        WHERE user_id = %s AND lesson_id = %s
        ORDER BY attempt_no DESC
        LIMIT 20
        """,
        (user["id"], lesson_id),
    )
