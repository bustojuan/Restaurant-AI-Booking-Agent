import time

import pytest
from conftest import IDS, TOKEN, configuration, current, make_booking, start_booking, versioned, wait_for
from fastapi.testclient import TestClient

from app.main import create_app
from app.migrate import upgrade
from app.providers.calls import MockCallProvider
from app.schemas import EventOut


def test_priority_end_to_end_summary_and_history(client):
    booking = make_booking(client)
    start_booking(client, booking)
    result = wait_for(client, booking["id"], {"CONFIRMED"})
    summary = result["summary"]
    assert summary["party_size"] == 4
    assert summary["total_restaurants"] == 4
    assert summary["completed_attempts"] == 3
    assert [a["restaurant_id"] for a in summary["contacted_restaurants"]] == IDS[:3]
    assert [a["result"] for a in summary["contacted_restaurants"]] == [
        "NO_AVAILABILITY",
        "INCOMPATIBLE_OFFER",
        "CONFIRMED",
    ]
    assert [r["id"] for r in summary["pending_restaurants"]] == [IDS[3]]
    assert summary["confirmation"]["restaurant_id"] == IDS[2]
    assert summary["confirmation"]["simulated"] is True
    assert summary["current_restaurant"] is None
    assert summary["current_call_status"] is None
    assert summary["pending_approvals"] == []
    assert all(a["duration_ms"] >= 0 for a in summary["contacted_restaurants"])
    history = client.get("/api/bookings?status=CONFIRMED").json()
    assert history["items"][0] == summary
    events = client.get(f"/api/bookings/{booking['id']}/events?limit=100").json()["items"]
    assert events[0]["event_type"] == "booking.created"
    assert events[-1]["event_type"] == "booking.confirmed"
    assert events[-1]["payload"]["summary"] == summary
    assert len([e for e in events if e["event_type"] == "call.started"]) == 3
    assert client.get(f"/api/bookings/{booking['id']}/offers").status_code == 200


@pytest.mark.parametrize(
    "scenario,result",
    [
        ("all-full", "NO_AVAILABILITY"),
        ("timeout", "TIMEOUT"),
        ("errors", "ERROR"),
        ("no-confirmation", "NOT_CONFIRMED"),
    ],
)
def test_exhaustion_timeout_error_and_missing_confirmation(client, scenario, result):
    booking = make_booking(client, ids=IDS[:2])
    start_booking(client, booking, scenario)
    finished = wait_for(client, booking["id"], {"EXHAUSTED"})["summary"]
    assert finished["confirmation"] is None
    assert finished["completed_attempts"] == 2
    assert finished["pending_restaurants"] == []
    assert all(a["result"] == result for a in finished["contacted_restaurants"])


@pytest.mark.parametrize("approve,expected", [(True, "CONFIRMED"), (False, "EXHAUSTED")])
def test_approval_and_rejection(client, approve, expected):
    booking = make_booking(client, ids=IDS[:1])
    start_booking(client, booking, "approval")
    waiting = wait_for(client, booking["id"], {"WAITING_FOR_USER"})
    summary = waiting["summary"]
    assert summary["confirmation"] is None
    assert summary["current_restaurant"]["id"] == IDS[0]
    assert summary["current_call_status"] == "COMPLETED"
    assert summary["completed_attempts"] == 1
    assert len(summary["pending_approvals"]) == 1
    offer_id = summary["pending_approvals"][0]["id"]
    response = versioned(
        client,
        "POST",
        f"/api/bookings/{booking['id']}/decisions",
        waiting["version"],
        {"offer_id": offer_id, "approve": approve},
    )
    assert response.status_code == 200
    result = wait_for(client, booking["id"], {expected})
    assert result["summary"]["pending_approvals"] == []
    assert bool(result["summary"]["confirmation"]) == approve


@pytest.mark.parametrize("state", ["RUNNING", "WAITING_FOR_USER", "CONFIRMED"])
def test_edit_and_delete_restrictions(client, state):
    booking = make_booking(client, ids=IDS[:1])
    if state == "RUNNING":
        client.app.state.executor.provider = MockCallProvider(1)
    start_booking(client, booking, "approval" if state == "WAITING_FOR_USER" else "confirm-first")
    wait_for(client, booking["id"], {state})
    base = f"/api/bookings/{booking['id']}"
    for method, path, body in [
        ("PATCH", base, {"configuration": {"notes": "not allowed"}}),
        ("POST", base + "/restaurants", {"restaurant_id": IDS[1]}),
        ("PUT", base + "/restaurants/order", {"restaurant_ids": IDS[:1]}),
        ("DELETE", base + f"/restaurants/{IDS[0]}", None),
        ("DELETE", base, None),
    ]:
        version = current(client, booking["id"])["version"]
        response = versioned(client, method, path, version, body)
        assert response.status_code == 409
    latest = current(client, booking["id"])
    assert latest["configuration"] == booking["configuration"]
    assert len(latest["restaurants"]) == 1


def test_cancel_ignores_late_result(client):
    client.app.state.executor.provider = MockCallProvider(0.15)
    booking = make_booking(client)
    start_booking(client, booking, "confirm-first")
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        running = current(client, booking["id"])
        if running["summary"]["current_call_status"] == "RUNNING":
            break
        time.sleep(0.005)
    assert running["summary"]["current_restaurant"]["id"] == IDS[0]
    response = versioned(client, "POST", f"/api/bookings/{booking['id']}/cancel", running["version"])
    assert response.status_code == 200
    time.sleep(0.4)
    result = current(client, booking["id"])["summary"]
    assert result["status"] == "CANCELLED"
    assert result["confirmation"] is None
    assert result["completed_attempts"] == 1
    assert result["contacted_restaurants"][0]["result"] == "CANCELLED"
    assert len(result["pending_restaurants"]) == 3


