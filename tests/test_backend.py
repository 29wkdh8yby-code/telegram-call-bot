from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from app.backend import create_app
from app.config import Settings
from app.database import init_database, session_scope
from app.models import CallRecord


class BackendTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        database_path = Path(self.tempdir.name) / "test.db"
        self.settings = Settings(
            telegram_bot_token="test-token",
            backend_api_base_url="http://127.0.0.1:5000/api",
            database_url=f"sqlite:///{database_path}",
            request_timeout=5,
            status_poll_interval=1,
            default_user_credits=10.0,
            available_numbers=("+12025550111", "+12025550112"),
            trunk_provider_name="test-trunk",
            backend_host="127.0.0.1",
            backend_port=5000,
            log_level="INFO",
        )
        init_database(self.settings.database_url)
        self.app = create_app(self.settings)
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_auth_numbers_and_selection(self) -> None:
        auth_response = self.client.post(
            "/api/auth/telegram",
            json={"telegram_id": 42, "username": "alice", "first_name": "Alice"},
        )
        self.assertEqual(auth_response.status_code, 200)
        self.assertEqual(auth_response.get_json()["user"]["balance_credits"], 10.0)

        numbers_response = self.client.get("/api/numbers")
        self.assertEqual(numbers_response.status_code, 200)
        self.assertEqual(numbers_response.get_json()["numbers"], ["+12025550111", "+12025550112"])

        select_response = self.client.post(
            "/api/users/42/selected-number",
            json={"selected_number": "+12025550112"},
        )
        self.assertEqual(select_response.status_code, 200)
        self.assertEqual(select_response.get_json()["user"]["selected_number"], "+12025550112")

    def test_call_lifecycle_and_history(self) -> None:
        self.client.post(
            "/api/auth/telegram",
            json={"telegram_id": 7, "username": "bob", "first_name": "Bob"},
        )
        place_response = self.client.post(
            "/api/calls",
            json={
                "telegram_id": 7,
                "source_number": "+12025550111",
                "destination_number": "+12025550199",
            },
        )
        self.assertEqual(place_response.status_code, 201)
        call_id = place_response.get_json()["call_id"]

        with session_scope() as session:
            call = session.scalar(select(CallRecord).where(CallRecord.external_call_id == call_id))
            call.started_at = datetime.now(UTC) - timedelta(seconds=25)

        status_response = self.client.get(f"/api/calls/{call_id}")
        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.get_json()["status"], "completed")
        self.assertGreaterEqual(status_response.get_json()["cost"], 0.01)

        history_response = self.client.get("/api/users/7/calls")
        self.assertEqual(history_response.status_code, 200)
        history = history_response.get_json()["calls"]
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["call_id"], call_id)


if __name__ == "__main__":
    unittest.main()
