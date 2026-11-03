"""Checks the demo's isolation/reset boundary and reproducible scenario budget."""

import socket
import tempfile
import unittest
from collections import Counter
from datetime import date
from pathlib import Path

import demo


class ProductionSafetyTests(unittest.TestCase):
    def test_reproducible_baseline(self):
        runs = demo.schedule(date(2026, 11, 2))
        self.assertEqual(len(runs), 119)
        self.assertEqual(sum(r["calls"] for r in runs), 297)
        self.assertEqual(
            Counter(r["region"] for r in runs), {"madrid": 59, "navarra": 60}
        )
        self.assertEqual(len({r["slot"].date() for r in runs}), 41)
        self.assertEqual(runs, demo.schedule(date(2026, 11, 2)))
        self.assertEqual(Counter(r["scenario"] for r in runs)["priority-success"], 66)

    def test_settings_cannot_enable_paid_providers(self):
        s = demo.settings()
        self.assertIsNone(s.openai_api_key)
        self.assertIsNone(s.twilio_auth_token)
        self.assertFalse(s.voice_sandbox_enabled)
        self.assertFalse(s.real_telephony_enabled)
        self.assertFalse(s.langsmith_tracing_enabled)
        self.assertEqual(s.ai_extraction_mode, "deterministic")
        self.assertNotIn("backend/booking.db", s.database_url.replace("\\", "/"))

    def test_live_server_blocks_restore(self):
        with socket.socket() as client:
            if client.connect_ex(("127.0.0.1", 18011)) != 0:
                self.skipTest("Run demo:start to exercise the live-server reset guard")
        with self.assertRaisesRegex(AssertionError, "Stop the demo server"):
            demo.restore()

    def test_capture_pool_preserves_sqlite_foreign_keys_across_connections(self):
        from app.db.session import Database
        from sqlalchemy.exc import IntegrityError

        with tempfile.TemporaryDirectory(prefix="baria-video-pool-test-") as folder:
            db = Database(f"sqlite:///{Path(folder) / 'test.db'}")
            demo.configure_capture_pool(db.engine)
            try:
                with db.engine.begin() as connection:
                    connection.exec_driver_sql(
                        "CREATE TABLE parent (id INTEGER PRIMARY KEY)"
                    )
                    connection.exec_driver_sql(
                        "CREATE TABLE child (parent_id INTEGER REFERENCES parent(id))"
                    )
                for _ in range(3):
                    with db.engine.connect() as connection:
                        self.assertEqual(
                            connection.exec_driver_sql("PRAGMA foreign_keys").scalar(),
                            1,
                        )
                        with self.assertRaises(IntegrityError):
                            connection.exec_driver_sql("INSERT INTO child VALUES (999)")
            finally:
                db.engine.dispose()


if __name__ == "__main__":
    unittest.main()
