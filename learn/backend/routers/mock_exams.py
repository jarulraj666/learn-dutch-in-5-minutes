from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from psycopg.types.json import Jsonb

import db
from auth import AdminUser
from models import (
    MockExamAttemptResult,
    MockExamAttemptSummary,
    MockExamDetailAdmin,
    MockExamPassageAdmin,
    MockExamPassagePublic,
    MockExamQuestionAdmin,
    MockExamQuestionPublic,
    MockExamQuestionResult,
    MockExamSubmission,
    MockExamSummary,
    MockExamTakeDetail,
)
from writing_feedback import WritingFeedbackError, grade_writing_answers

ROOT = Path(__file__).resolve().parent.parent.parent.parent

router = APIRouter()
WRITING_STUDY_TARGET = 25


def _safe_media_path(rel_path: str) -> Path:
    """Resolve a relative media path, rejecting anything outside output/mock_exams."""
    media_root = (ROOT / "output" / "mock_exams").resolve()
    p = (ROOT / rel_path).resolve()
    if not str(p).startswith(str(media_root)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access denied")
    if not p.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    return p


@router.get("/mock-exams/media/image")
async def serve_mock_exam_image(_: AdminUser, path: str):
    p = _safe_media_path(path)
    media_type = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(
        p.suffix.lower(), "image/png"
    )
    return FileResponse(p, media_type=media_type)


@router.get("/mock-exams/media/audio")
async def serve_mock_exam_audio(_: AdminUser, path: str):
    p = _safe_media_path(path)
    return FileResponse(p, media_type="audio/wav")


@router.get("/mock-exams/media/video")
async def serve_mock_exam_video(_: AdminUser, path: str):
    p = _safe_media_path(path)
    return FileResponse(p, media_type="video/mp4")



@router.get("/mock-exams", response_model=list[MockExamSummary])
async def list_mock_exams(_: AdminUser, section: str | None = None) -> list[MockExamSummary]:
    query = (
        "SELECT id, section, level, exam_number, title, time_limit_minutes, total_questions, "
        "parts_count, pass_threshold, max_score, status FROM mock_exams"
    )
    params: tuple = ()
    if section:
        query += " WHERE section = %s"
        params = (section,)
    query += " ORDER BY section, exam_number"

    rows = await db.fetch_all(query, params)
    return [MockExamSummary(**row) for row in rows]


@router.get("/mock-exams/{exam_id}", response_model=MockExamDetailAdmin)
async def get_mock_exam(exam_id: str, _: AdminUser) -> MockExamDetailAdmin:
    exam = await db.fetch_one(
        "SELECT id, section, level, exam_number, title, instructions, time_limit_minutes, "
        "total_questions, parts_count, pass_threshold, max_score, status "
        "FROM mock_exams WHERE id = %s",
        (exam_id,),
    )
    if not exam:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mock exam not found")

    passages = await db.fetch_all(
        "SELECT id, order_index, part_number, passage_type, title, content_nl, content_en, "
        "media_urls, image_prompt FROM mock_exam_passages WHERE exam_id = %s ORDER BY order_index",
        (exam_id,),
    )
    questions = await db.fetch_all(
        "SELECT id, passage_id, part_number, order_index, question_text, question_type, options, "
        "answer, explanation, category, max_score, grading_rubric, model_answer, year_asked, "
        "option_image_prompts, option_media_urls "
        "FROM mock_exam_questions WHERE exam_id = %s ORDER BY order_index",
        (exam_id,),
    )

    return MockExamDetailAdmin(
        **exam,
        passages=[MockExamPassageAdmin(**p) for p in passages],
        questions=[MockExamQuestionAdmin(**q) for q in questions],
    )


@router.get("/mock-exams/{exam_id}/take", response_model=MockExamTakeDetail)
async def take_mock_exam(exam_id: str, _: AdminUser) -> MockExamTakeDetail:
    """Learner-facing exam view: never includes answers, explanations or rubrics."""
    exam = await db.fetch_one(
        "SELECT id, section, level, exam_number, title, instructions, time_limit_minutes, "
        "total_questions, parts_count, pass_threshold, max_score, status "
        "FROM mock_exams WHERE id = %s",
        (exam_id,),
    )
    if not exam:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mock exam not found")

    passages = await db.fetch_all(
        "SELECT id, order_index, part_number, passage_type, title, content_nl, content_en, media_urls "
        "FROM mock_exam_passages WHERE exam_id = %s ORDER BY order_index",
        (exam_id,),
    )
    questions = await db.fetch_all(
        "SELECT id, passage_id, part_number, order_index, question_text, question_type, options, "
        "option_media_urls "
        "FROM mock_exam_questions WHERE exam_id = %s ORDER BY order_index",
        (exam_id,),
    )

    return MockExamTakeDetail(
        **exam,
        passages=[MockExamPassagePublic(**p) for p in passages],
        questions=[MockExamQuestionPublic(**q) for q in questions],
    )


def _score_label(percent: int, passed: bool) -> str:
    if percent >= 90:
        return "Excellent!"
    if percent >= 75:
        return "Good job!"
    if passed:
        return "You passed"
    return "Needs improvement"


def _writing_score_label(score: int) -> str:
    return "Study target reached" if score >= WRITING_STUDY_TARGET else "Keep practising"


def _grade(questions: list[dict], answers: dict[str, str]) -> tuple[int, int, list[MockExamQuestionResult]]:
    """Grade multiple_choice questions against submitted answers.

    Only multiple_choice questions are auto-graded; open_written/open_spoken answers
    (writing/speaking) are recorded as ungraded until LLM grading ships.
    """
    results: list[MockExamQuestionResult] = []
    score = 0
    gradable = 0
    for q in questions:
        given = answers.get(q["id"])
        if q["question_type"] == "multiple_choice":
            gradable += 1
            correct = given == q["answer"]
            score += int(correct)
            results.append(MockExamQuestionResult(
                id=q["id"], question_type=q["question_type"], graded=True,
                correct=correct, given=given, answer=q["answer"], explanation=q["explanation"],
            ))
        else:
            results.append(MockExamQuestionResult(
                id=q["id"], question_type=q["question_type"], graded=False, given=given,
            ))
    return score, gradable, results


def _writing_task_score(feedback: dict, rubric: list[dict], max_score: int) -> tuple[int, list[dict]]:
    """Normalize criterion scores and apply the adequacy gate before totaling."""
    raw_scores = feedback.get("criterion_scores")
    if not isinstance(raw_scores, list):
        return 0, []

    scores_by_criterion = {
        str(item.get("criterion", "")).strip().lower(): item.get("score", 0)
        for item in raw_scores
        if isinstance(item, dict)
    }
    normalized = []
    for item in rubric:
        criterion = str(item.get("criterion", "")).strip()
        maximum = max(0, int(item.get("max_points") or 0))
        try:
            awarded = int(scores_by_criterion.get(criterion.lower(), 0))
        except (TypeError, ValueError):
            awarded = 0
        normalized.append({"criterion": criterion, "score": min(max(awarded, 0), maximum)})

    adequacy = next((item["score"] for item in normalized if item["criterion"] == "adequacy_understandability"), None)
    if adequacy == 0:
        return 0, [{"criterion": item["criterion"], "score": 0} for item in normalized]
    return min(sum(item["score"] for item in normalized), max_score), normalized


async def _grade_writing(questions: list[dict], answers: dict[str, str]) -> tuple[int, int, list[MockExamQuestionResult]]:
    tasks = []
    for question in questions:
        answer = answers.get(question["id"], "").strip()
        if not answer:
            continue
        tasks.append({
            "id": question["id"],
            "source_text": question["content_nl"],
            "question_text": question["question_text"],
            "learner_answer": answer,
            "rubric": question["grading_rubric"] or [],
            "model_answer": question["model_answer"] or "",
            "max_score": question["max_score"],
        })

    if not tasks:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Write an answer for at least one task before submitting")

    try:
        feedback_by_id = await grade_writing_answers(tasks)
    except WritingFeedbackError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Writing feedback is temporarily unavailable") from exc

    score = 0
    total = sum(int(question["max_score"]) for question in questions)
    results = []
    for question in questions:
        answer = answers.get(question["id"], "").strip()
        feedback = feedback_by_id.get(question["id"])
        if feedback:
            task_score, criterion_scores = _writing_task_score(
                feedback, question["grading_rubric"] or [], int(question["max_score"])
            )
            score += task_score
            results.append(MockExamQuestionResult(
                id=question["id"], question_type=question["question_type"], graded=True, given=answer,
                writing_feedback={
                    "score": task_score,
                    "max_score": question["max_score"],
                    "feedback": str(feedback.get("feedback", "")),
                    "possible_answer": str(feedback.get("possible_answer", "")),
                    "criterion_scores": criterion_scores,
                },
            ))
        else:
            results.append(MockExamQuestionResult(
                id=question["id"], question_type=question["question_type"], graded=False, given=answer,
            ))
    return score, total, results


def _writing_results_from_feedback(questions: list[dict], answers: dict[str, str]) -> list[MockExamQuestionResult]:
    feedback_by_id = answers.get("__writing_feedback", {})
    if not isinstance(feedback_by_id, dict):
        feedback_by_id = {}
    results = []
    for question in questions:
        feedback = feedback_by_id.get(question["id"])
        answer = answers.get(question["id"], "").strip()
        if isinstance(feedback, dict):
            results.append(MockExamQuestionResult(
                id=question["id"], question_type=question["question_type"], graded=True, given=answer,
                writing_feedback=feedback,
            ))
        else:
            results.append(MockExamQuestionResult(
                id=question["id"], question_type=question["question_type"], graded=False, given=answer,
            ))
    return results


@router.post("/mock-exams/{exam_id}/submit", response_model=MockExamAttemptResult)
async def submit_mock_exam(exam_id: str, payload: MockExamSubmission, user: AdminUser) -> MockExamAttemptResult:
    """Grade server-side (so the answer key never reaches the browser before submission)
    and persist the attempt so the learner can review it later."""
    exam = await db.fetch_one(
        "SELECT pass_threshold, max_score FROM mock_exams WHERE id = %s", (exam_id,)
    )
    if not exam:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mock exam not found")

    exam_section = (await db.fetch_one("SELECT section FROM mock_exams WHERE id = %s", (exam_id,)))["section"]
    if exam_section == "writing":
        questions = await db.fetch_all(
            "SELECT q.id, q.question_type, q.question_text, q.grading_rubric, q.model_answer, q.max_score, "
            "p.content_nl FROM mock_exam_questions q LEFT JOIN mock_exam_passages p ON p.id = q.passage_id "
            "WHERE q.exam_id = %s ORDER BY q.order_index",
            (exam_id,),
        )
        score, gradable, results = await _grade_writing(questions, payload.answers)
    else:
        questions = await db.fetch_all(
            "SELECT id, question_type, answer, explanation FROM mock_exam_questions "
            "WHERE exam_id = %s ORDER BY order_index",
            (exam_id,),
        )
        score, gradable, results = _grade(questions, payload.answers)
    percent = round(score * 100 / gradable) if gradable else 0
    pass_threshold = exam["pass_threshold"]
    if exam_section == "writing":
        label = _writing_score_label(score)
    else:
        passed = score >= pass_threshold if pass_threshold is not None else percent >= 60
        label = _score_label(percent, passed)

    stored_answers = dict(payload.answers)
    if exam_section == "writing":
        stored_answers["__writing_feedback"] = {
            result.id: result.writing_feedback.model_dump()
            for result in results
            if result.writing_feedback is not None
        }

    row = await db.fetch_one(
        """
        INSERT INTO mock_exam_attempts (user_id, exam_id, attempt_no, score, total, percent, label, answers)
        SELECT %s, %s,
               COALESCE(max(attempt_no), 0) + 1, %s, %s, %s, %s, %s
        FROM mock_exam_attempts WHERE user_id = %s AND exam_id = %s
        RETURNING attempt_no, created_at
        """,
        (user["id"], exam_id, score, gradable, percent, label, Jsonb(stored_answers),
         user["id"], exam_id),
    )

    return MockExamAttemptResult(
        exam_id=exam_id,
        attempt_no=row["attempt_no"],
        score=score,
        total=gradable,
        percent=percent,
        label=label,
        created_at=row["created_at"],
        results=results,
    )


@router.get("/mock-exams/{exam_id}/attempts", response_model=list[MockExamAttemptSummary])
async def list_mock_exam_attempts(exam_id: str, user: AdminUser) -> list[MockExamAttemptSummary]:
    rows = await db.fetch_all(
        """
        SELECT attempt_no, score, total, percent, label, created_at
        FROM mock_exam_attempts
        WHERE user_id = %s AND exam_id = %s
        ORDER BY attempt_no DESC
        """,
        (user["id"], exam_id),
    )
    return [MockExamAttemptSummary(**row) for row in rows]


@router.get("/mock-exams/{exam_id}/attempts/{attempt_no}", response_model=MockExamAttemptResult)
async def get_mock_exam_attempt(exam_id: str, attempt_no: int, user: AdminUser) -> MockExamAttemptResult:
    attempt = await db.fetch_one(
        """
        SELECT score, total, percent, label, answers, created_at
        FROM mock_exam_attempts
        WHERE user_id = %s AND exam_id = %s AND attempt_no = %s
        """,
        (user["id"], exam_id, attempt_no),
    )
    if not attempt:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attempt not found")

    exam_section = (await db.fetch_one("SELECT section FROM mock_exams WHERE id = %s", (exam_id,)))["section"]
    if exam_section == "writing":
        questions = await db.fetch_all(
            "SELECT id, question_type FROM mock_exam_questions WHERE exam_id = %s ORDER BY order_index",
            (exam_id,),
        )
        results = _writing_results_from_feedback(questions, attempt["answers"])
    else:
        questions = await db.fetch_all(
            "SELECT id, question_type, answer, explanation FROM mock_exam_questions "
            "WHERE exam_id = %s ORDER BY order_index",
            (exam_id,),
        )
        _, _, results = _grade(questions, attempt["answers"])

    return MockExamAttemptResult(
        exam_id=exam_id,
        attempt_no=attempt_no,
        score=attempt["score"],
        total=attempt["total"],
        percent=attempt["percent"],
        label=attempt["label"],
        created_at=attempt["created_at"],
        results=results,
    )
