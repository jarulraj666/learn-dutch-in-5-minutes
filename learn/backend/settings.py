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
SPEAKING_WORKER_TOKEN = os.environ.get("SPEAKING_WORKER_TOKEN", "")
R2_ENDPOINT_URL = os.environ.get("R2_ENDPOINT_URL", "")
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET = os.environ.get("R2_BUCKET", "")

# Mollie (payments). Test API keys start with "test_", live keys with "live_".
MOLLIE_API_KEY = os.environ.get("MOLLIE_API_KEY", "")
# Must be a publicly reachable URL so Mollie's servers can call the webhook.
API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8001").rstrip("/")

# Stripe (payments). Test secret keys start with "sk_test_", live with "sk_live_".
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

# Which provider /billing/checkout uses: "mollie" or "stripe".
PAYMENT_PROVIDER = os.environ.get("PAYMENT_PROVIDER", "stripe")
