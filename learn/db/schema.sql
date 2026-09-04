-- Learner app database (PostgreSQL).
--
-- Two groups of tables:
--   * content_*  — replaced wholesale by pipeline/tools/export_learning_content.py.
--                  Never write to these from the API.
--   * everything else — owned by the learner app.
--
-- Apply with:  psql "$DATABASE_URL" -f learn/db/schema.sql

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ---------------------------------------------------------------------------
-- Content (exported from the pipeline)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS courses (
    id           TEXT PRIMARY KEY,              -- CEFR level slug, e.g. 'A1A2'
    title        TEXT        NOT NULL,
    subtitle     TEXT        NOT NULL DEFAULT '',
    description  TEXT        NOT NULL DEFAULT '',
    status       TEXT        NOT NULL DEFAULT 'published'
                 CHECK (status IN ('published', 'coming_soon')),
    order_index  INTEGER     NOT NULL DEFAULT 0,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS modules (
    id           TEXT PRIMARY KEY,              -- '<course_id>:<category>'
    course_id    TEXT        NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    category     TEXT        NOT NULL,          -- grammar | vocabulary | common_words | dialogue
    title        TEXT        NOT NULL,
    description  TEXT        NOT NULL DEFAULT '',
    order_index  INTEGER     NOT NULL DEFAULT 0,
    -- Optional modules are add-ons: excluded from course progress and certificates.
    is_optional  BOOLEAN     NOT NULL DEFAULT FALSE,
    UNIQUE (course_id, category)
);

ALTER TABLE modules ADD COLUMN IF NOT EXISTS is_optional BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS lessons (
    id                TEXT PRIMARY KEY,          -- pipeline topics.id
    module_id         TEXT        NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
    course_id         TEXT        NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    title             TEXT        NOT NULL,
    title_nl          TEXT        NOT NULL DEFAULT '',
    title_en          TEXT        NOT NULL DEFAULT '',
    summary           TEXT        NOT NULL DEFAULT '',
    description       TEXT        NOT NULL DEFAULT '',
    youtube_video_id  TEXT        NOT NULL,
    duration_sec      INTEGER,
    transcript_text   TEXT        NOT NULL DEFAULT '',
    order_index       INTEGER     NOT NULL DEFAULT 0,
    is_premium        BOOLEAN     NOT NULL DEFAULT FALSE,
    published_at      TIMESTAMPTZ,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_lessons_module ON lessons(module_id, order_index);
CREATE INDEX IF NOT EXISTS idx_lessons_course ON lessons(course_id);

ALTER TABLE lessons ADD COLUMN IF NOT EXISTS title_en TEXT NOT NULL DEFAULT '';

CREATE TABLE IF NOT EXISTS lesson_vocabulary (
    id           BIGSERIAL PRIMARY KEY,
    lesson_id    TEXT    NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    nl           TEXT    NOT NULL,
    en           TEXT    NOT NULL,
    order_index  INTEGER NOT NULL DEFAULT 0,
    UNIQUE (lesson_id, order_index)
);

CREATE INDEX IF NOT EXISTS idx_vocab_lesson ON lesson_vocabulary(lesson_id);

CREATE TABLE IF NOT EXISTS lesson_key_phrases (
    id           BIGSERIAL PRIMARY KEY,
    lesson_id    TEXT    NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    phrase       TEXT    NOT NULL,
    order_index  INTEGER NOT NULL DEFAULT 0,
    UNIQUE (lesson_id, order_index)
);

CREATE TABLE IF NOT EXISTS lesson_grammar_notes (
    id           BIGSERIAL PRIMARY KEY,
    lesson_id    TEXT    NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    title        TEXT    NOT NULL,
    explanation  TEXT    NOT NULL DEFAULT '',
    examples     JSONB   NOT NULL DEFAULT '[]'::jsonb,
    order_index  INTEGER NOT NULL DEFAULT 0,
    UNIQUE (lesson_id, order_index)
);

CREATE TABLE IF NOT EXISTS lesson_transcript (
    id           BIGSERIAL PRIMARY KEY,
    lesson_id    TEXT    NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    speaker      TEXT    NOT NULL DEFAULT '',
    line_nl      TEXT    NOT NULL DEFAULT '',
    line_en      TEXT    NOT NULL DEFAULT '',
    order_index  INTEGER NOT NULL DEFAULT 0,
    UNIQUE (lesson_id, order_index)
);

CREATE INDEX IF NOT EXISTS idx_transcript_lesson ON lesson_transcript(lesson_id, order_index);

-- WebVTT is stored inline so the public app needs no media file hosting.
CREATE TABLE IF NOT EXISTS lesson_subtitles (
    lesson_id  TEXT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    lang       TEXT NOT NULL CHECK (lang IN ('nl', 'en')),
    vtt_text   TEXT NOT NULL,
    PRIMARY KEY (lesson_id, lang)
);

CREATE TABLE IF NOT EXISTS quiz_questions (
    id           TEXT PRIMARY KEY,              -- '<lesson_id>-q<n>', stable across regeneration
    lesson_id    TEXT    NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    question     TEXT    NOT NULL,
    options      JSONB   NOT NULL,
    answer       TEXT    NOT NULL,              -- never sent to the browser
    explanation  TEXT    NOT NULL DEFAULT '',
    difficulty   TEXT    NOT NULL DEFAULT 'medium',
    skill        TEXT    NOT NULL DEFAULT 'comprehension',
    order_index  INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_quiz_lesson ON quiz_questions(lesson_id, order_index);

-- A2 mock exams (Staatsexamen NT2 Programma I style). Exported from the
-- pipeline the same way lessons/quizzes are — see pipeline/core/store_mock_exam.py.
CREATE TABLE IF NOT EXISTS mock_exams (
    id                 TEXT PRIMARY KEY,          -- 'a2-<section>-<n>'
    section            TEXT        NOT NULL CHECK (section IN ('reading', 'listening', 'writing', 'speaking', 'knm')),
    level              TEXT        NOT NULL DEFAULT 'A2',
    exam_number        INTEGER     NOT NULL,
    title              TEXT        NOT NULL,
    instructions       TEXT        NOT NULL DEFAULT '',
    time_limit_minutes INTEGER     NOT NULL,
    total_questions    INTEGER     NOT NULL,
    parts_count        INTEGER     NOT NULL DEFAULT 1,
    pass_threshold     INTEGER,                    -- score needed to pass, e.g. 18; NULL where not published (speaking)
    max_score          INTEGER,                    -- e.g. 25, 37, 40; NULL where not published (speaking)
    status             TEXT        NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published')),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (section, exam_number)
);

CREATE TABLE IF NOT EXISTS mock_exam_passages (
    id                  TEXT PRIMARY KEY,
    exam_id             TEXT    NOT NULL REFERENCES mock_exams(id) ON DELETE CASCADE,
    order_index         INTEGER NOT NULL DEFAULT 0,
    part_number         INTEGER,                   -- 1-4 for speaking/writing parts
    passage_type        TEXT    NOT NULL CHECK (passage_type IN
                         ('text', 'audio', 'video', 'one_picture', 'two_picture', 'three_picture')),
    title               TEXT    NOT NULL DEFAULT '',
    display_prompt_nl   TEXT    NOT NULL DEFAULT '',     -- learner-facing scenario/instruction; content_nl remains the audio script
    scene_description   TEXT    NOT NULL DEFAULT '',     -- visual/image script used to generate still/video media
    content_nl          TEXT    NOT NULL DEFAULT '',
    content_en          TEXT,
    media_urls          JSONB   NOT NULL DEFAULT '[]'::jsonb,   -- [{type, url}, ...]
    render_manifest_path TEXT,                     -- provenance for regeneration
    image_prompt        JSONB                       -- prompt(s) used to generate media, for audit/regeneration
);

CREATE INDEX IF NOT EXISTS idx_mock_passages_exam ON mock_exam_passages(exam_id, order_index);

CREATE TABLE IF NOT EXISTS mock_exam_questions (
    id              TEXT PRIMARY KEY,              -- '<exam_id>-q<n>'
    exam_id         TEXT    NOT NULL REFERENCES mock_exams(id) ON DELETE CASCADE,
    passage_id      TEXT    REFERENCES mock_exam_passages(id) ON DELETE CASCADE,
    part_number     INTEGER,
    order_index     INTEGER NOT NULL DEFAULT 0,
    question_text   TEXT    NOT NULL,
    question_audio_url TEXT,
    question_options_audio_url TEXT,
    option_audio_cues JSONB,                       -- listening combined audio: [{option_index, start, end}, ...]
    question_type   TEXT    NOT NULL CHECK (question_type IN ('multiple_choice', 'open_written', 'open_spoken')),
    options         JSONB,                          -- required for multiple_choice
    answer          TEXT,                           -- never sent to non-admin client
    explanation     TEXT    NOT NULL DEFAULT '',
    category        TEXT,                           -- KNM theme tag: customs | work_income | education | healthcare | housing | institutions | government | history_geography
    max_score       INTEGER NOT NULL DEFAULT 1,
    grading_rubric  JSONB,                          -- writing/speaking: [{criterion, max_points}, ...]
    model_answer    TEXT,                           -- reference answer for QA / future grading
    year_asked      INTEGER,                        -- real exam year, only if confidently known; else NULL
    option_image_prompts JSONB,                     -- rare "picture-choice" MC questions: one image prompt per option, admin-only
    option_audio_urls   JSONB,                      -- listening MC questions: one generated audio path per option
    option_media_urls   JSONB                       -- matching uploaded image path per option, null until generated/uploaded
);

CREATE INDEX IF NOT EXISTS idx_mock_questions_exam ON mock_exam_questions(exam_id, order_index);

-- ---------------------------------------------------------------------------
-- Auth.js tables (schema required by @auth/pg-adapter)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS users (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name           TEXT,
    email          TEXT UNIQUE,
    "emailVerified" TIMESTAMPTZ,
    image          TEXT,
    plan           TEXT        NOT NULL DEFAULT 'free',   -- reserved for future paid tiers
    role           TEXT        NOT NULL DEFAULT 'learner' CHECK (role IN ('learner', 'admin')),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS accounts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    "userId"            UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type                TEXT NOT NULL,
    provider            TEXT NOT NULL,
    "providerAccountId" TEXT NOT NULL,
    refresh_token       TEXT,
    access_token        TEXT,
    expires_at          BIGINT,
    id_token            TEXT,
    scope               TEXT,
    session_state       TEXT,
    token_type          TEXT,
    UNIQUE (provider, "providerAccountId")
);

CREATE TABLE IF NOT EXISTS sessions (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    "userId"       UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires        TIMESTAMPTZ NOT NULL,
    "sessionToken" TEXT        NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS verification_token (
    identifier TEXT        NOT NULL,
    token      TEXT        NOT NULL,
    expires    TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (identifier, token)
);

-- ---------------------------------------------------------------------------
-- Learner state
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS user_settings (
    user_id       UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    locale        TEXT        NOT NULL DEFAULT 'en',
    email_opt_in  BOOLEAN     NOT NULL DEFAULT FALSE,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS enrollments (
    user_id      UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    course_id    TEXT        NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    enrolled_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, course_id)
);

CREATE TABLE IF NOT EXISTS lesson_progress (
    user_id           UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    lesson_id         TEXT        NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    watched_sec       INTEGER     NOT NULL DEFAULT 0,
    last_position_sec INTEGER     NOT NULL DEFAULT 0,
    percent           SMALLINT    NOT NULL DEFAULT 0 CHECK (percent BETWEEN 0 AND 100),
    completed_at      TIMESTAMPTZ,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, lesson_id)
);

CREATE INDEX IF NOT EXISTS idx_progress_user ON lesson_progress(user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS quiz_attempts (
    id          BIGSERIAL PRIMARY KEY,
    user_id     UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    lesson_id   TEXT        NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    attempt_no  INTEGER     NOT NULL,
    score       SMALLINT    NOT NULL,
    total       SMALLINT    NOT NULL,
    answers     JSONB       NOT NULL DEFAULT '[]'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, lesson_id, attempt_no)
);

CREATE INDEX IF NOT EXISTS idx_attempts_user_lesson ON quiz_attempts(user_id, lesson_id);

CREATE TABLE IF NOT EXISTS mock_exam_attempts (
    id          BIGSERIAL PRIMARY KEY,
    user_id     UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    exam_id     TEXT        NOT NULL REFERENCES mock_exams(id) ON DELETE CASCADE,
    attempt_no  INTEGER     NOT NULL,
    score       SMALLINT    NOT NULL,
    total       SMALLINT    NOT NULL,
    percent     SMALLINT    NOT NULL,
    label       TEXT        NOT NULL,
    status      TEXT        NOT NULL DEFAULT 'completed',
    answers     JSONB       NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, exam_id, attempt_no)
);

CREATE INDEX IF NOT EXISTS idx_mock_attempts_user_exam ON mock_exam_attempts(user_id, exam_id);

ALTER TABLE mock_exam_attempts ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'completed';

CREATE TABLE IF NOT EXISTS mock_exam_speaking_recordings (
    id          UUID        PRIMARY KEY,
    user_id     UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    exam_id     TEXT        NOT NULL REFERENCES mock_exams(id) ON DELETE CASCADE,
    question_id TEXT        NOT NULL REFERENCES mock_exam_questions(id) ON DELETE CASCADE,
    attempt_id  BIGINT      REFERENCES mock_exam_attempts(id) ON DELETE CASCADE,
    storage_path TEXT       NOT NULL,
    feedback_label TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, exam_id, question_id, attempt_id)
);

CREATE INDEX IF NOT EXISTS idx_speaking_recordings_attempt ON mock_exam_speaking_recordings(attempt_id);

-- SM-2 spaced repetition over lesson_vocabulary.
CREATE TABLE IF NOT EXISTS flashcard_reviews (
    user_id        UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    vocab_id       BIGINT      NOT NULL REFERENCES lesson_vocabulary(id) ON DELETE CASCADE,
    ease           REAL        NOT NULL DEFAULT 2.5,
    interval_days  INTEGER     NOT NULL DEFAULT 0,
    reps           INTEGER     NOT NULL DEFAULT 0,
    lapses         INTEGER     NOT NULL DEFAULT 0,
    due_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, vocab_id)
);

