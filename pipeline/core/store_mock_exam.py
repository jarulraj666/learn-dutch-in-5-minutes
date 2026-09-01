"""Storage for A2 mock exams: SQLite staging (pipeline) + Postgres export (learner app).

Mirrors the existing content pipeline's separation of concerns:
  * mock_exam_jobs (SQLite, db/content.db) — staging area holding the full
    generated artifact (passages + questions + media) before export. This is
    what the webapp reads/edits.
  * mock_exams / mock_exam_passages / mock_exam_questions (Postgres) — the
    finalized, learner-app-facing tables. Upserted the same delete-then-
    reinsert-children way pipeline/tools/export_learning_content.py upserts
    lessons.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# SQLite staging (db/content.db)
# ---------------------------------------------------------------------------

def _ensure_mock_exam_jobs_table(conn: sqlite3.Connection) -> None:
    # db/content.db files created before this feature existed won't have this
    # table yet, and nothing besides pipeline CLIs calls init_db() at startup
    # (the webapp backend doesn't) — so create it lazily on first use.
    conn.execute(
        "CREATE TABLE IF NOT EXISTS mock_exam_jobs ("
        "id TEXT PRIMARY KEY, section TEXT NOT NULL, exam_number INTEGER NOT NULL, "
        "level TEXT NOT NULL DEFAULT 'A2', status TEXT NOT NULL DEFAULT 'draft', "
        "artifact_json TEXT, exported_at TEXT, created_at TEXT NOT NULL, updated_at TEXT)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_mock_exam_jobs_section ON mock_exam_jobs(section, exam_number)"
    )


def save_mock_exam_job(exam_id: str, section: str, exam_number: int, level: str,
                        artifact: dict[str, Any], status: str) -> None:
    from pipeline.core.db import get_connection

    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        _ensure_mock_exam_jobs_table(conn)
        existing = conn.execute("SELECT id FROM mock_exam_jobs WHERE id = ?", (exam_id,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE mock_exam_jobs SET section=?, exam_number=?, level=?, status=?, "
                "artifact_json=?, updated_at=? WHERE id=?",
                (section, exam_number, level, status, json.dumps(artifact), now, exam_id),
            )
        else:
            conn.execute(
                "INSERT INTO mock_exam_jobs (id, section, exam_number, level, status, artifact_json, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (exam_id, section, exam_number, level, status, json.dumps(artifact), now, now),
            )
        conn.commit()


def load_mock_exam_job(exam_id: str) -> dict[str, Any] | None:
    from pipeline.core.db import get_connection

    with get_connection() as conn:
        _ensure_mock_exam_jobs_table(conn)
        row = conn.execute("SELECT * FROM mock_exam_jobs WHERE id = ?", (exam_id,)).fetchone()
    if not row:
        return None
    data = dict(row)
    data["artifact"] = json.loads(data["artifact_json"]) if data.get("artifact_json") else None
    return data


def list_mock_exam_jobs(section: str | None = None) -> list[dict[str, Any]]:
    from pipeline.core.db import get_connection

    query = "SELECT id, section, exam_number, level, status, exported_at, created_at, updated_at FROM mock_exam_jobs"
    params: tuple = ()
    if section:
        query += " WHERE section = ?"
        params = (section,)
    query += " ORDER BY section, exam_number"

    with get_connection() as conn:
        _ensure_mock_exam_jobs_table(conn)
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def mark_mock_exam_job_exported(exam_id: str) -> None:
    from pipeline.core.db import get_connection

    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        _ensure_mock_exam_jobs_table(conn)
        conn.execute(
            "UPDATE mock_exam_jobs SET status='exported', exported_at=?, updated_at=? WHERE id=?",
            (now, now, exam_id),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Postgres export (learn/db/schema.sql)
# ---------------------------------------------------------------------------

_CHILD_TABLES = ("mock_exam_questions", "mock_exam_passages")


def upsert_mock_exam(cur, artifact: dict[str, Any]) -> None:
    """Upsert one mock exam (and replace its passages/questions) into Postgres."""
    from psycopg.types.json import Jsonb

    exam_id = artifact["id"]

    cur.execute(
        """
        INSERT INTO mock_exams (id, section, level, exam_number, title, instructions,
                                 time_limit_minutes, total_questions, parts_count,
                                 pass_threshold, max_score, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            title = EXCLUDED.title, instructions = EXCLUDED.instructions,
            time_limit_minutes = EXCLUDED.time_limit_minutes,
            total_questions = EXCLUDED.total_questions, parts_count = EXCLUDED.parts_count,
            pass_threshold = EXCLUDED.pass_threshold, max_score = EXCLUDED.max_score,
            status = EXCLUDED.status
        """,
        (exam_id, artifact["section"], artifact["level"], artifact["exam_number"],
         artifact["title"], artifact["instructions"], artifact["time_limit_minutes"],
         artifact["total_questions"], artifact["parts_count"], artifact["pass_threshold"],
         artifact["max_score"], "published"),
    )

    # Replace children so upstream regeneration/deletions propagate cleanly.
    for table in _CHILD_TABLES:
        cur.execute(f"DELETE FROM {table} WHERE exam_id = %s", (exam_id,))

    cur.executemany(
        "INSERT INTO mock_exam_passages (id, exam_id, order_index, part_number, passage_type, "
        "title, content_nl, content_en, media_urls, render_manifest_path, image_prompt) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        [
            (p["id"], exam_id, p["order_index"], p.get("part_number"), p["passage_type"],
             p.get("title", ""), p.get("content_nl", ""), p.get("content_en"),
             Jsonb(p.get("media_urls") or []), p.get("render_manifest_path"),
             Jsonb(p["image_prompt"]) if p.get("image_prompt") else None)
            for p in artifact.get("passages", [])
        ],
    )
    cur.executemany(
        "INSERT INTO mock_exam_questions (id, exam_id, passage_id, part_number, order_index, "
        "question_text, question_type, options, answer, explanation, category, max_score, "
        "grading_rubric, model_answer, year_asked, option_image_prompts, option_media_urls) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        [
            (q["id"], exam_id, q.get("passage_id"), q.get("part_number"), q["order_index"],
             q["question_text"], q["question_type"],
             Jsonb(q["options"]) if q.get("options") else None, q.get("answer"),
             q.get("explanation", ""), q.get("category"), q.get("max_score", 1),
             Jsonb(q["grading_rubric"]) if q.get("grading_rubric") else None,
             q.get("model_answer"), q.get("year_asked"),
             Jsonb(q["option_image_prompts"]) if q.get("option_image_prompts") else None,
             Jsonb(q["option_media_urls"]) if q.get("option_media_urls") else None)
            for q in artifact.get("questions", [])
        ],
    )


def push_mock_exam_to_postgres(artifact: dict[str, Any], database_url: str) -> None:
    import psycopg

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            upsert_mock_exam(cur, artifact)
        conn.commit()
