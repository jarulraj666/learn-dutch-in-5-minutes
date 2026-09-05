"""Premium exam entitlements — one-time payments grant timed access.

'section' unlocks a single mock-exam section for 3 months; 'full' unlocks
every section. Access is derived from paid, unexpired premium_purchases rows.
"""
from __future__ import annotations

import db

PRICES_CENTS = {"section": 900, "full": 2500}
ENTITLEMENT_DAYS = 90


async def has_section_access(user_id: str, section: str) -> bool:
    row = await db.fetch_one(
        """
        SELECT 1 FROM premium_purchases
        WHERE user_id = %s AND status = 'paid' AND expires_at > now()
          AND (product = 'full' OR (product = 'section' AND section = %s))
        LIMIT 1
        """,
        (user_id, section),
    )
    return row is not None


async def list_active_entitlements(user_id: str) -> list[dict]:
    return await db.fetch_all(
        """
        SELECT product, section, expires_at FROM premium_purchases
        WHERE user_id = %s AND status = 'paid' AND expires_at > now()
        ORDER BY expires_at DESC
        """,
        (user_id,),
    )
