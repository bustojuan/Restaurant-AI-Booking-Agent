import asyncio
import time
from datetime import UTC, datetime, timedelta

import pytest
from conftest import IDS, TOKEN, configuration, current, make_booking, versioned, wait_for
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.ai.models import AIExecution, ToolOperation
from app.ai.tools import AgentTools, ToolScope
from app.core.errors import DomainError
from app.main import create_app
from app.migrate import upgrade


def start_ai(client, booking, scenario="priority-success"):
    response = versioned(
        client,
        "POST",
        f"/api/bookings/{booking['id']}/start",
        booking["version"],
        {"mode": "ai_simulation", "scenario_id": scenario},
    )
    assert response.status_code == 200, response.text
    return response.json()


def wait_ai(client, booking_id):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        result = client.get(f"/api/bookings/{booking_id}/ai").json()
        if result.get("quality_report"):
            return result
        time.sleep(0.02)
    pytest.fail(f"AI summary did not finish: {result}")


def test_real_langgraph_full_pipeline_persists_and_reuses_backend(client):
    config = {
        **configuration(),
        "flexibility_minutes": 30,
        "table_type": "terrace",
        "dietary_requirements": [{"kind": "celiac", "code": "gluten", "mandatory": True}],
    }
    booking = make_booking(client, config=config)
    start_ai(client, booking)
    result = wait_for(client, booking["id"], {"CONFIRMED", "FAILED"})
    assert result["status"] == "CONFIRMED", result
    assert result["summary"]["completed_attempts"] == 3
    assert result["summary"]["confirmation"]["restaurant_id"] == IDS[2]
    assert [r["id"] for r in result["summary"]["pending_restaurants"]] == [IDS[3]]
    execution = wait_ai(client, booking["id"])
    assert execution["quality_report"]["passed"] is True
    assert "3 intentos" in execution["summary_text"]
    assert len(execution["prompt_versions"]) == 8
    state = client.get(f"/api/bookings/{booking['id']}/ai/state").json()
    assert state["next_nodes"] == []
    from app.ai.models import VoiceCallSession

    with client.app.state.db.transaction() as session:
        calls = list(session.scalars(select(VoiceCallSession)))
        assert len(calls) == 3
        assert sum(c.evidence is not None for c in calls) == 1
    assert state["values"].get("verification_result") is not None
    assert state["values"]["verification_result"]["status"] == "CONFIRMED"
    assert state["values"]["booking_plan"]["mandatory_conditions"]
    assert "contact_phone" not in str(state)
    traces = client.get(f"/api/bookings/{booking['id']}/ai/traces?limit=100").json()
    assert {"planning", "research", "voice", "negotiation", "verification", "memory", "evaluation"}.issubset(
        {t["agent"] for t in traces}
    )
    assert any(t["tool"] == "persist_call_outcome" for t in traces)
    assert all(t["estimated_cost_eur"] is None for t in traces)
    events = client.get(f"/api/bookings/{booking['id']}/events?limit=100").json()["items"]
    assert any(e["event_type"] == "agent.activity" and e["payload"]["activity"] for e in events)


