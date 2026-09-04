from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from psycopg.types.json import Jsonb

import db
from auth import AdminUser, CurrentUser
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
from speaking_feedback import SpeakingFeedbackError, evaluate_speaking_recording

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
async def serve_mock_exam_image(_: CurrentUser, path: str):
    p = _safe_media_path(path)
    media_type = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(
        p.suffix.lower(), "image/png"
    )
    return FileResponse(p, media_type=media_type)


@router.get("/mock-exams/media/audio")
async def serve_mock_exam_audio(_: CurrentUser, path: str):
    p = _safe_media_path(path)
    media_type = {".mp3": "audio/mpeg", ".ogg": "audio/ogg", ".wav": "audio/wav"}.get(
        p.suffix.lower(), "application/octet-stream"
    )
    return FileResponse(p, media_type=media_type)


@router.get("/mock-exams/media/video")
async def serve_mock_exam_video(_: CurrentUser, path: str):
    p = _safe_media_path(path)
    return FileResponse(p, media_type="video/mp4")


@router.post("/mock-exams/{exam_id}/recordings")
async def upload_speaking_recording(
    exam_id: str,
    user: CurrentUser,
    question_id: str = Form(...),
    recording: UploadFile = File(...),
):
    question = await db.fetch_one(
        "SELECT id FROM mock_exam_questions WHERE id = %s AND exam_id = %s AND question_type = 'open_spoken'",
        (question_id, exam_id),
    )
    if not question:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Speaking question not found")
    suffix = Path(recording.filename or "recording.webm").suffix.lower() or ".webm"
    if suffix not in {".webm", ".ogg", ".wav", ".mp3", ".m4a"}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unsupported recording format")
    recording_dir = ROOT / "private_recordings" / str(user["id"]) / exam_id
    recording_dir.mkdir(parents=True, exist_ok=True)
    path = recording_dir / f"{question_id}-{uuid4()}{suffix}"
    path.write_bytes(await recording.read())
    await db.execute(
        "INSERT INTO mock_exam_speaking_recordings (id, user_id, exam_id, question_id, storage_path) VALUES (%s, %s, %s, %s, %s)",
        (uuid4(), user["id"], exam_id, question_id, str(path)),
    )
    return {"question_id": question_id}


@router.get("/mock-exams/{exam_id}/attempts/{attempt_no}/recordings/{question_id}")
async def serve_speaking_recording(exam_id: str, attempt_no: int, question_id: str, user: CurrentUser):
    recording = await db.fetch_one(
        "SELECT recording.storage_path FROM mock_exam_speaking_recordings recording "
        "JOIN mock_exam_attempts attempt ON attempt.id = recording.attempt_id "
        "WHERE recording.user_id = %s AND recording.exam_id = %s AND recording.question_id = %s "
        "AND attempt.attempt_no = %s",
        (user["id"], exam_id, question_id, attempt_no),
    )
    if not recording:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Speaking recording not found")
    path = Path(recording["storage_path"])
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Speaking recording file not found")
    media_type = {".webm": "audio/webm", ".ogg": "audio/ogg", ".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4"}.get(
        path.suffix.lower(), "application/octet-stream"
    )
    return FileResponse(path, media_type=media_type)



@router.get("/mock-exams", response_model=list[MockExamSummary])
async def list_mock_exams(_: CurrentUser, section: str | None = None) -> list[MockExamSummary]:
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
        "SELECT id, order_index, part_number, passage_type, title, display_prompt_nl, scene_description, content_nl, content_en, "
        "media_urls, image_prompt FROM mock_exam_passages WHERE exam_id = %s ORDER BY order_index",
        (exam_id,),
    )
    questions = await db.fetch_all(
        "SELECT id, passage_id, part_number, order_index, question_text, question_audio_url, "
        "question_options_audio_url, option_audio_cues, question_type, options, "
        "answer, explanation, category, max_score, grading_rubric, model_answer, year_asked, "
        "option_image_prompts, option_audio_urls, option_media_urls "
        "FROM mock_exam_questions WHERE exam_id = %s ORDER BY order_index",
        (exam_id,),
    )

    return MockExamDetailAdmin(
        **exam,
        passages=[MockExamPassageAdmin(**p) for p in passages],
        questions=[MockExamQuestionAdmin(**q) for q in questions],
    )


