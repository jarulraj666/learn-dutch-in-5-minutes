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