@pytest.mark.parametrize(
    "scenario,status,result",
    [
        ("all-full", "EXHAUSTED", "NO_AVAILABILITY"),
        ("ai-valid-alternative", "CONFIRMED", "CONFIRMED"),
        ("ai-correction", "EXHAUSTED", "INCOMPATIBLE_OFFER"),
        ("ai-ambiguous", "EXHAUSTED", "AMBIGUOUS"),
        ("approval", "WAITING_FOR_USER", "USER_APPROVAL_REQUIRED"),
        ("missing-evidence", "EXHAUSTED", "INSUFFICIENT_INFORMATION"),
        ("ai-disconnect", "EXHAUSTED", "DISCONNECTED"),
        ("ai-connection-error", "FAILED", "UNCERTAIN"),
        ("ai-incomplete-confirmation", "FAILED", "AMBIGUOUS"),
        ("ai-injection", "EXHAUSTED", "AMBIGUOUS"),
        ("ai-refuses", "EXHAUSTED", "DECLINED_AI"),
    ],
)
def test_ai_scenarios_are_truthful_and_bounded(client, scenario, status, result):
    booking = make_booking(
        client,
        ids=IDS[:1],
        config={
            **configuration(),
            "flexibility_minutes": 30,
            "dietary_requirements": [{"kind": "allergy", "code": "nuts"}],
        },
    )
    start_ai(client, booking, scenario)
    finished = wait_for(client, booking["id"], {status, "FAILED"})
    assert finished["status"] == status, finished
    assert finished["summary"]["contacted_restaurants"][0]["result"] == result
    assert bool(finished["summary"]["confirmation"]) == (status == "CONFIRMED")
    if status != "WAITING_FOR_USER":
        assert wait_ai(client, booking["id"])["quality_report"]["passed"] is True


def test_graph_approval_persists_across_restart_and_resumes_once(settings):
    upgrade(settings.database_url)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    with TestClient(create_app(settings), headers=headers) as client:
        booking = make_booking(client, ids=IDS[:1])
        start_ai(client, booking, "approval")
        wait_for(client, booking["id"], {"WAITING_FOR_USER"})
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            state = client.get(f"/api/bookings/{booking['id']}/ai/state").json()
            if state["interrupts"]:
                break
            time.sleep(0.02)
        assert state["interrupts"][0]["type"] == "booking_approval"
    with TestClient(create_app(settings), headers=headers) as client:
        recovered = current(client, booking["id"])
        assert recovered["status"] == "WAITING_FOR_USER"
        state = client.get(f"/api/bookings/{booking['id']}/ai/state").json()
        assert state["interrupts"]
        offer = recovered["summary"]["pending_approvals"][0]
        response = versioned(
            client,
            "POST",
            f"/api/bookings/{booking['id']}/decisions",
            recovered["version"],
            {"offer_id": offer["id"], "approve": True},
        )
        assert response.status_code == 200
        final = wait_for(client, booking["id"], {"CONFIRMED", "FAILED"})
        assert final["status"] == "CONFIRMED", final
        assert final["summary"]["completed_attempts"] == 1
        assert wait_ai(client, booking["id"])["quality_report"]["passed"] is True
        with client.app.state.db.transaction() as session:
            operations = session.scalars(
                select(ToolOperation).where(ToolOperation.tool == "persist_call_outcome")
            ).all()
            assert len(operations) == 2  # one contact, one acceptance; no repeated external contact


def test_tool_capabilities_validation_and_idempotency(client):
    booking = make_booking(client, ids=IDS[:1])
    # Bind a test execution without starting external work.
    from app.ai.prompts import prompt_bundle

    with client.app.state.db.transaction(write=True) as session:
        execution = AIExecution(booking_id=booking["id"], mode="ai_simulation", prompts=prompt_bundle())
        session.add(execution)
        session.flush()
        execution_id = execution.id
    scope = ToolScope(execution_id, booking["id"], "supervisor")
    count = []

    async def advance():
        count.append(True)

    tools = AgentTools(client.app.state.db, scope, advance)

    async def exercise():
        first = await tools.invoke("persist_call_outcome", operation_id="unique-operation")
        second = await tools.invoke("persist_call_outcome", operation_id="unique-operation")
        assert first == second
        with pytest.raises(DomainError, match="not permitted"):
            await tools.invoke("submit_reservation_evidence", {})
        with pytest.raises(DomainError, match="Invalid execution scope"):
            await AgentTools(client.app.state.db, ToolScope(execution_id, "wrong", "planning")).invoke(
                "get_booking_requirements"
            )
        catalog = AgentTools(
            client.app.state.db, ToolScope(execution_id, booking["id"], "planning")
        ).as_langchain_tools()
        assert await next(t for t in catalog if t.name == "get_booking_requirements").ainvoke({})

    asyncio.run(exercise())
    assert len(count) == 1


