from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pipeline import settings
from pipeline.core.db import (
    claim_facebook_reel_upload,
    claim_instagram_reel_upload,
    complete_facebook_reel_upload,
    complete_instagram_reel_upload,
    get_connection,
)


class FacebookUploadClaimTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.original_db_path = settings.DB_PATH
        settings.DB_PATH = Path(self.tempdir.name) / "content.db"
        schema = (settings.ROOT / "db" / "schema.sql").read_text(encoding="utf-8")
        artifact = {
            "shorts": [
                {"scene": 1, "facebook_scheduled_at": "2026-09-01T00:00:00+00:00"},
                {"scene": 2, "instagram_scheduled_at": "2026-09-01T00:00:00+00:00"},
            ]
        }
        with get_connection() as conn:
            conn.executescript(schema)
            conn.execute("INSERT INTO topics (id, track, title_hint) VALUES ('topic', 'daily', 'Test')")
            conn.execute(
                "INSERT INTO canonical_scripts (topic_id, language, title, script_json, fingerprint, created_at) "
                "VALUES ('topic', 'nl', 'Test', '{}', 'fingerprint', '2026-09-01T00:00:00+00:00')"
            )
            conn.execute(
                "INSERT INTO publish_jobs (canonical_script_id, playlist_track, scheduled_at, status, artifact_json, created_at) "
                "VALUES (1, 'daily', '2026-09-01T00:00:00+00:00', 'ready', ?, '2026-09-01T00:00:00+00:00')",
                [json.dumps(artifact)],
            )

    def tearDown(self) -> None:
        settings.DB_PATH = self.original_db_path
        self.tempdir.cleanup()

    def test_claim_prevents_duplicate_upload_and_completion_is_final(self) -> None:
        claim = claim_facebook_reel_upload("topic", 1)
        self.assertIsNotNone(claim)
        claim_id, _, _ = claim

        self.assertIsNone(claim_facebook_reel_upload("topic", 1))
        self.assertTrue(
            complete_facebook_reel_upload("topic", 1, claim_id, {"post_id": "123", "video_id": "456"})
        )
        self.assertIsNone(claim_facebook_reel_upload("topic", 1))

    def test_instagram_claim_prevents_duplicate_upload_and_completion_is_final(self) -> None:
        claim = claim_instagram_reel_upload("topic", 2)
        self.assertIsNotNone(claim)
        claim_id, _, _ = claim

        self.assertIsNone(claim_instagram_reel_upload("topic", 2))
        self.assertTrue(
            complete_instagram_reel_upload("topic", 2, claim_id, {"reel_id": "123", "permalink": "https://instagram.example/reel/123"})
        )
        self.assertIsNone(claim_instagram_reel_upload("topic", 2))


if __name__ == "__main__":
    unittest.main()