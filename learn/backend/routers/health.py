from __future__ import annotations

from fastapi import APIRouter

import db

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    checks: dict[str, object] = {}
    try:
        row = await db.fetch_one("SELECT count(*) AS n FROM lessons")
        checks["database"] = True
        checks["lessons"] = row["n"] if row else 0
    except Exception as exc:
        checks["database"] = False
        checks["error"] = str(exc)
    checks["ok"] = bool(checks.get("database"))
    return checks
