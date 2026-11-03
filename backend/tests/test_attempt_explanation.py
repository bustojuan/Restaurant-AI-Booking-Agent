import pytest
from conftest import configuration, make_booking
from pydantic import SecretStr
from sqlalchemy import delete, select
from test_ai_integration import start_ai, wait_ai
from test_control_center import ADMIN, get, wait_for

from app.ai.models import AIExecution, VoiceCallSession
from app.observability.models import ObservedExecution


def test_offer_mismatch_is_explained_with_persisted_evidence_and_no_private_data(client, settings):
    settings.admin_api_token = SecretStr(ADMIN)
    booking = make_booking(client, config={**configuration(), "flexibility_minutes": 30})
    start_ai(client, booking)
    wait_for(client, booking["id"], {"CONFIRMED"})
    wait_ai(client, booking["id"])
    calls = get(client, "/calls", q=booking["id"], direction="asc").json()["items"]
    response = get(client, f"/calls/{calls[1]['id']}")
    data = response.json()["explanation"]
    mismatch = next(f for f in data["facts"] if f["code"] == "time_outside_window")
    assert "90 minutos" in mismatch["message"] and "30 minutos autorizados" in mismatch["message"]
    assert {r["kind"] for r in mismatch["evidence"]} == {"request", "offer", "evaluation"}
    assert data["offers"][0]["evaluation"] == "UNACCEPTABLE"
    assert data["offers"][0]["terms"]["time"] == "22:30:00"
    assert "contact_phone" not in response.text and "+34000000000" not in response.text
    assert "customer_name" not in response.text and "Cliente simulado" not in response.text
    assert "verified_requirements" not in response.text
    confirmation = get(client, f"/calls/{calls[2]['id']}").json()["explanation"]
    assert confirmation["simulated"] is True
    assert any(
        f["code"] == "confirmed" and f["evidence"][0]["kind"] == "confirmation" for f in confirmation["facts"]
    )
    assert any(f["evidence"][0].get("event_cursor") for f in confirmation["facts"])
    # Retention removes trace evidence, not the retained business offer/confirmation.
    with client.app.state.db.transaction(write=True) as session:
        session.execute(delete(ObservedExecution).where(ObservedExecution.booking_id == booking["id"]))
    retained = get(client, f"/calls/{calls[2]['id']}").json()["explanation"]
    assert any(f["code"] == "confirmed" for f in retained["facts"])
    assert not any(f["code"] == "business_event" for f in retained["facts"])


@pytest.mark.parametrize(
    "scenario,state,category",
    [
        ("ai-ambiguous", "EXHAUSTED", "continue"),
        ("ai-incomplete-confirmation", "FAILED", "review_required"),
        ("ai-connection-error", "FAILED", "review_required"),
    ],
)
def test_ambiguity_distinguishes_no_acceptance_from_possible_reservation(
    client, settings, scenario, state, category
):
    settings.admin_api_token = SecretStr(ADMIN)
    booking = make_booking(client, ids=["madrid-1"])
    start_ai(client, booking, scenario)
    wait_for(client, booking["id"], {state})
    wait_ai(client, booking["id"])
    call = get(client, "/calls", q=booking["id"]).json()["items"][0]
    detail = get(client, f"/calls/{call['id']}").json()
    assert detail["confirmation_id"] is None
    review = detail["explanation"]["review"]
    assert review["category"] == category
    assert review["automatic_continuation"] is (category == "continue")
    assert not review["reconciliation_available"]  # Never offer Twilio for a simulation.
    if category == "review_required":
        assert review["steps"] and "Podría existir" in review["title"]
    else:
        with client.app.state.db.transaction(write=True) as session:
            session.execute(delete(VoiceCallSession).where(VoiceCallSession.attempt_id == call["id"]))
        missing = get(client, f"/calls/{call['id']}").json()["explanation"]["review"]
        assert missing["category"] == "unknown" and missing["automatic_continuation"] is None


def test_review_is_read_only_and_operator_reconciliation_does_not_imply_resumption(
    client, settings, monkeypatch
):
    settings.admin_api_token = SecretStr(ADMIN)
    booking = make_booking(client, ids=["madrid-1"])
    start_ai(client, booking, "ai-incomplete-confirmation")
    wait_for(client, booking["id"], {"FAILED"})
    wait_ai(client, booking["id"])
    call = get(client, "/calls", q=booking["id"]).json()["items"][0]

    async def forbidden(*args, **kwargs):
        raise AssertionError("Inspection cannot contact a provider or run a graph")

    monkeypatch.setattr("app.voice.telephony.TwilioTransport.inspect", forbidden)
    monkeypatch.setattr("app.voice.telephony.TwilioTransport.dial", forbidden)
    monkeypatch.setattr(client.app.state.ai.graph, "ainvoke", forbidden)
    with client.app.state.db.transaction(write=True) as session:
        ai = session.scalar(select(AIExecution).where(AIExecution.booking_id == booking["id"]))
        ai.mode = "real_telephony"  # Retained terminal fixture only; no real transport.
        voice = session.scalar(select(VoiceCallSession).where(VoiceCallSession.attempt_id == call["id"]))
        voice.external_call_sid = "CA" + "0" * 32
    before = client.get(f"/api/bookings/{booking['id']}").json()
    review = get(client, f"/calls/{call['id']}").json()["explanation"]["review"]
    assert review["reconciliation_available"] is True
    assert client.get(f"/api/bookings/{booking['id']}").json() == before
    with client.app.state.db.transaction(write=True) as session:
        voice = session.scalar(select(VoiceCallSession).where(VoiceCallSession.attempt_id == call["id"]))
        voice.action = "RECONCILED_NO_RESERVATION"
    review = get(client, f"/calls/{call['id']}").json()["explanation"]["review"]
    assert review["category"] == "reconciled" and review["automatic_continuation"] is False
