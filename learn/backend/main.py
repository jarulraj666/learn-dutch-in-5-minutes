"""Public learner API.

Deliberately separate from webapp/backend: that service is an unauthenticated
internal ops dashboard that can trigger the pipeline and publish to social
platforms. Nothing from it is mounted here.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import db
import settings
from routers import admin, auth, catalog, certificates, exam, feedback, flashcards, health, me, progress, quiz

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
LOGGER = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await db.open_pool()
    LOGGER.info("learn-api ready (origins=%s)", settings.ALLOWED_ORIGINS)
    try:
        yield
    finally:
        await db.close_pool()


app = FastAPI(title="Learn Dutch in 5 Minutes API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

for module in (health, auth, catalog, progress, quiz, flashcards, certificates, me, feedback, exam, admin):
    app.include_router(module.router, prefix="/api")
