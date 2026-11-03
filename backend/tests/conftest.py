import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.migrate import upgrade

TOKEN = "test-local-token-with-at-least-24-characters"
IDS = ["madrid-1", "madrid-2", "madrid-3", "navarra-1"]


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        local_api_token=TOKEN,
        admin_api_token=None,
        call_delay_seconds=0.01,
    )


@pytest.fixture
def client(settings):
    upgrade(settings.database_url)
    with TestClient(create_app(settings), headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        yield client


def configuration():
    future = datetime.now(ZoneInfo("Europe/Madrid")) + timedelta(days=14)
    return {
        "customer_name": "Cliente simulado",
        "contact_phone": "+34000000000",
        "requested_date": future.date().isoformat(),
        "preferred_time": "21:00:00",
        "adults": 4,
    }


def make_booking(client, ids=None, config=None):
    response = client.post(
        "/api/bookings",
        json={
            "configuration": configuration() if config is None else config,
            "restaurant_ids": IDS if ids is None else ids,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def current(client, booking_id):
    response = client.get(f"/api/bookings/{booking_id}")
    assert response.status_code == 200, response.text
    return response.json()


def versioned(client, method, path, version, payload=None):
    return client.request(method, path, headers={"If-Match": f'"{version}"'}, json=payload)


def start_booking(client, booking, scenario="priority-success"):
    result = versioned(
        client, "POST", f"/api/bookings/{booking['id']}/start", booking["version"], {"scenario_id": scenario}
    )
    assert result.status_code == 200, result.text
    return result.json()


def wait_for(client, booking_id, states):
    # Cold SQLite/checkpoint I/O on Windows can exceed five seconds while Electron is running.
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        booking = current(client, booking_id)
        if booking["status"] in states:
            return booking
        time.sleep(0.01)
    pytest.fail(f"Timed out waiting for {states}: {booking}")
