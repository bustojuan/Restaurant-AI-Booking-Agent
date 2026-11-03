import time

import pytest
from conftest import current, make_booking, versioned
from pydantic import SecretStr
from sqlalchemy import delete, select
from test_ai_integration import start_ai, wait_ai

from app.ai.models import AIExecution
from app.models import BookingRequest
from app.observability.models import ObservationEvent, ObservedExecution

ADMIN = "admin-control-center-test-only-token-12345"
ROOT = "/api/admin/observability"


def get(client, path, **params):
    return client.get(ROOT + path, params=params, headers={"Authorization": f"Bearer {ADMIN}"})


def post(client, path, data):
    return client.post(ROOT + path, json=data, headers={"Authorization": f"Bearer {ADMIN}"})


def wait_for(client, booking_id, states):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        booking = current(client, booking_id)
        if booking["status"] in states:
            return booking
        time.sleep(0.1)
    pytest.fail("Simulation did not reach expected persisted terminal state")


def test_call_history_filter_sort_group_and_safe_projection(client, settings):
    settings.admin_api_token = SecretStr(ADMIN)
    booking = make_booking(client)
    start_ai(client, booking)
    wait_for(client, booking["id"], {"CONFIRMED"})
    wait_ai(client, booking["id"])
    response = get(client, "/calls", q=booking["id"], sort="started_at", direction="asc", limit=2)
    assert response.status_code == 200, response.text
    page = response.json()
    assert page["total"] == 3 and len(page["items"]) == 2
    remaining = get(client, "/calls", q=booking["id"], offset=2, direction="asc").json()
    assert len(remaining["items"]) == 1
    assert not {c["id"] for c in page["items"]} & {c["id"] for c in remaining["items"]}
    confirmed = get(client, "/calls", q=booking["id"], result="CONFIRMED").json()
    assert confirmed["total"] == 1
    call = confirmed["items"][0]
    assert call["execution_id"] and call["confirmation_id"]
    assert call["cost_eur"] is None
    detail = get(client, f"/calls/{call['id']}").json()
    assert detail["explanation"]["facts"]
    assert {k: v for k, v in detail.items() if k != "explanation"} == {
        k: v for k, v in call.items() if k != "explanation"
    }
    assert get(client, "/calls", q=booking["id"], mode="real_telephony").json()["total"] == 0
    assert get(client, "/calls", q="%_").json()["total"] == 0
    groups = get(client, "/bookings", q=booking["id"], result="CONFIRMED").json()
    assert groups["total"] == 1 and len(groups["items"][0]["calls"]) == 3
    # Missing capture never becomes an invented graph. Business calls survive trace erasure.
    with client.app.state.db.transaction(write=True) as session:
        session.execute(delete(ObservedExecution).where(ObservedExecution.booking_id == booking["id"]))
    retained = get(client, f"/calls/{call['id']}").json()
    assert retained["coverage"] == "unavailable" and retained["execution_id"] is None
    assert "customer_name" not in response.text and "contact_phone" not in response.text
    assert get(client, "/calls", date_from="2026-11-05", date_to="2026-11-01").status_code == 422
    assert get(client, "/calls", limit=101).status_code == 422
    assert get(client, "/calls/no-such-call").status_code == 404


def test_administrative_reads_never_invoke_agents_or_tools(client, settings, monkeypatch):
    settings.admin_api_token = SecretStr(ADMIN)
    booking = make_booking(client)
    start_ai(client, booking)
    wait_for(client, booking["id"], {"CONFIRMED"})
    wait_ai(client, booking["id"])

    async def forbidden(*args, **kwargs):
        raise AssertionError("Administrative inspection must never execute agents")

    monkeypatch.setattr(client.app.state.ai.graph, "ainvoke", forbidden)
    before = client.get(f"/api/bookings/{booking['id']}").json()
    history = get(client, "/calls", q=booking["id"]).json()
    for call in history["items"]:
        assert get(client, f"/calls/{call['id']}").status_code == 200
    for path in ["/analytics", "/bookings", "/settings", "/playground/scenarios"]:
        assert get(client, path).status_code == 200
    report = get(client, f"/playground/runs/{booking['id']}").json()
    assert report["passed"] is True and report["agent_count"] >= 5 and len(report["tools"]) >= 3
    assert client.get(f"/api/bookings/{booking['id']}").json() == before


