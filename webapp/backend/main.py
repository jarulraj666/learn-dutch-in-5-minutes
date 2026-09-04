"""FastAPI backend for the Dutch Video Generation dashboard."""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Make the project root importable so pipeline.settings etc. work
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

# Load .env from project root so INSTAGRAM_*, YOUTUBE_*, GEMINI_* vars are available
_env_file = ROOT / ".env"
if _env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_file, override=False)
    except ImportError:
        # dotenv not installed — fall back to manual parse
        for line in _env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                import os
                os.environ.setdefault(k.strip(), v.strip())

# Reuse the learner app's local database configuration for mock-exam exports.
# Platform-provided values always take precedence.
_learner_env_file = ROOT / "learn" / ".env"
if _learner_env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_learner_env_file, override=False)
    except ImportError:
        for line in _learner_env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                import os
                os.environ.setdefault(k.strip(), v.strip())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from routers import config, health, media, mock_exams, pipeline, publish, topics

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
LOGGER = logging.getLogger(__name__)


async def _sleep_until_next_hour(scheduler: str) -> None:
    """Block until the next rounded hour (13:00, 14:00, ...) in local time."""
    now = datetime.now().astimezone()
    next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    delay = (next_hour - now).total_seconds()
    LOGGER.info("%s.scheduler sleeping %.0fs until %s", scheduler, delay, next_hour.isoformat())
    await asyncio.sleep(delay)


async def _instagram_scheduler_loop() -> None:
    """Hourly, on the rounded hour: upload shorts with instagram_scheduled_at <= now."""
    from services.db import get_connection

    await _sleep_until_next_hour("instagram")
    while True:
        try:
            now = datetime.now(timezone.utc)
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT t.id AS topic_id, pj.artifact_json "
                    "FROM topics t "
                    "JOIN canonical_scripts cs ON cs.topic_id = t.id "
                    "  AND cs.id = (SELECT MAX(id) FROM canonical_scripts WHERE topic_id = t.id) "
                    "JOIN publish_jobs pj ON pj.canonical_script_id = cs.id "
                    "  AND pj.id = (SELECT MAX(id) FROM publish_jobs WHERE canonical_script_id = cs.id) "
                    "WHERE pj.artifact_json IS NOT NULL"
                ).fetchall()

            for row in rows:
                topic_id = row["topic_id"]
                try:
                    artifact = json.loads(row["artifact_json"])
                except Exception:
                    continue

                shorts = artifact.get("shorts") or []
                for i, short in enumerate(shorts):
                    sched = short.get("instagram_scheduled_at")
                    if not sched or short.get("instagram", {}).get("reel_id"):
                        continue
                    try:
                        sched_dt = datetime.fromisoformat(sched)
                        if sched_dt.tzinfo is None:
                            sched_dt = sched_dt.replace(tzinfo=timezone.utc)
                    except ValueError:
                        continue
                    if sched_dt > now:
                        continue

                    scene = short.get("scene", i)
                    from pipeline.core.db import claim_instagram_reel_upload
                    claimed = claim_instagram_reel_upload(topic_id, scene)
                    if not claimed:
                        continue
                    claim_id, claimed_artifact, claimed_short = claimed
                    pending_container_id = (
                        claimed_short.get("instagram_pending_container") or {}
                    ).get("id", "")
                    LOGGER.info("instagram.scheduler uploading topic=%s scene=%s container=%s",
                                topic_id, scene, pending_container_id or "-")
                    try:
                        from pipeline.stages import stage_upload_short_instagram
                        from pipeline.core.db import (
                            complete_instagram_reel_upload,
                            record_instagram_pending_container,
                        )

                        def _persist_container(container_id: str, _scene=scene, _claim=claim_id) -> None:
                            record_instagram_pending_container(topic_id, _scene, _claim, container_id)

                        ig_result = await asyncio.to_thread(
                            stage_upload_short_instagram,
                            claimed_artifact,
                            claimed_short,
                            pending_container_id,
                            _persist_container,
                        )
                        complete_instagram_reel_upload(topic_id, scene, claim_id, ig_result)
                        LOGGER.info("instagram.scheduler done topic=%s scene=%s reel_id=%s",
                                    topic_id, scene, ig_result.get("reel_id"))
                    except Exception as exc:
                        from pipeline.core.db import release_instagram_reel_upload_claim
                        release_instagram_reel_upload_claim(topic_id, scene, claim_id)
                        LOGGER.warning("instagram.scheduler failed topic=%s scene=%s err=%s",
                                       topic_id, scene, exc)
        except Exception as exc:
            LOGGER.warning("instagram.scheduler loop error: %s", exc)

        await _sleep_until_next_hour("instagram")