CREATE INDEX IF NOT EXISTS idx_flashcards_due ON flashcard_reviews(user_id, due_at);

CREATE TABLE IF NOT EXISTS certificates (
    id         BIGSERIAL PRIMARY KEY,
    user_id    UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    course_id  TEXT        NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    serial     TEXT        NOT NULL UNIQUE,
    issued_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, course_id)
);

-- Learner feedback: submitted by users, reviewed and published by admins.
CREATE TABLE IF NOT EXISTS feedback (
    id           BIGSERIAL   PRIMARY KEY,
    user_id      UUID        REFERENCES users(id) ON DELETE SET NULL,
    display_name TEXT,                          -- used for seeded testimonials without a user account
    rating       SMALLINT    NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment      TEXT        NOT NULL DEFAULT '',
    status       TEXT        NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'published', 'rejected')),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_feedback_status ON feedback(status, created_at DESC);

-- Seed a few published testimonials so the landing page has content before real feedback arrives.
INSERT INTO feedback (display_name, rating, comment, status, published_at)
SELECT * FROM (VALUES
    ('Sanne V.', 5, 'The five-minute lessons fit perfectly into my commute. I finally stuck with a language habit!', 'published', now()),
    ('Mateusz K.', 5, 'Grammar explanations are so clear. I passed my inburgering exam thanks to this course.', 'published', now()),
    ('Priya R.', 4, 'Love the flashcards and quizzes. Would like even more dialogue practice.', 'published', now())
) AS seed(display_name, rating, comment, status, published_at)
WHERE NOT EXISTS (SELECT 1 FROM feedback);
