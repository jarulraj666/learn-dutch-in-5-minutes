"""End-to-end checks for the learner API against a live Postgres.

    DATABASE_URL=... LEARN_API=http://127.0.0.1:8001 python learn/backend/tests/smoke.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
import uuid

import psycopg

API = os.environ.get("LEARN_API", "http://127.0.0.1:8001")
DATABASE_URL = os.environ["DATABASE_URL"]

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"{'PASS' if condition else 'FAIL'}  {name}{f' — {detail}' if detail and not condition else ''}")
    if not condition:
        failures.append(name)


def request(method: str, path: str, token: str | None = None, body: dict | None = None):
    req = urllib.request.Request(
        f"{API}{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    try:
        with urllib.request.urlopen(req) as res:
            payload = res.read()
            return res.status, json.loads(payload) if payload else None
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        try:
            return exc.code, json.loads(payload) if payload else None
        except json.JSONDecodeError:
            return exc.code, payload.decode(errors="replace")


def seed_user(conn, email: str, role: str = "learner") -> str:
    token = f"test-{uuid.uuid4()}"
    user_id = conn.execute(
        "INSERT INTO users (name, email, role) VALUES (%s, %s, %s) RETURNING id",
        ("Test Learner", email, role),
    ).fetchone()[0]
    conn.execute(
        'INSERT INTO sessions ("userId", expires, "sessionToken")'
        " VALUES (%s, now() + interval '1 day', %s)",
        (user_id, token),
    )
    return token


def main() -> int:
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        learner = seed_user(conn, f"learner-{uuid.uuid4()}@example.com")
        admin = seed_user(conn, f"admin-{uuid.uuid4()}@example.com", role="admin")

        lesson = conn.execute(
            """
            SELECT l.id, l.course_id, l.duration_sec
            FROM lessons l
            JOIN modules m ON m.id = l.module_id
            WHERE NOT m.is_optional
              AND EXISTS (SELECT 1 FROM quiz_questions q WHERE q.lesson_id = l.id)
            ORDER BY l.id LIMIT 1
            """
        ).fetchone()
        if not lesson:
            print("No lesson with a quiz found — run the exporter first.")
            return 1
        lesson_id, course_id, duration = lesson

        status, health = request("GET", "/api/health")
        check("health ok", status == 200 and health["ok"], str(health))

        status, courses = request("GET", "/api/courses")
        check("courses public", status == 200 and len(courses) >= 1, str(status))

        status, detail = request("GET", f"/api/courses/{course_id}")
        categories = [m["category"] for m in detail["modules"]]
        check("start here comes first", categories[0] == "start_here", str(categories[:2]))
        check("dialogue comes last", categories[-1] == "dialogue", str(categories[-2:]))
        check("course is split into progressive units", len(categories) >= 5, str(categories))

        start_here = next(m for m in detail["modules"] if m["category"] == "start_here")
        ids = [l["id"] for l in start_here["lessons"]]
        check("start here stays an onboarding ramp", 0 < len(ids) <= 15, f"{len(ids)} lessons")

        # Grammar must arrive early rather than being deferred to the end.
        check("present tense is taught in the first unit",
              "grammar_present_tense" in ids, str(ids))

        # Units must mix lesson types instead of grouping by generation category.
        mixed = [
            m["category"] for m in detail["modules"]
            if m["category"] not in ("start_here", "dialogue")
            and len({l["id"].split("_")[0] for l in m["lessons"]}) > 1
        ]
        check("units mix vocabulary, words and grammar",
              len(mixed) >= 4, f"only {len(mixed)} mixed units")

        all_ids = [l["id"] for m in detail["modules"] for l in m["lessons"]]
        check("no lesson appears in two modules", len(all_ids) == len(set(all_ids)))
        check("dialogue is the only optional module",
              [m["category"] for m in detail["modules"] if m["is_optional"]] == ["dialogue"],
              str([m["category"] for m in detail["modules"] if m["is_optional"]]))

        optional_lessons = sum(
            len(m["lessons"]) for m in detail["modules"] if m["is_optional"]
        )
        required_lessons = sum(
            len(m["lessons"]) for m in detail["modules"] if not m["is_optional"]
        )
        check("lesson_count excludes optional",
              detail["lesson_count"] == required_lessons
              and detail["optional_lesson_count"] == optional_lessons,
              f"{detail['lesson_count']} vs {required_lessons}")

        status, lesson_detail = request("GET", f"/api/lessons/{lesson_id}")
        check("lesson loads", status == 200, str(status))
        check("quiz hides answers",
              all("answer" not in q for q in lesson_detail["quiz"]),
              "answer leaked to client")
        check("lesson has vocabulary", len(lesson_detail["vocabulary"]) > 0)

        status, _ = request("POST", "/api/progress",
                            body={"lesson_id": lesson_id, "position_sec": 10,
                                  "watched_sec": 10, "duration_sec": duration or 300})
        check("progress requires auth", status == 401, f"got {status}")

        status, result = request("POST", "/api/progress", token=learner,
                                 body={"lesson_id": lesson_id, "position_sec": 10,
                                       "watched_sec": 10, "duration_sec": 100})
        check("progress 10% not complete", status == 200 and result["percent"] == 10
              and not result["completed"], str(result))

        status, result = request("POST", "/api/progress", token=learner,
                                 body={"lesson_id": lesson_id, "position_sec": 95,
                                       "watched_sec": 95, "duration_sec": 100})
        check("progress 95% completes", result["percent"] == 95 and result["completed"], str(result))

        status, result = request("POST", "/api/progress", token=learner,
                                 body={"lesson_id": lesson_id, "position_sec": 20,
                                       "watched_sec": 5, "duration_sec": 100})
        check("progress never regresses", result["percent"] == 95 and result["completed"], str(result))

        answers = conn.execute(
            "SELECT id, answer FROM quiz_questions WHERE lesson_id = %s ORDER BY order_index",
            (lesson_id,),
        ).fetchall()

        wrong = {qid: "definitely not the answer" for qid, _ in answers}
        status, quiz = request("POST", f"/api/lessons/{lesson_id}/quiz/submit",
                               token=learner, body={"answers": wrong})
        check("all wrong scores 0", quiz["score"] == 0 and quiz["percent"] == 0, str(quiz))
        check("explanations returned after grading",
              all("explanation" in r for r in quiz["results"]))

        status, cert = request("GET", f"/api/courses/{course_id}/certificate", token=learner)
        check("certificate blocked while incomplete", not cert["eligible"], str(cert))

        status, _ = request("POST", f"/api/courses/{course_id}/certificate", token=learner)
        check("certificate claim rejected", status == 403, f"got {status}")

        status, quiz = request("POST", f"/api/lessons/{lesson_id}/quiz/submit",
                               token=learner, body={"answers": dict(answers)})
        check("all right scores 100", quiz["percent"] == 100, str(quiz))
        check("attempt number increments", quiz["attempt_no"] == 2, str(quiz["attempt_no"]))

        status, _ = request("POST", f"/api/lessons/{lesson_id}/quiz/submit",
                            token=learner, body={"answers": {"bogus-id": "x"}})
        check("unknown question id rejected", status == 400, f"got {status}")

        status, cards = request("GET", "/api/flashcards/due", token=learner)
        check("flashcards from completed lesson", status == 200 and len(cards) > 0, str(status))

        if cards:
            status, state = request("POST", "/api/flashcards/review", token=learner,
                                    body={"vocab_id": cards[0]["vocab_id"], "quality": 5})
            check("sm2 first interval is 1 day", state["interval_days"] == 1, str(state))
            status, state = request("POST", "/api/flashcards/review", token=learner,
                                    body={"vocab_id": cards[0]["vocab_id"], "quality": 5})
            check("sm2 second interval is 6 days", state["interval_days"] == 6, str(state))

        status, _ = request("GET", "/api/admin/stats", token=learner)
        check("admin blocked for learner", status == 403, f"got {status}")

        status, stats = request("GET", "/api/admin/stats", token=admin)
        check("admin allowed", status == 200 and stats["learners"] >= 2, str(status))

        status, _ = request("GET", "/api/me/dashboard", token=learner)
        check("dashboard ok", status == 200, f"got {status}")

        status, _ = request("GET", "/api/lessons/does-not-exist")
        check("missing lesson is 404", status == 404, f"got {status}")

    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
