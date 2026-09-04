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


class FeedbackSubmission(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = Field(min_length=1, max_length=2000)


class FeedbackPublic(BaseModel):
    id: int
    name: str
    rating: int
    comment: str
    created_at: datetime


class PublicStats(BaseModel):
    active_learners: int


class AdminFeedback(BaseModel):
    id: int
    user_id: str | None
    name: str | None
    email: str | None
    rating: int
    comment: str
    status: str
    created_at: datetime
    published_at: datetime | None


class MockExamSummary(BaseModel):
    id: str
    section: str
    level: str
    exam_number: int
    title: str
    time_limit_minutes: int
    total_questions: int
    parts_count: int
    pass_threshold: int | None
    max_score: int | None
    status: str


class MockExamPassageAdmin(BaseModel):
    id: str
    order_index: int
    part_number: int | None
    passage_type: str
    title: str
    display_prompt_nl: str = ""
    scene_description: str = ""
    content_nl: str
    content_en: str | None
    media_urls: list[dict[str, Any]]
    image_prompt: Any | None = None


class MockExamQuestionAdmin(BaseModel):
    """Admin-only view — includes the answer, rubric and model answer."""
    id: str
    passage_id: str | None
    part_number: int | None
    order_index: int
    question_text: str
    question_audio_url: str | None = None
    question_options_audio_url: str | None = None
    option_audio_cues: list[dict[str, Any]] | None = None
    question_type: str
    options: list[str] | None
    answer: str | None
    explanation: str
    category: str | None
    max_score: int
    grading_rubric: list[dict[str, Any]] | None
    model_answer: str | None
    year_asked: int | None
    option_image_prompts: list[str] | None = None
    option_audio_urls: list[str | None] | None = None
    option_media_urls: list[str | None] | None = None


class MockExamDetailAdmin(MockExamSummary):
    instructions: str
    passages: list[MockExamPassageAdmin]
    questions: list[MockExamQuestionAdmin]


class MockExamPassagePublic(BaseModel):
    """Learner-facing passage view — media only, no answer-key metadata."""
    id: str
    order_index: int
    part_number: int | None
    passage_type: str
    title: str
    display_prompt_nl: str = ""
    content_nl: str
    content_en: str | None
    media_urls: list[dict[str, Any]]


class MockExamQuestionPublic(BaseModel):
    """Learner-facing question view — never carries the answer."""
    id: str
    passage_id: str | None
    part_number: int | None
    order_index: int
    question_text: str
    question_audio_url: str | None = None
    question_options_audio_url: str | None = None
    option_audio_cues: list[dict[str, Any]] | None = None
    question_type: str
    options: list[str] | None
    category: str | None = None
    option_audio_urls: list[str | None] | None = None
    option_media_urls: list[str | None] | None = None


class MockExamTakeDetail(MockExamSummary):
    instructions: str
    passages: list[MockExamPassagePublic]
    questions: list[MockExamQuestionPublic]


class MockExamSubmission(BaseModel):
    answers: dict[str, str] = Field(default_factory=dict)


class WritingFeedback(BaseModel):
    score: int
    max_score: int
    feedback: str
    possible_answer: str = ""
    criterion_scores: list[dict[str, Any]] = []


class SpeakingFeedback(BaseModel):
    label: str
    spoken_text: str
    feedback: str
    possible_answer: str


class MockExamQuestionResult(BaseModel):
    id: str
    question_type: str
    graded: bool
    correct: bool | None = None
    given: str | None = None
    answer: str | None = None
    explanation: str | None = None
    writing_feedback: WritingFeedback | None = None
    speaking_feedback: SpeakingFeedback | None = None


class MockExamAttemptResult(BaseModel):
    exam_id: str
    attempt_no: int
    score: int
    total: int
    percent: int
    label: str
    status: str = "completed"
    created_at: datetime
    results: list[MockExamQuestionResult]


class MockExamAttemptSummary(BaseModel):
    attempt_no: int
    score: int
    total: int
    percent: int
    label: str
    status: str = "completed"
    created_at: datetime
