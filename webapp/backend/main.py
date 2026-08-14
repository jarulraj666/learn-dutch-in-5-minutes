"""FastAPI backend for the Dutch Video Generation dashboard."""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from routers import config, health, media, pipeline, publish, topics

LOGGER = logging.getLogger(__name__)


async def _instagram_scheduler_loop() -> None:
    """Every 60 s: find shorts with instagram_scheduled_at <= now and upload them."""
    from services.artifact import find_artifact, load_artifact
    from services.db import get_connection, update_publish_job_artifact_json

    while True:
        try:
            now = datetime.now(timezone.utc)
            # Scan all artifacts in publish_jobs that have artifact_json
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
                changed = False
                for i, short in enumerate(shorts):
                    sched = short.get("instagram_scheduled_at")
                    if not sched:
                        continue
                    if short.get("instagram", {}).get("reel_id"):
                        continue  # already uploaded
                    try:
                        sched_dt = datetime.fromisoformat(sched)
                        if sched_dt.tzinfo is None:
                            sched_dt = sched_dt.replace(tzinfo=timezone.utc)
                    except ValueError:
                        continue
                    if sched_dt > now:
                        continue

                    # Due — upload now
                    artifact_file = find_artifact(topic_id)
                    if not artifact_file:
                        continue
                    disk_artifact = load_artifact(artifact_file)
                    if not disk_artifact:
                        continue

                    LOGGER.info("instagram.scheduler uploading topic=%s scene=%s", topic_id, short.get("scene"))
                    try:
                        from pipeline.stages import stage_upload_short_instagram
                        ig_result = stage_upload_short_instagram(disk_artifact, str(artifact_file), short)
                        disk_artifact["shorts"][i]["instagram"] = ig_result
                        disk_artifact["shorts"][i]["reel_id"] = ig_result.get("reel_id")
                        disk_artifact["shorts"][i]["permalink"] = ig_result.get("permalink")
                        disk_artifact["shorts"][i]["instagram_scheduled_at"] = None
                        artifact_file.write_text(
                            json.dumps(disk_artifact, indent=2, ensure_ascii=False), encoding="utf-8"
                        )
                        update_publish_job_artifact_json(topic_id, disk_artifact)
                        LOGGER.info("instagram.scheduler done topic=%s scene=%s reel_id=%s",
                                    topic_id, short.get("scene"), ig_result.get("reel_id"))
                        changed = True
                    except Exception as exc:
                        LOGGER.warning("instagram.scheduler failed topic=%s scene=%s err=%s",
                                       topic_id, short.get("scene"), exc)
        except Exception as exc:
            LOGGER.warning("instagram.scheduler loop error: %s", exc)

        await asyncio.sleep(60)


async def _facebook_scheduler_loop() -> None:
    """Every 60 s: find shorts with facebook_scheduled_at <= now and upload them."""
    from services.artifact import find_artifact, load_artifact
    from services.db import get_connection, update_publish_job_artifact_json

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

                    artifact_file = find_artifact(topic_id)
                    if not artifact_file:
                        continue
                    disk_artifact = load_artifact(artifact_file)
                    if not disk_artifact:
                        continue

                    LOGGER.info("facebook.scheduler uploading topic=%s scene=%s", topic_id, short.get("scene"))
                    try:
                        from pipeline.stages import stage_upload_short_facebook
                        fb_result = stage_upload_short_facebook(disk_artifact, str(artifact_file), short)
                        disk_artifact["shorts"][i]["facebook"] = fb_result
                        disk_artifact["shorts"][i]["facebook_scheduled_at"] = None
                        artifact_file.write_text(
                            json.dumps(disk_artifact, indent=2, ensure_ascii=False), encoding="utf-8"
                        )
                        update_publish_job_artifact_json(topic_id, disk_artifact)
                        LOGGER.info("facebook.scheduler done topic=%s scene=%s post_id=%s",
                                    topic_id, short.get("scene"), fb_result.get("post_id"))
                    except Exception as exc:
                        LOGGER.warning("facebook.scheduler failed topic=%s scene=%s err=%s",
                                       topic_id, short.get("scene"), exc)
        except Exception as exc:
            LOGGER.warning("facebook.scheduler loop error: %s", exc)

        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks = [
        asyncio.create_task(_instagram_scheduler_loop()),
        asyncio.create_task(_facebook_scheduler_loop()),
    ]
    LOGGER.info("instagram.scheduler + facebook.scheduler started")
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

app.include_router(health.router, prefix="/api")
app.include_router(topics.router, prefix="/api")
app.include_router(pipeline.router, prefix="/api")
app.include_router(publish.router, prefix="/api")
app.include_router(media.router, prefix="/api")
app.include_router(config.router, prefix="/api")

# Serve output files (audio, video, images) statically
output_dir = ROOT / "output"
if output_dir.exists():
    app.mount("/output", StaticFiles(directory=str(output_dir)), name="output")
