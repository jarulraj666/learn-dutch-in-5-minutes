"""Shared SQLite helpers — reads from the same db/content.db the pipeline uses."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent.parent
DB_PATH = ROOT / "db" / "content.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


# ---------------------------------------------------------------------------
# Topics
# ---------------------------------------------------------------------------

def list_topics(
    level: str | None = None,
    category: str | None = None,
    status: str | None = None,
    search: str | None = None,
) -> list[dict]:
    conditions: list[str] = []
    params: list[Any] = []

    if level:
        conditions.append("t.level = ?")
        params.append(level)
    if category:
        conditions.append("t.category = ?")
        params.append(category)
    if status:
        conditions.append("t.status = ?")
        params.append(status)
    if search:
        conditions.append("(t.id LIKE ? OR t.title_hint LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    # Join with canonical_scripts to get latest title + youtube_video_id from publish_jobs
    sql = f"""
        SELECT
            t.id,
            t.track,
            t.title_hint,
            t.level,
            t.category,
            t.status,
            t.order_index,
            t.last_used_at,
            t.use_count,
            cs.title AS script_title,
            cs.created_at AS script_created_at,
            pj.youtube_video_id,
            pj.scheduled_at,
            pj.artifact_path,
            pj.video_file_path,
            pj.status AS publish_status
        FROM topics t
        LEFT JOIN canonical_scripts cs ON cs.topic_id = t.id
            AND cs.id = (SELECT MAX(id) FROM canonical_scripts WHERE topic_id = t.id)
        LEFT JOIN publish_jobs pj ON pj.canonical_script_id = cs.id
            AND pj.id = (SELECT MAX(id) FROM publish_jobs WHERE canonical_script_id = cs.id)
        {where}
        ORDER BY t.order_index, t.id
    """
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [row_to_dict(r) for r in rows]


def get_topic(topic_id: str) -> dict | None:
    sql = """
        SELECT
            t.*,
            cs.id AS canonical_script_id,
            cs.title AS script_title,
            cs.script_json,
            cs.fingerprint,
            cs.created_at AS script_created_at,
            pj.id AS publish_job_id,
            pj.youtube_video_id,
            pj.scheduled_at,
            pj.artifact_path,
            pj.artifact_json,
            pj.artifact_file_path,
            pj.video_file_path,
            pj.status AS publish_status,
            pj.status_detail,
            pj.playlist_name
        FROM topics t
        LEFT JOIN canonical_scripts cs ON cs.topic_id = t.id
            AND cs.id = (SELECT MAX(id) FROM canonical_scripts WHERE topic_id = t.id)
        LEFT JOIN publish_jobs pj ON pj.canonical_script_id = cs.id
            AND pj.id = (SELECT MAX(id) FROM publish_jobs WHERE canonical_script_id = cs.id)
        WHERE t.id = ?
    """
    with get_connection() as conn:
        row = conn.execute(sql, [topic_id]).fetchone()
    if not row:
        return None
    result = row_to_dict(row)
    if result.get("script_json"):
        try:
            result["script"] = json.loads(result["script_json"])
        except Exception:
            result["script"] = None
    return result


def get_artifact_json(topic_id: str) -> str | None:
    """Return the raw artifact_json blob for a topic's latest publish job, or None."""
    sql = """
        SELECT pj.artifact_json
        FROM topics t
        LEFT JOIN canonical_scripts cs ON cs.topic_id = t.id
            AND cs.id = (SELECT MAX(id) FROM canonical_scripts WHERE topic_id = t.id)
        LEFT JOIN publish_jobs pj ON pj.canonical_script_id = cs.id
            AND pj.id = (SELECT MAX(id) FROM publish_jobs WHERE canonical_script_id = cs.id)
        WHERE t.id = ?
    """
    with get_connection() as conn:
        row = conn.execute(sql, [topic_id]).fetchone()
    if row:
        return row["artifact_json"]
    return None


