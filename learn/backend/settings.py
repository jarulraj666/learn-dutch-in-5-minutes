from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent.parent

load_dotenv(ROOT / ".env")
load_dotenv(ROOT / "learn" / "frontend" / ".env.local")
load_dotenv(ROOT / "learn" / ".env", override=True)

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Browser origins allowed to call this API directly. The Next.js server-side
# proxy is the normal path, so this list stays short.
ALLOWED_ORIGINS = [
    o.strip() for o in os.environ.get(
        "LEARN_ALLOWED_ORIGINS",
        "http://localhost:3001,https://learndutchin5minutes.nl,https://www.learndutchin5minutes.nl",
    ).split(",") if o.strip()
]

# Emails promoted to admin on sign-in. Comma separated.
ADMIN_EMAILS = {
    e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()
}

# A lesson counts as watched at this percentage.
COMPLETION_PERCENT = int(os.environ.get("LEARN_COMPLETION_PERCENT", "90"))

# Minimum quiz score (percent) required for a certificate.
CERTIFICATE_PASS_PERCENT = int(os.environ.get("LEARN_CERTIFICATE_PASS_PERCENT", "70"))

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.environ.get(
    "GOOGLE_REDIRECT_URI",
    os.environ.get(
        "FRONTEND_URL",
        os.environ.get("NEXTAUTH_URL", "https://learndutchin5minutes.nl"),
    ).rstrip("/") + "/api/auth/google/callback",
)
FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://learndutchin5minutes.nl").rstrip("/")
AUTH_STATE_SECRET = os.environ.get("AUTH_STATE_SECRET") or os.environ.get("AUTH_SECRET", "")
