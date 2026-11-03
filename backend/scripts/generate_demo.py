"""Generate recorded deterministic runs in a NEW isolated directory, without providers."""

import argparse
import json
import secrets
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.migrate import upgrade


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--bookings", type=int, default=1, choices=range(1, 101), metavar="1..100")
    args = parser.parse_args()
    directory = args.directory.resolve()
    directory.mkdir(parents=True, exist_ok=False)
    local, admin = secrets.token_urlsafe(36), secrets.token_urlsafe(36)
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{(directory / 'booking.db').as_posix()}",
        local_api_token=local,
        admin_api_token=admin,
        seed_mock_data=True,
        ai_extraction_mode="deterministic",
        openai_api_key=None,
        twilio_account_sid=None,
        twilio_auth_token=None,
        real_telephony_enabled=False,
        voice_sandbox_enabled=False,
        langsmith_tracing_enabled=False,
        call_delay_seconds=0,
    )
    # Only this private file contains the generated credentials. Never print them.
    (directory / ".env").write_text(
        f"DATABASE_URL={settings.database_url}\nLOCAL_API_TOKEN={local}\nADMIN_API_TOKEN={admin}\n"
        "SEED_MOCK_DATA=true\nAI_EXTRACTION_MODE=deterministic\nREAL_TELEPHONY_ENABLED=false\n"
        "VOICE_SANDBOX_ENABLED=false\nLANGSMITH_TRACING_ENABLED=false\n",
        encoding="utf-8",
    )
    upgrade(settings.database_url)
    future = datetime.now(ZoneInfo("Europe/Madrid")) + timedelta(days=14)
    completed = []
    with TestClient(create_app(settings)) as client:
        client.headers["Authorization"] = f"Bearer {local}"
        for _ in range(args.bookings):
            response = client.post(
                "/api/bookings",
                json={
                    "configuration": {
                        "customer_name": "Demo Guest",
                        "contact_phone": "+34000000000",
                        "requested_date": future.date().isoformat(),
                        "preferred_time": "21:00",
                        "adults": 4,
                        "flexibility_minutes": 30,
                    },
                    "restaurant_ids": ["madrid-1", "madrid-2", "madrid-3"],
                },
            )
            response.raise_for_status()
            booking = response.json()
            response = client.post(
                f"/api/bookings/{booking['id']}/start",
                headers={"If-Match": str(booking["version"])},
                json={"mode": "ai_simulation", "scenario_id": "priority-success"},
            )
            response.raise_for_status()
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                response = client.get(f"/api/bookings/{booking['id']}")
                response.raise_for_status()
                result = response.json()
                if result["status"] in {"CONFIRMED", "FAILED", "EXHAUSTED", "WAITING_FOR_USER"}:
                    break
                time.sleep(0.05)
            else:
                raise SystemExit("Timed out waiting for the deterministic workflow.")
            if result["status"] != "CONFIRMED" or result["summary"]["completed_attempts"] != 3:
                raise SystemExit("Unexpected deterministic simulation result.")
            completed.append({"booking_id": booking["id"], "attempts": 3, "status": result["status"]})
            print(f"Recorded simulation {len(completed)}/{args.bookings}: three attempts, confirmed.")
    (directory / "manifest.json").write_text(
        json.dumps({"mode": "ai_simulation", "external_calls": 0, "bookings": completed}, indent=2),
        encoding="utf-8",
    )
    print("Isolated archive ready. See INSTALLATION.md for launch instructions.")


if __name__ == "__main__":
    main()