@router.get("/mock-exams/{exam_id}/take", response_model=MockExamTakeDetail)
async def take_mock_exam(exam_id: str, _: CurrentUser) -> MockExamTakeDetail:
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
        "SELECT id, order_index, part_number, passage_type, title, display_prompt_nl, content_nl, content_en, media_urls "
        "FROM mock_exam_passages WHERE exam_id = %s ORDER BY order_index",
        (exam_id,),
    )
    questions = await db.fetch_all(
        "SELECT id, passage_id, part_number, order_index, question_text, question_audio_url, "
        "question_options_audio_url, option_audio_cues, question_type, options, category, "
        "option_audio_urls, option_media_urls "
        "FROM mock_exam_questions WHERE exam_id = %s ORDER BY order_index",
        (exam_id,),
    )
    public_passages = []
    for passage in passages:
        public_passage = dict(passage)
        if exam["section"] == "listening":
            public_passage["content_nl"] = ""
        if public_passage["passage_type"] == "video":
            public_passage["content_nl"] = ""
            public_passage["content_en"] = None
        public_passages.append(MockExamPassagePublic(**public_passage))

    return MockExamTakeDetail(
        **exam,
        passages=public_passages,
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


async def _process_speaking_attempt(attempt_id: int) -> None:
    attempt = await db.fetch_one("SELECT user_id, exam_id, answers FROM mock_exam_attempts WHERE id = %s", (attempt_id,))
    if not attempt:
        return
    questions = await db.fetch_all(
        "SELECT id, question_text, grading_rubric, model_answer FROM mock_exam_questions WHERE exam_id = %s ORDER BY order_index",
        (attempt["exam_id"],),
    )
    recordings = await db.fetch_all(
        "SELECT question_id, storage_path FROM mock_exam_speaking_recordings WHERE attempt_id = %s",
        (attempt_id,),
    )
    recording_by_question = {recording["question_id"]: recording for recording in recordings}
    feedback_by_id = {}
    score = 0
    try:
        for question in questions:
            recording = recording_by_question.get(question["id"])
            if not recording:
                continue
            try:
                feedback = await evaluate_speaking_recording(
                    Path(recording["storage_path"]), question["question_text"],
                    question["grading_rubric"] or [], question["model_answer"] or "",
                )
            except Exception:
                feedback = {
                    "label": "Improvement needed",
                    "spoken_text": "",
                    "feedback": "This recording could not be assessed.",
                    "possible_answer": question["model_answer"] or "",
                }
            await db.execute(
                "UPDATE mock_exam_speaking_recordings SET feedback_label = %s WHERE attempt_id = %s AND question_id = %s",
                (feedback["label"], attempt_id, question["id"]),
            )
            feedback_by_id[question["id"]] = feedback
            Path(recording["storage_path"]).unlink(missing_ok=True)
            await db.execute(
                "DELETE FROM mock_exam_speaking_recordings WHERE attempt_id = %s AND question_id = %s",
                (attempt_id, question["id"]),
            )
            score += {"Excellent": 2, "Good": 1}.get(feedback["label"], 1)

        total = len(questions) * 2
        percent = round(score * 100 / total) if total else 0
        label = _score_label(percent, percent >= 60)
        answers = dict(attempt["answers"])
        answers["__speaking_feedback"] = feedback_by_id
        await db.execute(
            "UPDATE mock_exam_attempts SET score = %s, total = %s, percent = %s, label = %s, status = 'completed', answers = %s WHERE id = %s",
            (score, total, percent, label, Jsonb(answers), attempt_id),
        )
    except Exception:
        await db.execute(
            "UPDATE mock_exam_attempts SET status = 'failed', label = 'Feedback unavailable' WHERE id = %s",
            (attempt_id,),
        )


@router.post("/mock-exams/{exam_id}/submit", response_model=MockExamAttemptResult)
async def submit_mock_exam(exam_id: str, payload: MockExamSubmission, user: CurrentUser, background_tasks: BackgroundTasks) -> MockExamAttemptResult:
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
    elif exam_section == "speaking":
        questions = await db.fetch_all(
            "SELECT id, question_type, question_text, grading_rubric, model_answer FROM mock_exam_questions "
            "WHERE exam_id = %s ORDER BY order_index",
            (exam_id,),
        )
        score, gradable = 0, len(questions) * 2
        results = []
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
    elif exam_section == "speaking":
        label = "Processing feedback"
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
         INSERT INTO mock_exam_attempts (user_id, exam_id, attempt_no, score, total, percent, label, status, answers)
        SELECT %s, %s,
             COALESCE(max(attempt_no), 0) + 1, %s, %s, %s, %s, %s, %s
        FROM mock_exam_attempts WHERE user_id = %s AND exam_id = %s
        RETURNING id, attempt_no, created_at
        """,
         (user["id"], exam_id, score, gradable, percent, label, "processing" if exam_section == "speaking" else "completed", Jsonb(stored_answers),
         user["id"], exam_id),
    )

    if exam_section == "speaking":
        await db.execute(
            "UPDATE mock_exam_speaking_recordings SET attempt_id = %s "
            "WHERE user_id = %s AND exam_id = %s AND attempt_id IS NULL",
            (row["id"], user["id"], exam_id),
        )
        background_tasks.add_task(_process_speaking_attempt, row["id"])

    return MockExamAttemptResult(
        exam_id=exam_id,
        attempt_no=row["attempt_no"],
        score=score,
        total=gradable,
        percent=percent,
        label=label,
        status="processing" if exam_section == "speaking" else "completed",
        created_at=row["created_at"],
        results=results,
    )


def _speaking_results_from_feedback(questions: list[dict], answers: dict[str, Any]) -> list[MockExamQuestionResult]:
    feedback_by_id = answers.get("__speaking_feedback", {})
    if not isinstance(feedback_by_id, dict):
        feedback_by_id = {}
    results = []
    for question in questions:
        stored_feedback = feedback_by_id.get(question["id"])
        feedback = None
        if isinstance(stored_feedback, dict):
            feedback = {
                "label": str(stored_feedback.get("label", "Improvement needed")),
                "spoken_text": str(stored_feedback.get("spoken_text", "")),
                "feedback": str(stored_feedback.get("feedback", "")),
                "possible_answer": str(stored_feedback.get("possible_answer", "")),
            }
        results.append(MockExamQuestionResult(
            id=question["id"], question_type=question["question_type"],
            graded=feedback is not None, given="audio-recording" if feedback else None,
            speaking_feedback=feedback,
        ))
    return results


@router.get("/mock-exams/{exam_id}/attempts", response_model=list[MockExamAttemptSummary])
async def list_mock_exam_attempts(exam_id: str, user: CurrentUser) -> list[MockExamAttemptSummary]:
    rows = await db.fetch_all(
        """
        SELECT attempt_no, score, total, percent, label, status, created_at
        FROM mock_exam_attempts
        WHERE user_id = %s AND exam_id = %s
        ORDER BY attempt_no DESC
        """,
        (user["id"], exam_id),
    )
    return [MockExamAttemptSummary(**row) for row in rows]


@router.get("/mock-exams/{exam_id}/attempts/{attempt_no}", response_model=MockExamAttemptResult)
async def get_mock_exam_attempt(exam_id: str, attempt_no: int, user: CurrentUser) -> MockExamAttemptResult:
    attempt = await db.fetch_one(
        """
        SELECT score, total, percent, label, status, answers, created_at
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
    elif exam_section == "speaking":
        questions = await db.fetch_all(
            "SELECT id, question_type FROM mock_exam_questions WHERE exam_id = %s ORDER BY order_index",
            (exam_id,),
        )
        results = _speaking_results_from_feedback(questions, attempt["answers"])
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
        status=attempt["status"],
        created_at=attempt["created_at"],
        results=results,
    )