async def _facebook_scheduler_loop() -> None:
    """Hourly, on the rounded hour: upload shorts with facebook_scheduled_at <= now."""
    from services.db import get_connection, update_publish_job_artifact_json

    await _sleep_until_next_hour("facebook")
    while True:
        try:
            now = datetime.now(timezone.utc)
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT t.id AS topic_id, pj.artifact_json "
                    "FROM topics t "
                    "JOIN canonical_scripts cs ON cs.topic_id = t.id "
                    "  AND cs.id = (SELECT MAX(id) FROM canonical_scripts WHERE topic_id = t.id) "
                    "JOIN publish_jobs pj ON pj.canonical_script_id = cs.id "
                    "  AND pj.id = (SELECT MAX(id) FROM publish_jobs WHERE canonical_script_id = cs.id) "
                    "WHERE pj.artifact_json IS NOT NULL"
                ).fetchall()

            for row in rows:
                topic_id = row["topic_id"]
                try:
                    artifact = json.loads(row["artifact_json"])
                except Exception:
                    continue

                for i, short in enumerate(artifact.get("shorts") or []):
                    sched = short.get("facebook_scheduled_at")
                    if not sched or short.get("facebook", {}).get("post_id"):
                        continue
                    try:
                        sched_dt = datetime.fromisoformat(sched)
                        if sched_dt.tzinfo is None:
                            sched_dt = sched_dt.replace(tzinfo=timezone.utc)
                    except ValueError:
                        continue
                    if sched_dt > now:
                        continue

                    scene = short.get("scene", i)
                    from pipeline.core.db import claim_facebook_reel_upload
                    claimed = claim_facebook_reel_upload(topic_id, scene)
                    if not claimed:
                        continue
                    claim_id, claimed_artifact, claimed_short = claimed
                    LOGGER.info("facebook.scheduler uploading topic=%s scene=%s", topic_id, scene)
                    try:
                        from pipeline.stages import stage_upload_short_facebook
                        from pipeline.core.db import complete_facebook_reel_upload
                        fb_result = await asyncio.to_thread(
                            stage_upload_short_facebook, claimed_artifact, claimed_short
                        )
                        complete_facebook_reel_upload(topic_id, scene, claim_id, fb_result)
                        LOGGER.info("facebook.scheduler done topic=%s scene=%s post_id=%s",
                                    topic_id, scene, fb_result.get("post_id"))
                    except Exception as exc:
                        from pipeline.core.db import release_facebook_reel_upload_claim
                        release_facebook_reel_upload_claim(topic_id, scene, claim_id)
                        LOGGER.warning("facebook.scheduler failed topic=%s scene=%s err=%s",
                                       topic_id, scene, exc)
        except Exception as exc:
            LOGGER.warning("facebook.scheduler loop error: %s", exc)

        await _sleep_until_next_hour("facebook")


async def _tiktok_scheduler_loop() -> None:
    """Hourly, on the rounded hour: upload shorts with tiktok_scheduled_at <= now."""
    import os
    from services.db import get_connection, update_publish_job_artifact_json

    await _sleep_until_next_hour("tiktok")
    while True:
        try:
            if os.getenv("UPLOAD_TIKTOK", "true").lower() not in ("1", "true", "yes"):
                await _sleep_until_next_hour("tiktok")
                continue
            now = datetime.now(timezone.utc)
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT t.id AS topic_id, pj.artifact_json "
                    "FROM topics t "
                    "JOIN canonical_scripts cs ON cs.topic_id = t.id "
                    "  AND cs.id = (SELECT MAX(id) FROM canonical_scripts WHERE topic_id = t.id) "
                    "JOIN publish_jobs pj ON pj.canonical_script_id = cs.id "
                    "  AND pj.id = (SELECT MAX(id) FROM publish_jobs WHERE canonical_script_id = cs.id) "
                    "WHERE pj.artifact_json IS NOT NULL"
                ).fetchall()

            for row in rows:
                topic_id = row["topic_id"]
                try:
                    artifact = json.loads(row["artifact_json"])
                except Exception:
                    continue

                for i, short in enumerate(artifact.get("shorts") or []):
                    sched = short.get("tiktok_scheduled_at")
                    if not sched or short.get("tiktok", {}).get("publish_id"):
                        continue
                    try:
                        sched_dt = datetime.fromisoformat(sched)
                        if sched_dt.tzinfo is None:
                            sched_dt = sched_dt.replace(tzinfo=timezone.utc)
                    except ValueError:
                        continue
                    if sched_dt > now:
                        continue

                    LOGGER.info("tiktok.scheduler uploading topic=%s scene=%s", topic_id, short.get("scene"))
                    try:
                        from pipeline.stages import stage_upload_short_tiktok
                        tt_result = stage_upload_short_tiktok(artifact, short)
                        artifact["shorts"][i]["tiktok"] = tt_result
                        artifact["shorts"][i]["tiktok_scheduled_at"] = None
                        update_publish_job_artifact_json(topic_id, artifact)
                        LOGGER.info("tiktok.scheduler done topic=%s scene=%s publish_id=%s",
                                    topic_id, short.get("scene"), tt_result.get("publish_id"))
                    except Exception as exc:
                        LOGGER.warning("tiktok.scheduler failed topic=%s scene=%s err=%s",
                                       topic_id, short.get("scene"), exc)
        except Exception as exc:
            LOGGER.warning("tiktok.scheduler loop error: %s", exc)

        await _sleep_until_next_hour("tiktok")


@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks = [
        asyncio.create_task(_instagram_scheduler_loop()),
        asyncio.create_task(_facebook_scheduler_loop()),
        asyncio.create_task(_tiktok_scheduler_loop()),
    ]
    LOGGER.info("instagram.scheduler + facebook.scheduler + tiktok.scheduler started (hourly)")
    yield
    for t in tasks:
        t.cancel()


app = FastAPI(title="Dutch Video Generation Dashboard", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def no_cache_middleware(request, call_next):
    """Disable all caching so regenerated media/config is never served stale."""
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


app.include_router(health.router, prefix="/api")
app.include_router(topics.router, prefix="/api")
app.include_router(pipeline.router, prefix="/api")
app.include_router(publish.router, prefix="/api")
app.include_router(media.router, prefix="/api")
app.include_router(config.router, prefix="/api")
app.include_router(mock_exams.router, prefix="/api")

# Serve output files (audio, video, images) statically
output_dir = ROOT / "output"
if output_dir.exists():
    app.mount("/output", StaticFiles(directory=str(output_dir)), name="output")
