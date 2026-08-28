"""Export published episodes from the pipeline SQLite DB into the learner-app Postgres DB.

The learner app never reads ``db/content.db``. This tool is the only bridge:
it reads the latest artifact per topic, maps it onto the ``learn/db/schema.sql``
content tables, and upserts. Re-running is safe — child rows for a lesson are
replaced, so removing a vocabulary item upstream removes it downstream too.

Usage:
    export DATABASE_URL='postgresql://user:pass@host/db'

    python -m pipeline.tools.export_learning_content --dry-run
    python -m pipeline.tools.export_learning_content
    python -m pipeline.tools.export_learning_content --topic vocab_weather
    python -m pipeline.tools.export_learning_content --level A1A2

    # Write a JSON snapshot instead of talking to Postgres:
    python -m pipeline.tools.export_learning_content --json-out output/learn_export.json
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
LOGGER = logging.getLogger(__name__)

# The learner-facing curriculum: progressive units that deliberately mix
# vocabulary, high-frequency words and grammar, instead of grouping by the
# category a lesson was generated under. Grammar arrives at the point the
# learner needs it — present tense lands in unit 0, lesson 8.
#
# Every non-dialogue A1A2 topic must appear exactly once. Anything missing is
# swept into the FALLBACK_UNIT and reported by --dry-run, so nothing is lost.
UNITS: list[dict] = [
    {
        "key": "start_here",
        "title": "Start Here",
        "description": "Sounds, greetings and just enough grammar to speak from day one. "
                       "By the end you can introduce yourself and ask a question.",
        "lessons": [
            "course_welcome",
            "vocab_alphabet_pronunciation",
            "pronunciation_tricky_sounds",
            "vocab_greetings",
            "cw_polite_basics",
            "cw_pronouns",
            "grammar_zijn_hebben",          # "Ik ben ..." — first sentence
            "grammar_present_tense",        # "Ik werk ..." — grammar early, as intended
            "cw_top_verbs",                 # the verbs they can now conjugate
            "cw_numbers_1_20",
            "intro_self_monologue",         # payoff: introduce yourself
            "grammar_de_het",
            "grammar_jij_vs_u",
            "grammar_word_order",
            "grammar_questions",            # payoff: ask as well as answer
        ],
    },
    {
        "key": "people",
        "title": "People and Possessions",
        "description": "Talk about family, work and how you feel — and say what is not true.",
        "lessons": [
            "cw_question_words",
            "grammar_plural",
            "grammar_spelling_open_closed",  # explains the plural spelling changes
            "vocab_family",
            "grammar_possessive_pronouns",
            "cw_professions_basic",
            "grammar_object_pronouns",
            "cw_emotions",
            "vocab_body_parts",
            "grammar_negation",
            "cw_negative_indefinites",
        ],
    },
    {
        "key": "describing",
        "title": "Describing Things",
        "description": "Adjectives, opposites and pointing things out: this one, that one.",
        "lessons": [
            "grammar_adjective_basics",
            "cw_colors",
            "cw_adjectives_basic",
            "cw_opposites",
            "cw_degree_adverbs",
            "grammar_demonstratives",
            "vocab_clothing",
            "vocab_home_rooms",
            "cw_house_objects",
        ],
    },
    {
        "key": "time_routine",
        "title": "Time and Daily Routine",
        "description": "Numbers, the clock, the calendar, and the verbs you use every day.",
        "lessons": [
            "cw_numbers_20_100",
            "cw_numbers_large",
            "cw_ordinal_numbers",
            "cw_days_of_week",
            "cw_months",
            "cw_seasons",
            "cw_time_telling",
            "vocab_time",
            "grammar_prepositions_time",
            "cw_frequency_words",
            "cw_verbs_daily_actions",
            "grammar_separable_verbs",
            "grammar_reflexive_verbs",
        ],
    },
    {
        "key": "food_shopping",
        "title": "Food, Shopping and Money",
        "description": "Order, buy and pay — plus the modal verbs that make requests polite.",
        "lessons": [
            "vocab_food_drinks",
            "vocab_vegetables_fruit",
            "vocab_cooking",
            "vocab_at_restaurant",
            "cw_quantities",
            "cw_shopping_words",
            "vocab_clothing_shopping",
            "vocab_banking_money",
            "grammar_modal_verbs",
            "grammar_imperative",
        ],
    },
    {
        "key": "out_and_about",
        "title": "Out and About",
        "description": "Getting around town, describing where things are, and the weather.",
        "lessons": [
            "cw_prepositions",
            "vocab_transport",
            "vocab_city_navigation",
            "cw_city_places",
            "cw_direction_words",
            "grammar_prepositions_place",
            "grammar_directional_prepositions",
            "grammar_er",
            "vocab_weather",
            "vocab_nature_outdoor",
            "cw_nature",
            "cw_animals",
        ],
    },
    {
        "key": "work_health_leisure",
        "title": "Work, Health and Free Time",
        "description": "The vocabulary of appointments, offices, classrooms, hobbies and celebrations.",
        "lessons": [
            "vocab_health_body",
            "cw_health_words",
            "vocab_work_office",
            "vocab_school_items",
            "vocab_digital_daily",
            "vocab_polite_expressions",
            "vocab_sports_hobbies",
            "vocab_celebrations",
        ],
    },
    {
        # Grammar with no natural situational home lives here rather than being
        # forced into a themed unit where it does not belong.
        "key": "grammar",
        "title": "Grammar",
        "description": "The two Dutch past tenses, plus the rules that do not belong to any "
                       "one situation: diminutives and comparisons.",
        "lessons": [
            "grammar_perfect_tense",
            "grammar_past_tense_zijn",
            "grammar_imperfect_regular",
            "grammar_imperfect_irregular",
            "grammar_imperfect_vs_perfect",
            "grammar_diminutives",
            "grammar_comparative",
        ],
    },
    {
        "key": "advanced_grammar",
        "title": "Advanced Grammar",
        "description": "Longer sentences: because, that, which, if — plus the future and "
                       "the conditional. Take these once the earlier units feel comfortable.",
        "lessons": [
            "cw_conjunctions_basic",
            "cw_linking_words",
            "grammar_want_omdat",
            "grammar_dat_clauses",
            "grammar_relative_clauses",
            "grammar_als_conditional",
            "grammar_future_gaan",
            "grammar_future_zullen",
            "grammar_conditional_zou",
            "grammar_om_te",
        ],
    },
]

# Catches any topic missing from UNITS so a curriculum edit can never drop a lesson.
# It is hidden from learners while empty, so it is safe to leave in place permanently.
FALLBACK_UNIT = {
    "key": "more",
    "title": "More Lessons",
    "description": "Extra lessons that do not belong to a unit yet.",
    "lessons": [],
}

# Real conversations, kept as an optional add-on outside the graded path.
DIALOGUE_UNIT = {
    "key": "dialogue",
    "title": "Dialogue & Listening",
    "description": "Practice with natural Dutch conversations. Optional — these do not "
                   "count toward your course progress or certificate.",
    "lessons": [],
}

OPTIONAL_MODULES = {"dialogue"}

# topic_id → (unit key, position within the unit)
UNIT_INDEX: dict[str, tuple[str, int]] = {
    topic_id: (unit["key"], position)
    for unit in UNITS
    for position, topic_id in enumerate(unit["lessons"])
}

# Start Here is an onboarding ramp, not a fourth content module.
START_HERE_MAX = 15

ALL_UNITS = [*UNITS, FALLBACK_UNIT, DIALOGUE_UNIT]

# Used when config/playlists.yaml has no entry for the module.
MODULE_DESCRIPTIONS = {
    "start_here": "Your first hour of Dutch. Sounds, greetings and just enough "
                  "grammar to start speaking in real sentences straight away.",
}

COURSE_META = {
    "A1A2": {
        "title": "Dutch for Beginners",
        "subtitle": "A1–A2",
        "description": "Start from zero. Short units built around real situations — each one "
                       "mixing everyday words with the grammar that makes them usable, "
                       "starting from your very first lesson.",
        "order_index": 1,
        "status": "published",
    },
    "B1": {
        "title": "Dutch Intermediate",
        "subtitle": "B1",
        "description": "Build fluency with richer grammar, wider vocabulary and longer conversations.",
        "order_index": 2,
        "status": "coming_soon",
    },
    "B2": {
        "title": "Dutch Upper Intermediate",
        "subtitle": "B2",
        "description": "Handle nuanced, natural Dutch with confidence.",
        "order_index": 3,
        "status": "coming_soon",
    },
}

_TTS_TAG_RE = re.compile(r"\[(?:slow|fast|normal|whisper|excited|pause[^\]]*)\]", re.IGNORECASE)
_SRT_TIME_RE = re.compile(r"(\d{2}:\d{2}:\d{2}),(\d{3})")
_VTT_END_RE = re.compile(r"-->\s*(\d{2}):(\d{2}):(\d{2})\.(\d{3})")


def _clean(text: Any) -> str:
    return " ".join(_TTS_TAG_RE.sub(" ", str(text or "")).split())


def srt_to_vtt(srt_text: str) -> str:
    """Convert SRT to WebVTT (comma → dot in timestamps, plus the WEBVTT header)."""
    return "WEBVTT\n\n" + _SRT_TIME_RE.sub(r"\1.\2", srt_text).lstrip()


def _duration_from_vtt(vtt_text: str) -> int | None:
    """Artifacts store no video duration, so take the last subtitle cue end time."""
    ends = _VTT_END_RE.findall(vtt_text or "")
    if not ends:
        return None
    hours, minutes, seconds, millis = ends[-1]
    total = int(hours) * 3600 + int(minutes) * 60 + int(seconds) + (1 if int(millis) else 0)
    return total or None


def _read_subtitle(rel_path: str) -> str:
    """Read an SRT file referenced by the artifact and return WebVTT, or '' if unavailable."""
    if not rel_path:
        return ""
    p = Path(rel_path)
    if not p.is_absolute():
        p = ROOT / p
    try:
        p = p.resolve()
        p.relative_to(ROOT.resolve())
    except (OSError, ValueError):
        LOGGER.warning("subtitle path outside repo, skipping: %s", rel_path)
        return ""
    if not p.is_file():
        return ""
    return srt_to_vtt(p.read_text(encoding="utf-8", errors="replace"))


def _subtitle_paths(subtitles: dict) -> dict[str, str]:
    """Resolve NL/EN SRT paths across the artifact shapes the pipeline has produced."""
    files = subtitles.get("srt_files") or {}
    return {
        "nl": subtitles.get("srt_nl") or files.get("nl") or subtitles.get("nl") or "",
        "en": subtitles.get("srt_en") or files.get("en") or "",
    }


# ---------------------------------------------------------------------------
# Artifact → lesson record
# ---------------------------------------------------------------------------

def _build_transcript(script: dict) -> list[dict[str, Any]]:
    from pipeline.utils import iter_dialogue_turns

    turns = iter_dialogue_turns(script.get("dialogue", []))
    en_turns = iter_dialogue_turns(script.get("dialogue_en", []))
    en_by_index = {i: line for i, (_, line) in enumerate(en_turns)}

    rows = []
    for idx, (speaker, line) in enumerate(turns):
        nl = _clean(line)
        if not nl:
            continue
        rows.append({
            "speaker": speaker,
            "line_nl": nl,
            "line_en": _clean(en_by_index.get(idx, "")),
            "order_index": len(rows),
        })
    return rows


def _english_title(script: dict, title_hint: str) -> str:
    """Prefer the script's English title; otherwise take the hint's leading clause.

    Hints look like "Personal pronouns: ik, jij, hij, ..." — everything after the
    colon is example words, not a title.
    """
    title = _clean(script.get("topic_title_en"))
    if title:
        return title
    head = _clean(title_hint).split(":", 1)[0].split(" — ", 1)[0]
    return head[:80]


def _lesson_summary(artifact: dict, script: dict) -> str:
    """Only a genuinely distinct blurb; the English title is exported separately."""
    return ""


def build_lesson(row: dict, artifact: dict) -> dict[str, Any] | None:
    """Map one artifact onto a learner lesson record, or None if not publishable."""
    from pipeline.generate.generate_quiz import normalize_quiz
    from pipeline.stages import normalize_level

    topic_id = row["topic_id"]
    script = artifact.get("script") or {}
    youtube = artifact.get("youtube") or {}
    video_id = youtube.get("video_id") or row.get("youtube_video_id") or ""

    if not video_id:
        return None
    if not script.get("dialogue") and not script.get("script_text"):
        return None

    level = normalize_level(artifact.get("level") or row["level"] or "A1A2")
    category = artifact.get("category") or row["category"] or "dialogue"
    metadata = artifact.get("metadata") or {}
    subtitles = artifact.get("subtitles") or {}

    quiz = normalize_quiz(script.get("quiz") or [], topic_id)

    # Curriculum position comes from UNITS, not from the generation category.
    if category == "dialogue":
        unit_key, order_index = "dialogue", row.get("order_index") or 0
    elif topic_id in UNIT_INDEX:
        unit_key, order_index = UNIT_INDEX[topic_id]
    else:
        LOGGER.warning("%s is not placed in any unit — falling back to 'more'", topic_id)
        unit_key, order_index = "more", row.get("order_index") or 0


    subtitle_vtt = {
        lang: vtt
        for lang, path in _subtitle_paths(subtitles).items()
        if (vtt := _read_subtitle(path))
    }
    duration_sec = next(
        (d for d in (_duration_from_vtt(v) for v in subtitle_vtt.values()) if d), None
    )

    return {
        "id": topic_id,
        "course_id": level,
        "category": unit_key,
        "module_id": f"{level}:{unit_key}",
        "title": row.get("youtube_title") or metadata.get("title") or row["title_hint"],
        "title_nl": _clean(script.get("topic_title")),
        "title_en": _english_title(script, row["title_hint"]),
        "summary": _lesson_summary(artifact, script),
        "description": metadata.get("description", ""),
        "youtube_video_id": video_id,
        "duration_sec": duration_sec,
        "transcript_text": _clean(script.get("script_text")),
        "order_index": order_index,
        "is_premium": False,
        "published_at": row.get("published_at"),
        "vocabulary": [
            {"nl": _clean(v.get("nl")), "en": _clean(v.get("en")), "order_index": i}
            for i, v in enumerate(script.get("vocabulary") or [])
            if v.get("nl") and v.get("en")
        ],
        "key_phrases": [
            {"phrase": _clean(p), "order_index": i}
            for i, p in enumerate(script.get("key_phrases") or [])
            if _clean(p)
        ],
        "grammar_notes": [
            {
                "title": _clean(n.get("title")),
                "explanation": _clean(n.get("explanation")),
                "examples": [_clean(e) for e in (n.get("examples") or [])],
                "order_index": i,
            }
            for i, n in enumerate(script.get("grammar_notes") or [])
            if n.get("title")
        ],
        "transcript": _build_transcript(script),
        "subtitles": subtitle_vtt,
        "quiz": [dict(q, order_index=i) for i, q in enumerate(quiz)],
    }


def validate_curriculum(all_topic_ids: set[str]) -> list[str]:
    """Return human-readable problems with the UNITS definition."""
    problems: list[str] = []

    seen: dict[str, str] = {}
    for unit in UNITS:
        for topic_id in unit["lessons"]:
            if topic_id in seen:
                problems.append(
                    f"{topic_id} appears in both '{seen[topic_id]}' and '{unit['key']}'"
                )
            seen[topic_id] = unit["key"]

    start_here = next(u for u in UNITS if u["key"] == "start_here")
    if len(start_here["lessons"]) > START_HERE_MAX:
        problems.append(
            f"Start Here has {len(start_here['lessons'])} lessons, max is {START_HERE_MAX}"
        )

    unplaced = sorted(all_topic_ids - set(seen))
    if unplaced:
        problems.append(f"not placed in any unit: {', '.join(unplaced)}")

    unknown = sorted(set(seen) - all_topic_ids)
    if unknown:
        problems.append(f"listed in UNITS but not a known topic: {', '.join(unknown)}")

    return problems


def collect_lessons(level: str | None, category: str | None, topic_id: str | None) -> list[dict]:
    from pipeline.core.db import get_connection

    sql = """
        SELECT t.id AS topic_id, t.level, t.category, t.title_hint, t.order_index,
               t.youtube_title, pj.youtube_video_id, pj.published_at, pj.artifact_json
        FROM topics t
        JOIN canonical_scripts cs ON cs.topic_id = t.id
            AND cs.id = (SELECT MAX(id) FROM canonical_scripts WHERE topic_id = t.id)
        JOIN publish_jobs pj ON pj.canonical_script_id = cs.id
            AND pj.id = (SELECT MAX(id) FROM publish_jobs WHERE canonical_script_id = cs.id)
        WHERE pj.artifact_json IS NOT NULL
    """
    params: list[str] = []
    if topic_id:
        sql += " AND t.id = ?"
        params.append(topic_id)
    if category:
        sql += " AND t.category = ?"
        params.append(category)
    if level:
        sql += " AND t.level = ?"
        params.append(level)

    with get_connection() as conn:
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]

    lessons = []
    for row in rows:
        try:
            artifact = json.loads(row["artifact_json"])
        except json.JSONDecodeError:
            LOGGER.warning("skip %s: unreadable artifact_json", row["topic_id"])
            continue
        lesson = build_lesson(row, artifact)
        if lesson:
            lessons.append(lesson)
        else:
            LOGGER.info("skip %s: no YouTube video id or no script", row["topic_id"])
    return lessons


# ---------------------------------------------------------------------------
# Postgres upsert
# ---------------------------------------------------------------------------

_CHILD_TABLES = (
    "lesson_vocabulary",
    "lesson_key_phrases",
    "lesson_grammar_notes",
    "lesson_transcript",
    "lesson_subtitles",
    "quiz_questions",
)


def _upsert_courses(cur, levels: set[str]) -> None:
    for level in sorted(levels | set(COURSE_META)):
        meta = COURSE_META.get(level, {
            "title": level, "subtitle": level, "description": "",
            "order_index": 99, "status": "coming_soon",
        })
        cur.execute(
            """
            INSERT INTO courses (id, title, subtitle, description, status, order_index, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, now())
            ON CONFLICT (id) DO UPDATE SET
                title = EXCLUDED.title, subtitle = EXCLUDED.subtitle,
                description = EXCLUDED.description, status = EXCLUDED.status,
                order_index = EXCLUDED.order_index, updated_at = now()
            """,
            (level, meta["title"], meta["subtitle"], meta["description"],
             meta["status"], meta["order_index"]),
        )


def _upsert_modules(cur, level: str, playlists: dict) -> None:
    for order_index, unit in enumerate(ALL_UNITS):
        cur.execute(
            """
            INSERT INTO modules (id, course_id, category, title, description, order_index, is_optional)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                title = EXCLUDED.title, description = EXCLUDED.description,
                order_index = EXCLUDED.order_index, is_optional = EXCLUDED.is_optional
            """,
            (f"{level}:{unit['key']}", level, unit["key"],
             unit["title"], unit["description"],
             order_index, unit["key"] in OPTIONAL_MODULES),
        )


def _upsert_lesson(cur, lesson: dict) -> None:
    from psycopg.types.json import Jsonb

    cur.execute(
        """
        INSERT INTO lessons (id, module_id, course_id, title, title_nl, title_en, summary, description,
                             youtube_video_id, duration_sec, transcript_text, order_index,
                             is_premium, published_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
        ON CONFLICT (id) DO UPDATE SET
            module_id = EXCLUDED.module_id, course_id = EXCLUDED.course_id,
            title = EXCLUDED.title, title_nl = EXCLUDED.title_nl,
            title_en = EXCLUDED.title_en, summary = EXCLUDED.summary,
            description = EXCLUDED.description, youtube_video_id = EXCLUDED.youtube_video_id,
            duration_sec = EXCLUDED.duration_sec, transcript_text = EXCLUDED.transcript_text,
            order_index = EXCLUDED.order_index, is_premium = EXCLUDED.is_premium,
            published_at = EXCLUDED.published_at, updated_at = now()
        """,
        (lesson["id"], lesson["module_id"], lesson["course_id"], lesson["title"],
         lesson["title_nl"], lesson["title_en"], lesson["summary"], lesson["description"],
         lesson["youtube_video_id"], lesson["duration_sec"], lesson["transcript_text"],
         lesson["order_index"], lesson["is_premium"], lesson["published_at"]),
    )

    # Replace children so upstream deletions propagate.
    for table in _CHILD_TABLES:
        cur.execute(f"DELETE FROM {table} WHERE lesson_id = %s", (lesson["id"],))

    cur.executemany(
        "INSERT INTO lesson_vocabulary (lesson_id, nl, en, order_index) VALUES (%s, %s, %s, %s)",
        [(lesson["id"], v["nl"], v["en"], v["order_index"]) for v in lesson["vocabulary"]],
    )
    cur.executemany(
        "INSERT INTO lesson_key_phrases (lesson_id, phrase, order_index) VALUES (%s, %s, %s)",
        [(lesson["id"], p["phrase"], p["order_index"]) for p in lesson["key_phrases"]],
    )
    cur.executemany(
        "INSERT INTO lesson_grammar_notes (lesson_id, title, explanation, examples, order_index)"
        " VALUES (%s, %s, %s, %s, %s)",
        [(lesson["id"], n["title"], n["explanation"], Jsonb(n["examples"]), n["order_index"])
         for n in lesson["grammar_notes"]],
    )
    cur.executemany(
        "INSERT INTO lesson_transcript (lesson_id, speaker, line_nl, line_en, order_index)"
        " VALUES (%s, %s, %s, %s, %s)",
        [(lesson["id"], t["speaker"], t["line_nl"], t["line_en"], t["order_index"])
         for t in lesson["transcript"]],
    )
    cur.executemany(
        "INSERT INTO lesson_subtitles (lesson_id, lang, vtt_text) VALUES (%s, %s, %s)",
        [(lesson["id"], lang, vtt) for lang, vtt in lesson["subtitles"].items()],
    )
    cur.executemany(
        "INSERT INTO quiz_questions (id, lesson_id, question, options, answer, explanation,"
        " difficulty, skill, order_index) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
        [(q["id"], lesson["id"], q["question"], Jsonb(q["options"]), q["answer"],
          q["explanation"], q["difficulty"], q["skill"], q["order_index"])
         for q in lesson["quiz"]],
    )


def push_to_postgres(lessons: list[dict], database_url: str, prune: bool) -> None:
    import psycopg

    from pipeline import settings

    playlists = settings.PLAYLISTS_CONFIG.get("playlists", {})
    levels = {lesson["course_id"] for lesson in lessons}

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            _upsert_courses(cur, levels)
            for level in sorted(levels | set(COURSE_META)):
                _upsert_modules(cur, level, playlists)
            for lesson in lessons:
                _upsert_lesson(cur, lesson)

            # Drop modules from earlier curriculum versions so renaming or
            # re-splitting units never leaves empty sections behind.
            cur.execute(
                "DELETE FROM modules WHERE NOT (category = ANY(%s))",
                ([unit["key"] for unit in ALL_UNITS],),
            )
            if cur.rowcount:
                LOGGER.info("pruned %d module(s) from a previous curriculum", cur.rowcount)

            if prune:
                cur.execute(
                    "DELETE FROM lessons WHERE NOT (id = ANY(%s))",
                    ([lesson["id"] for lesson in lessons],),
                )
                LOGGER.info("pruned %d stale lessons", cur.rowcount)
        conn.commit()


def main() -> int:
    import os

    parser = argparse.ArgumentParser(description="Export published episodes to the learner app DB")
    parser.add_argument("--dry-run", action="store_true", help="Report only; no writes")
    parser.add_argument("--level", help="Restrict to one CEFR level")
    parser.add_argument("--category", help="Restrict to one category")
    parser.add_argument("--topic", help="Restrict to one topic id")
    parser.add_argument("--json-out", help="Write a JSON snapshot instead of using Postgres")
    parser.add_argument("--prune", action="store_true",
                        help="Delete lessons in Postgres that are no longer exported")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL", ""))
    args = parser.parse_args()

    lessons = collect_lessons(args.level, args.category, args.topic)

    # Curriculum problems are reported even when the run is narrowed to one topic.
    from pipeline.core.db import get_connection
    with get_connection() as conn:
        known = {
            r["id"] for r in conn.execute(
                "SELECT id FROM topics WHERE level = 'A1A2' AND category <> 'dialogue'"
            ).fetchall()
        }
    problems = validate_curriculum(known)
    for problem in problems:
        print(f"  ⚠️  curriculum: {problem}")

    if not lessons:
        print("Nothing to export.")
        return 1 if problems else 0

    by_module: dict[str, int] = {}
    for lesson in lessons:
        by_module[lesson["module_id"]] = by_module.get(lesson["module_id"], 0) + 1

    print(f"lessons ready: {len(lessons)}")
    for unit in ALL_UNITS:
        count = by_module.get(f"A1A2:{unit['key']}", 0)
        if count or unit["key"] not in ("more",):
            optional = " (optional)" if unit["key"] in OPTIONAL_MODULES else ""
            print(f"  {unit['title']:<32} {count:>3}{optional}")
    missing_quiz = [lesson["id"] for lesson in lessons if not lesson["quiz"]]
    if missing_quiz:
        print(f"  ⚠️  {len(missing_quiz)} lesson(s) without a quiz "
              f"(run backfill_quiz): {', '.join(missing_quiz[:5])}")

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(lessons, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✅ Wrote snapshot: {out}")
        return 0

    if args.dry_run:
        return 0

    if not args.database_url:
        print("✗ DATABASE_URL is not set (or pass --database-url / --json-out)", file=sys.stderr)
        return 1

    push_to_postgres(lessons, args.database_url, prune=args.prune)
    print(f"✅ Exported {len(lessons)} lessons")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
