from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CourseSummary(BaseModel):
    id: str
    title: str
    subtitle: str
    description: str
    status: str
    # Counts cover required modules only; optional add-ons are reported separately.
    lesson_count: int = 0
    completed_count: int = 0
    optional_lesson_count: int = 0
    optional_completed_count: int = 0
    module_count: int = 0


class LessonSummary(BaseModel):
    id: str
    title: str
    title_nl: str
    title_en: str = ""
    summary: str
    duration_sec: int | None = None
    order_index: int
    is_premium: bool
    completed: bool = False
    percent: int = 0
    best_quiz_percent: int | None = None


class ModuleDetail(BaseModel):
    id: str
    category: str
    title: str
    description: str
    order_index: int
    is_optional: bool = False
    lessons: list[LessonSummary]


class CourseDetail(CourseSummary):
    modules: list[ModuleDetail]
    next_lesson_id: str | None = None


class VocabularyItem(BaseModel):
    id: int
    nl: str
    en: str


class GrammarNote(BaseModel):
    title: str
    explanation: str
    examples: list[str]


class TranscriptLine(BaseModel):
    speaker: str
    line_nl: str
    line_en: str


class QuizQuestionPublic(BaseModel):
    """Quiz question as sent to the browser — never carries the answer."""
    id: str
    question: str
    options: list[str]
    difficulty: str
    skill: str


class LessonProgress(BaseModel):
    watched_sec: int = 0
    last_position_sec: int = 0
    percent: int = 0
    completed_at: datetime | None = None


class LessonDetail(BaseModel):
    id: str
    course_id: str
    module_id: str
    category: str
    title: str
    title_nl: str
    title_en: str = ""
    summary: str
    description: str
    youtube_video_id: str
    duration_sec: int | None = None
    is_premium: bool
    key_phrases: list[str]
    vocabulary: list[VocabularyItem]
    grammar_notes: list[GrammarNote]
    transcript: list[TranscriptLine]
    subtitle_langs: list[str]
    quiz: list[QuizQuestionPublic]
    progress: LessonProgress | None = None
    prev_lesson_id: str | None = None
    next_lesson_id: str | None = None


class ProgressUpdate(BaseModel):
    lesson_id: str
    position_sec: int = Field(ge=0, le=86400)
    watched_sec: int = Field(ge=0, le=86400)
    duration_sec: int | None = Field(default=None, ge=1, le=86400)


class ProgressResult(BaseModel):
    lesson_id: str
    percent: int
    completed: bool


class QuizSubmission(BaseModel):
    answers: dict[str, str] = Field(min_length=1, max_length=50)


class QuizAnswerResult(BaseModel):
    id: str
    correct: bool
    given: str
    answer: str
    explanation: str


class QuizResult(BaseModel):
    lesson_id: str
    score: int
    total: int
    percent: int
    attempt_no: int
    results: list[QuizAnswerResult]


class FlashcardDue(BaseModel):
    vocab_id: int
    nl: str
    en: str
    lesson_id: str
    lesson_title: str
    reps: int = 0


class FlashcardReview(BaseModel):
    vocab_id: int
    quality: int = Field(ge=0, le=5, description="SM-2 recall quality: 0=again … 5=perfect")


class FlashcardState(BaseModel):
    vocab_id: int
    ease: float
    interval_days: int
    reps: int
    due_at: datetime


class Certificate(BaseModel):
    serial: str
    course_id: str
    course_title: str
    user_name: str
    issued_at: datetime


class CertificateEligibility(BaseModel):
    course_id: str
    eligible: bool
    lessons_total: int
    lessons_completed: int
    quizzes_total: int
    quizzes_passed: int
    pass_percent: int
    certificate: Certificate | None = None


class UserSettings(BaseModel):
    locale: str = Field(default="en", max_length=10)
    email_opt_in: bool = False


class UserProfile(BaseModel):
    id: str
    email: str | None
    name: str | None
    image: str | None
    plan: str
    role: str
    settings: UserSettings


class DashboardCourse(BaseModel):
    course_id: str
    title: str
    lessons_total: int
    lessons_completed: int
    percent: int
    optional_total: int = 0
    optional_completed: int = 0
    resume_lesson_id: str | None = None
    resume_lesson_title: str | None = None


class Dashboard(BaseModel):
    courses: list[DashboardCourse]
    flashcards_due: int
    recent: list[dict[str, Any]]


class AdminLearner(BaseModel):
    id: str
    email: str | None
    name: str | None
    created_at: datetime
    lessons_completed: int
    quiz_attempts: int
    last_active: datetime | None = None
