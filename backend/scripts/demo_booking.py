"""Exercise the running local API with simulation data only."""

import argparse
import json
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from app.core.config import get_settings

settings = get_settings()
parser = argparse.ArgumentParser()
parser.add_argument("--mode", choices=["simulation", "ai_simulation"], default="simulation")
arguments = parser.parse_args()
future = datetime.now(ZoneInfo("Europe/Madrid")) + timedelta(days=14)
with httpx.Client(
    base_url=f"http://{settings.host}:{settings.port}",
    headers={"Authorization": f"Bearer {settings.local_api_token.get_secret_value()}"},
    timeout=10,
) as client:
    response = client.post(
        "/api/bookings",
        json={
            "configuration": {
                "customer_name": "Cliente simulado",
                "contact_phone": "+34000000000",
                "requested_date": future.date().isoformat(),
                "preferred_time": "21:00",
                "adults": 4,
            },
            "restaurant_ids": ["madrid-1", "madrid-2", "madrid-3", "navarra-1"],
        },
    )
    response.raise_for_status()
    booking = response.json()
    started = client.post(
        f"/api/bookings/{booking['id']}/start",
        headers={"If-Match": f'"{booking["version"]}"'},
        json={"scenario_id": "priority-success", "mode": arguments.mode},
    )
    started.raise_for_status()
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        response = client.get(f"/api/bookings/{booking['id']}")
        response.raise_for_status()
        result = response.json()
        if result["status"] in {"CONFIRMED", "EXHAUSTED", "CANCELLED", "FAILED", "WAITING_FOR_USER"}:
            print(json.dumps(result["summary"], indent=2, ensure_ascii=False))
            if result["status"] != "CONFIRMED" or result["summary"]["completed_attempts"] != 3:
                raise SystemExit("Unexpected simulation outcome")
            break
        time.sleep(0.1)
    else:
        raise SystemExit("Simulation did not finish in 30 seconds")