def update_publish_job_artifact_json(topic_id: str, artifact: dict) -> bool:
    """Overwrite artifact_json on the latest publish_job for a topic."""
    sql = """
        UPDATE publish_jobs
        SET artifact_json = ?
        WHERE id = (
            SELECT pj.id
            FROM canonical_scripts cs
            JOIN publish_jobs pj ON pj.canonical_script_id = cs.id
            WHERE cs.topic_id = ?
            ORDER BY pj.id DESC
            LIMIT 1
        )
    """
    with get_connection() as conn:
        cur = conn.execute(sql, [json.dumps(artifact, ensure_ascii=False), topic_id])
        return cur.rowcount > 0


def update_topic_status(topic_id: str, status: str) -> bool:
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE topics SET status = ? WHERE id = ?", [status, topic_id]
        )
        return cur.rowcount > 0


def update_topic_script(topic_id: str, script: dict[str, Any]) -> bool:
    """Update latest canonical script and mirrored artifact JSON for a topic."""
    script_json = json.dumps(script, ensure_ascii=False)

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, title
            FROM canonical_scripts
            WHERE topic_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            [topic_id],
        ).fetchone()
        if not row:
            return False

        title = script.get("topic_title") or row["title"]
        conn.execute(
            """
            UPDATE canonical_scripts
            SET title = ?, script_json = ?
            WHERE id = ?
            """,
            [title, script_json, row["id"]],
        )

        artifact_row = conn.execute(
            """
            SELECT id, artifact_json
            FROM publish_jobs
            WHERE canonical_script_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            [row["id"]],
        ).fetchone()

        if artifact_row and artifact_row["artifact_json"]:
            try:
                artifact = json.loads(artifact_row["artifact_json"])
                artifact["script"] = script
                artifact["script_manually_edited"] = True
                artifact["script_edit_source"] = "webapp"
                if isinstance(script.get("image_prompt"), str):
                    artifact["image_prompt"] = script.get("image_prompt")
                conn.execute(
                    "UPDATE publish_jobs SET artifact_json = ? WHERE id = ?",
                    [json.dumps(artifact, ensure_ascii=False), artifact_row["id"]],
                )
            except Exception:
                pass

    return True


def get_stats() -> dict:
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM topics").fetchone()[0]
        by_status = conn.execute(
            "SELECT status, COUNT(*) as count FROM topics GROUP BY status"
        ).fetchall()
        by_level = conn.execute(
            "SELECT level, COUNT(*) as count FROM topics GROUP BY level"
        ).fetchall()
        by_category = conn.execute(
            "SELECT category, COUNT(*) as count FROM topics GROUP BY category"
        ).fetchall()
        recent = conn.execute(
            """
            SELECT t.id, t.title_hint, t.level, t.category, t.status,
                   cs.created_at, pj.youtube_video_id
            FROM topics t
            LEFT JOIN canonical_scripts cs ON cs.topic_id = t.id
            LEFT JOIN publish_jobs pj ON pj.canonical_script_id = cs.id
            WHERE cs.id IS NOT NULL
            ORDER BY cs.created_at DESC LIMIT 10
            """
        ).fetchall()
    return {
        "total": total,
        "by_status": {r["status"]: r["count"] for r in by_status},
        "by_level": {r["level"]: r["count"] for r in by_level},
        "by_category": {r["category"]: r["count"] for r in by_category},
        "recent": [row_to_dict(r) for r in recent],
    }


# ---------------------------------------------------------------------------
# Publish jobs
# ---------------------------------------------------------------------------

def list_publish_jobs(status: str | None = None) -> list[dict]:
    conditions = []
    params: list[Any] = []
    if status:
        conditions.append("pj.status = ?")
        params.append(status)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = f"""
        SELECT pj.*, t.id AS topic_id, t.title_hint, t.level, t.category,
               cs.title AS script_title
        FROM publish_jobs pj
        LEFT JOIN canonical_scripts cs ON cs.id = pj.canonical_script_id
        LEFT JOIN topics t ON t.id = cs.topic_id
        {where}
        ORDER BY pj.scheduled_at DESC
    """
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [row_to_dict(r) for r in rows]


def reschedule_publish_job(job_id: int, scheduled_at: str) -> bool:
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE publish_jobs SET scheduled_at = ? WHERE id = ?",
            [scheduled_at, job_id],
        )
        return cur.rowcount > 0