def test_start_is_idempotent_and_execution_respects_reorder(client):
    booking = make_booking(client)
    reversed_ids = list(reversed(IDS))
    reordered = versioned(
        client,
        "PUT",
        f"/api/bookings/{booking['id']}/restaurants/order",
        booking["version"],
        {"restaurant_ids": reversed_ids},
    )
    assert reordered.status_code == 200
    start_booking(client, reordered.json(), "confirm-first")
    start_booking(client, reordered.json(), "confirm-first")
    finished = wait_for(client, booking["id"], {"CONFIRMED"})
    assert finished["summary"]["completed_attempts"] == 1
    assert finished["summary"]["confirmation"]["restaurant_id"] == IDS[-1]
    events = client.get(f"/api/bookings/{booking['id']}/events?limit=100").json()["items"]
    assert sum(e["event_type"] == "booking.started" for e in events) == 1


@pytest.mark.parametrize(
    "config,ids",
    [
        ({}, IDS),
        (configuration(), []),
        ({**configuration(), "requested_date": "2020-01-01"}, IDS),
    ],
)
def test_incomplete_or_past_draft_cannot_start(client, config, ids):
    booking = make_booking(client, config=config, ids=ids)
    result = versioned(
        client,
        "POST",
        f"/api/bookings/{booking['id']}/start",
        booking["version"],
        {"scenario_id": "priority-success"},
    )
    assert result.status_code == 422
    assert current(client, booking["id"])["status"] == "DRAFT"


def test_websocket_replay_global_stream_and_rest_match(client):
    first = make_booking(client, ids=[], config={})
    second = make_booking(client, ids=[], config={})
    events = client.get(f"/api/bookings/{first['id']}/events").json()["items"]
    with client.websocket_connect(f"/api/events/ws?booking_id={first['id']}") as websocket:
        websocket.send_json({"token": TOKEN})
        replay = websocket.receive_json()
        assert replay == events[0]
        EventOut.model_validate(replay)
        changed = versioned(
            client,
            "PATCH",
            f"/api/bookings/{first['id']}",
            first["version"],
            {"configuration": {"adults": 7}},
        )
        assert changed.status_code == 200
        update = websocket.receive_json()
        assert update["payload"]["summary"]["party_size"] == 7
    with client.websocket_connect(f"/api/events/ws?after_event_id={replay['event_id']}") as websocket:
        websocket.send_json({"token": TOKEN})
        assert websocket.receive_json()["booking_id"] == second["id"]
        assert websocket.receive_json() == update
    rest = client.get(f"/api/bookings/{first['id']}/events?after_event_id={replay['event_id']}").json()
    assert rest["items"] == [update]


def test_paginated_event_recovery(client):
    booking = make_booking(client, ids=IDS[:1])
    start_booking(client, booking, "confirm-first")
    wait_for(client, booking["id"], {"CONFIRMED"})
    events, cursor = [], 0
    while True:
        page = client.get(f"/api/bookings/{booking['id']}/events?after_event_id={cursor}&limit=2").json()
        events.extend(page["items"])
        cursor = page["next_after_event_id"]
        if not page["has_more"]:
            break
    assert len({event["event_id"] for event in events}) == len(events)
    assert events[-1]["event_type"] == "booking.confirmed"


def test_interrupted_run_reconciles_without_new_calls(settings):
    upgrade(settings.database_url)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    settings.call_delay_seconds = 10
    with TestClient(create_app(settings), headers=headers) as client:
        booking = make_booking(client)
        start_booking(client, booking, "confirm-first")
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            running = current(client, booking["id"])
            if running["summary"]["current_call_status"] == "RUNNING":
                break
            time.sleep(0.01)
        assert running["summary"]["current_call_status"] == "RUNNING"
    settings.call_delay_seconds = 0
    with TestClient(create_app(settings), headers=headers) as client:
        recovered = current(client, booking["id"])["summary"]
        assert recovered["status"] == "FAILED"
        assert recovered["confirmation"] is None
        assert recovered["completed_attempts"] == 1
        assert recovered["contacted_restaurants"][0]["result"] == "INTERRUPTED"
        assert len(recovered["pending_restaurants"]) == 3


def test_waiting_approval_survives_restart(settings):
    upgrade(settings.database_url)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    with TestClient(create_app(settings), headers=headers) as client:
        booking = make_booking(client, ids=IDS[:1])
        start_booking(client, booking, "approval")
        waiting = wait_for(client, booking["id"], {"WAITING_FOR_USER"})
    with TestClient(create_app(settings), headers=headers) as client:
        recovered = current(client, booking["id"])
        assert recovered == waiting
        offer_id = recovered["summary"]["pending_approvals"][0]["id"]
        response = versioned(
            client,
            "POST",
            f"/api/bookings/{booking['id']}/decisions",
            recovered["version"],
            {"offer_id": offer_id, "approve": True},
        )
        assert response.status_code == 200
        confirmed = wait_for(client, booking["id"], {"CONFIRMED"})
        assert confirmed["summary"]["completed_attempts"] == 1


def test_confirmation_timeout_stops_without_trying_next(client):
    class UncertainProvider(MockCallProvider):
        async def confirm(self, *args, **kwargs):
            raise TimeoutError("Uncertain confirmation")

    client.app.state.executor.provider = UncertainProvider(0)
    booking = make_booking(client)
    start_booking(client, booking, "confirm-first")
    failed = wait_for(client, booking["id"], {"FAILED"})["summary"]
    assert failed["completed_attempts"] == 1
    assert failed["contacted_restaurants"][0]["result"] == "TIMEOUT"
    assert failed["confirmation"] is None
