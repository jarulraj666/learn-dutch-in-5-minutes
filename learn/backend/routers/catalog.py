from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

import db
from auth import OptionalUser
from models import (
    CourseDetail,
    CourseSummary,
    GrammarNote,
    LessonDetail,
    LessonProgress,
    LessonSummary,
    ModuleDetail,
    QuizQuestionPublic,
    TranscriptLine,
    VocabularyItem,
)

router = APIRouter()


@router.get("/courses", response_model=list[CourseSummary])
async def list_courses(user: OptionalUser) -> list[CourseSummary]:
    rows = await db.fetch_all(
        """
        SELECT c.id, c.title, c.subtitle, c.description, c.status,
               count(l.id) FILTER (WHERE NOT m.is_optional) AS lesson_count,
               count(p.lesson_id) FILTER (WHERE NOT m.is_optional AND p.completed_at IS NOT NULL)
                   AS completed_count,
               count(l.id) FILTER (WHERE m.is_optional) AS optional_lesson_count,
               count(p.lesson_id) FILTER (WHERE m.is_optional AND p.completed_at IS NOT NULL)
                   AS optional_completed_count,
               count(DISTINCT m.id) FILTER (WHERE NOT m.is_optional) AS module_count
        FROM courses c
        LEFT JOIN lessons l ON l.course_id = c.id
        LEFT JOIN modules m ON m.id = l.module_id
        LEFT JOIN lesson_progress p ON p.lesson_id = l.id AND p.user_id = %s
        GROUP BY c.id
        ORDER BY c.order_index, c.id
        """,
        (user["id"] if user else None,),
    )
    return [CourseSummary(**row) for row in rows]


@router.get("/courses/{course_id}", response_model=CourseDetail)
async def get_course(course_id: str, user: OptionalUser) -> CourseDetail:
    course = await db.fetch_one(
        "SELECT id, title, subtitle, description, status FROM courses WHERE id = %s",
        (course_id,),
    )
    if not course:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Course not found")

    user_id = user["id"] if user else None
    module_rows = await db.fetch_all(
        """
        SELECT id, category, title, description, order_index, is_optional
        FROM modules WHERE course_id = %s ORDER BY is_optional, order_index
        """,
        (course_id,),
    )
    lesson_rows = await db.fetch_all(
        """
        SELECT l.id, l.module_id, l.title, l.title_nl, l.title_en, l.summary, l.duration_sec,
               l.order_index, l.is_premium,
               COALESCE(p.percent, 0) AS percent,
               (p.completed_at IS NOT NULL) AS completed,
               (
                 SELECT max(round(a.score * 100.0 / NULLIF(a.total, 0)))
                 FROM quiz_attempts a
                 WHERE a.lesson_id = l.id AND a.user_id = %s
               ) AS best_quiz_percent
        FROM lessons l
        LEFT JOIN lesson_progress p ON p.lesson_id = l.id AND p.user_id = %s
        WHERE l.course_id = %s
        ORDER BY l.order_index, l.id
        """,
        (user_id, user_id, course_id),
    )

    by_module: dict[str, list[LessonSummary]] = {}
    for row in lesson_rows:
        module_id = row.pop("module_id")
        row["best_quiz_percent"] = int(row["best_quiz_percent"]) if row["best_quiz_percent"] is not None else None
        by_module.setdefault(module_id, []).append(LessonSummary(**row))

    modules = [
        ModuleDetail(**module, lessons=by_module.get(module["id"], []))
        for module in module_rows
    ]
    # Units with nothing published yet would render as empty sections.
    modules = [module for module in modules if module.lessons]

    required = [lesson for m in modules if not m.is_optional for lesson in m.lessons]
    optional = [lesson for m in modules if m.is_optional for lesson in m.lessons]

    # Required lessons come first; only fall back to the optional add-on once they are done.
    next_lesson = next(
        (lesson for lesson in required + optional if not lesson.completed), None
    )

    return CourseDetail(
        **course,
        lesson_count=len(required),
        completed_count=sum(1 for lesson in required if lesson.completed),
        optional_lesson_count=len(optional),
        optional_completed_count=sum(1 for lesson in optional if lesson.completed),
        modules=modules,
        next_lesson_id=next_lesson.id if next_lesson else None,
    )