def test_analytics_uses_persisted_data_and_does_not_mix_modes(client, settings):
    settings.admin_api_token = SecretStr(ADMIN)
    booking = make_booking(client)
    start_ai(client, booking)
    wait_for(client, booking["id"], {"CONFIRMED"})
    wait_ai(client, booking["id"])
    metrics = get(client, "/analytics", q=booking["id"], mode="ai_simulation").json()
    assert metrics["calls"] == 3 and metrics["bookings"] == 1
    assert metrics["confirmed_bookings"] == 1 and metrics["confirmation_rate"] == 1
    assert metrics["attempts_per_booking"] == 3
    assert metrics["known_cost_eur"] is None and metrics["input_tokens"] is None
    assert sum(day["calls"] for day in metrics["days"]) == 3
    assert metrics["agents"] and metrics["tools"]
    assert all(agent["average_ms"] is None or agent["average_ms"] >= 0 for agent in metrics["agents"])
    assert get(client, "/analytics", mode="real_telephony").json()["calls"] == 0
    assert get(client, "/analytics", model="nonexistent-model").json()["calls"] == 0
    assert get(client, "/analytics", prompt="nonexistent-prompt").json()["calls"] == 0


def test_playground_uses_existing_engine_without_changing_workspace(client, settings):
    settings.admin_api_token = SecretStr(ADMIN)
    draft = make_booking(client)
    workspace = client.get("/api/workspace").json()
    versioned(client, "PUT", "/api/workspace", workspace["version"], {"active_draft_id": draft["id"]})
    workspace = client.get("/api/workspace").json()
    simulation = post(
        client,
        "/playground/runs",
        {"scenario_id": "priority-success", "adults": 3, "flexibility_minutes": 30},
    )
    assert simulation.status_code == 201, simulation.text
    identity = simulation.json()["booking_id"]
    wait_for(client, identity, {"CONFIRMED"})
    wait_ai(client, identity)
    assert get(client, f"/playground/runs/{identity}").json()["passed"] is True
    assert client.get("/api/workspace").json() == workspace
    dietary = post(client, "/playground/runs", {"scenario_id": "missing-evidence"})
    assert dietary.status_code == 201
    dietary_id = dietary.json()["booking_id"]
    wait_for(client, dietary_id, {"EXHAUSTED"})
    dietary_calls = get(client, "/calls", q=dietary_id).json()["items"]
    assert dietary_calls and all(call["confirmation_id"] is None for call in dietary_calls)
    with client.app.state.db.transaction() as session:
        assert session.get(BookingRequest, draft["id"]).status == "DRAFT"
        assert (
            session.scalar(select(AIExecution).where(AIExecution.booking_id == identity)).mode
            == "ai_simulation"
        )
    assert (
        post(
            client, "/playground/runs", {"scenario_id": "confirm-first", "mode": "real_telephony"}
        ).status_code
        == 422
    )
    assert post(client, "/playground/runs", {"scenario_id": "missing"}).status_code == 404
    settings.ai_extraction_mode = "responses"
    assert not get(client, "/playground/scenarios").json()[0]["available"]
    assert post(client, "/playground/runs", {"scenario_id": "confirm-first"}).status_code == 409


def test_admin_access_and_settings_never_expose_credentials(client, settings):
    settings.admin_api_token = None
    assert get(client, "/settings").status_code == 503
    settings.admin_api_token = SecretStr(ADMIN)
    settings.openai_api_key = SecretStr("PRIVATE_PROVIDER_KEY")
    for path in ["/calls", "/bookings", "/analytics", "/settings", "/playground/scenarios"]:
        assert client.get(ROOT + path).status_code == 401
        assert client.get(ROOT + path, headers={"Authorization": "Bearer invalid"}).status_code == 401
    response = get(client, "/settings")
    assert response.status_code == 200
    assert ADMIN not in response.text and "PRIVATE_PROVIDER_KEY" not in response.text
    assert response.json()["read_only"] and response.json()["prompts"]
    assert client.post(ROOT + "/playground/runs", json={"scenario_id": "confirm-first"}).status_code == 401


def test_human_interventions_survive_trace_retention(client, settings):
    settings.admin_api_token = SecretStr(ADMIN)
    booking = make_booking(client, ids=["madrid-1"])
    start_ai(client, booking, "approval")
    waiting = wait_for(client, booking["id"], {"WAITING_FOR_USER"})
    offer_id = waiting["summary"]["pending_approvals"][0]["id"]
    response = versioned(
        client,
        "POST",
        f"/api/bookings/{booking['id']}/decisions",
        waiting["version"],
        {"offer_id": offer_id, "approve": True},
    )
    assert response.status_code == 200
    wait_for(client, booking["id"], {"CONFIRMED"})
    wait_ai(client, booking["id"])
    assert get(client, "/analytics", q=booking["id"]).json()["human_interventions"] == 1
    with client.app.state.db.transaction(write=True) as session:
        session.execute(delete(ObservationEvent).where(ObservationEvent.booking_id == booking["id"]))
    metrics = get(client, "/analytics", q=booking["id"]).json()
    assert metrics["human_interventions"] == 1 and metrics["confirmed_bookings"] == 1
    assert metrics["agents"] == []