def test_preferences_require_consent_expire_and_do_not_change_draft(client):
    booking = make_booking(client, ids=[])
    expires = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    path = "/api/ai/memories/preferences"
    payload = {"key": "table_type", "value": "terrace", "expires_at": expires, "authorized_by_user": True}
    assert client.post(path, json={**payload, "authorized_by_user": False}).status_code == 422
    saved = client.post(path, json=payload)
    assert saved.status_code == 200
    assert current(client, booking["id"])["configuration"] == booking["configuration"]
    assert client.get("/api/ai/memories?scope=preference").json()[0]["provenance"] == "USER_AUTHORIZED"
    assert client.delete("/api/ai/memories/" + saved.json()["id"]).status_code == 204
    assert client.get("/api/ai/memories?scope=preference").json() == []


def test_real_telephony_and_voice_are_disabled_by_default(client):
    booking = make_booking(client, ids=IDS[:1])
    response = versioned(
        client, "POST", f"/api/bookings/{booking['id']}/start", booking["version"], {"mode": "real_telephony"}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "real_telephony_disabled"
    assert current(client, booking["id"])["status"] == "DRAFT"
    assert client.get("/api/ai/capabilities").json()["recording_enabled"] is False
    with client.websocket_connect(f"/api/voice/sandbox/ws?booking_id={booking['id']}") as ws:
        ws.send_json({"token": TOKEN, "allow_api_costs": True, "audio_processing_consent": True})
        assert ws.receive_json()["code"] == "voice_sandbox_not_configured"


def test_pause_persists_at_boundary_and_resumes_after_restart(settings):
    upgrade(settings.database_url)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    settings.call_delay_seconds = 0.3
    with TestClient(create_app(settings), headers=headers) as client:
        booking = make_booking(client, ids=IDS[:2])
        start_ai(client, booking, "all-full")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            running = current(client, booking["id"])
            if running["summary"]["current_call_status"] == "RUNNING":
                break
            time.sleep(0.01)
        response = versioned(client, "POST", f"/api/bookings/{booking['id']}/ai/pause", running["version"])
        assert response.status_code == 200
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            state = client.get(f"/api/bookings/{booking['id']}/ai/state").json()
            if state["interrupts"]:
                break
            time.sleep(0.02)
        assert state["interrupts"][0]["type"] == "execution_paused"
        assert current(client, booking["id"])["summary"]["completed_attempts"] == 1
    settings.call_delay_seconds = 0.01
    with TestClient(create_app(settings), headers=headers) as client:
        recovered = current(client, booking["id"])
        assert recovered["status"] == "RUNNING"
        assert client.get(f"/api/bookings/{booking['id']}/ai").json()["paused"] is True
        response = versioned(client, "POST", f"/api/bookings/{booking['id']}/ai/resume", recovered["version"])
        assert response.status_code == 200
        result = wait_for(client, booking["id"], {"EXHAUSTED", "FAILED"})
        assert result["status"] == "EXHAUSTED"
        assert result["summary"]["completed_attempts"] == 2
        assert wait_ai(client, booking["id"])["quality_report"]["passed"]


def test_cancelling_interrupted_graph_finishes_and_allows_ai_data_erasure(client):
    booking = make_booking(client, ids=IDS[:1])
    start_ai(client, booking, "approval")
    waiting = wait_for(client, booking["id"], {"WAITING_FOR_USER"})
    result = versioned(client, "POST", f"/api/bookings/{booking['id']}/cancel", waiting["version"])
    assert result.status_code == 200
    execution = wait_ai(client, booking["id"])
    assert "confirmó la reserva" not in execution["summary_text"]
    latest = current(client, booking["id"])
    assert latest["status"] == "CANCELLED"
    response = versioned(client, "DELETE", f"/api/bookings/{booking['id']}/ai/data", latest["version"])
    assert response.status_code == 204
    assert client.get(f"/api/bookings/{booking['id']}/ai").status_code == 404
    assert current(client, booking["id"])["status"] == "CANCELLED"