async def _neighbours(course_id: str, lesson_id: str) -> tuple[str | None, str | None]:
    """Previous/next lesson in curriculum order, crossing module boundaries."""
    rows = await db.fetch_all(
        """
        SELECT l.id
        FROM lessons l
        JOIN modules m ON m.id = l.module_id
        WHERE l.course_id = %s
        ORDER BY m.is_optional, m.order_index, l.order_index, l.id
        """,
        (course_id,),
    )
    ids = [row["id"] for row in rows]
    if lesson_id not in ids:
        return None, None
    index = ids.index(lesson_id)
    return (ids[index - 1] if index > 0 else None,
            ids[index + 1] if index + 1 < len(ids) else None)


@router.get("/lessons/{lesson_id}", response_model=LessonDetail)
async def get_lesson(lesson_id: str, user: OptionalUser) -> LessonDetail:
    lesson = await db.fetch_one(
        """
        SELECT l.id, l.course_id, l.module_id, m.category, l.title, l.title_nl, l.title_en,
               l.summary, l.description, l.youtube_video_id, l.duration_sec, l.is_premium
        FROM lessons l
        JOIN modules m ON m.id = l.module_id
        WHERE l.id = %s
        """,
        (lesson_id,),
    )
    if not lesson:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lesson not found")

    phrases = await db.fetch_all(
        "SELECT phrase FROM lesson_key_phrases WHERE lesson_id = %s ORDER BY order_index",
        (lesson_id,),
    )
    vocabulary = await db.fetch_all(
        "SELECT id, nl, en FROM lesson_vocabulary WHERE lesson_id = %s ORDER BY order_index",
        (lesson_id,),
    )
    notes = await db.fetch_all(
        "SELECT title, explanation, examples FROM lesson_grammar_notes"
        " WHERE lesson_id = %s ORDER BY order_index",
        (lesson_id,),
    )
    transcript = await db.fetch_all(
        "SELECT speaker, line_nl, line_en FROM lesson_transcript"
        " WHERE lesson_id = %s ORDER BY order_index",
        (lesson_id,),
    )
    subtitle_rows = await db.fetch_all(
        "SELECT lang FROM lesson_subtitles WHERE lesson_id = %s ORDER BY lang", (lesson_id,)
    )
    # The answer column is deliberately not selected.
    quiz = await db.fetch_all(
        "SELECT id, question, options, difficulty, skill FROM quiz_questions"
        " WHERE lesson_id = %s ORDER BY order_index",
        (lesson_id,),
    )

    progress = None
    if user:
        row = await db.fetch_one(
            "SELECT watched_sec, last_position_sec, percent, completed_at"
            " FROM lesson_progress WHERE user_id = %s AND lesson_id = %s",
            (user["id"], lesson_id),
        )
        if row:
            progress = LessonProgress(**row)

    prev_id, next_id = await _neighbours(lesson["course_id"], lesson_id)

    return LessonDetail(
        **lesson,
        key_phrases=[row["phrase"] for row in phrases],
        vocabulary=[VocabularyItem(**row) for row in vocabulary],
        grammar_notes=[GrammarNote(**row) for row in notes],
        transcript=[TranscriptLine(**row) for row in transcript],
        subtitle_langs=[row["lang"] for row in subtitle_rows],
        quiz=[QuizQuestionPublic(**row) for row in quiz],
        progress=progress,
        prev_lesson_id=prev_id,
        next_lesson_id=next_id,
    )


@router.get("/lessons/{lesson_id}/subtitles/{lang}")
async def get_subtitles(lesson_id: str, lang: str):
    from fastapi.responses import Response

    if lang not in ("nl", "en"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown subtitle language")
    row = await db.fetch_one(
        "SELECT vtt_text FROM lesson_subtitles WHERE lesson_id = %s AND lang = %s",
        (lesson_id, lang),
    )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subtitles not available")
    return Response(content=row["vtt_text"], media_type="text/vtt")
