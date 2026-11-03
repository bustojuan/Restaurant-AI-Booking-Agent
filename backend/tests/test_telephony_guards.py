import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs

import httpx
import pytest
from conftest import IDS, configuration
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect
from twilio.request_validator import RequestValidator

from app.ai.models import AIExecution, VoiceCallSession
from app.ai.prompts import prompt_bundle
from app.bootstrap import bootstrap
from app.core.errors import DomainError
from app.db.session import Database
from app.migrate import upgrade
from app.models import CallAttempt
from app.providers.calls import UncertainCallError
from app.providers.images import NoImageProvider
from app.repositories import require_booking, require_restaurant
from app.schemas import BookingCreate, CallAuthorization
from app.services.bookings import create_booking
from app.voice.authorization import validate_authorization
from app.voice.gateway import bind_stream, create_gateway, signed_url
from app.voice.live import LiveProtocolError
from app.voice.telephony import TwilioCallProvider, TwilioTransport


@pytest.fixture
def phone_store(settings):
    settings.real_telephony_enabled = True
    settings.openai_api_key = SecretStr("fake-openai-key")
    settings.twilio_account_sid = "AC" + "a" * 32
    settings.twilio_auth_token = SecretStr("fake-twilio-key")
    settings.twilio_phone_number = "+34910000001"
    settings.telephony_allowed_numbers = ["+34910000002"]
    settings.telephony_public_origin = "https://gateway.example.test"
    settings.telephony_start_hour, settings.telephony_end_hour = 0, 24
    settings.telephony_cost_per_minute, settings.live_cost_per_minute = 0.1, 0.1
    settings.reasoning_reserved_cost_per_call = 0.1
    authorization = CallAuthorization(
        explicit_authorization=True,
        own_test_numbers_only=True,
        audio_processing_consent=True,
        max_calls=1,
        max_duration_seconds=30,
        max_estimated_cost_eur=2,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    upgrade(settings.database_url)
    db = Database(settings.database_url)
    bootstrap(db, NoImageProvider(), True)
    with db.transaction(write=True) as session:
        restaurant = require_restaurant(session, IDS[0])
        restaurant.phone = settings.telephony_allowed_numbers[0]
        booking = create_booking(
            session, BookingCreate(configuration=configuration(), restaurant_ids=IDS[:1])
        )
        row = require_booking(session, booking.id)
        row.status = "RUNNING"
        execution = AIExecution(
            booking_id=booking.id,
            mode="real_telephony",
            prompts=prompt_bundle(),
            authorization=authorization.model_dump(mode="json"),
        )
        session.add(execution)
        attempt = CallAttempt(booking_id=booking.id, restaurant_id=IDS[0], status="RUNNING", sequence=0)
        session.add(attempt)
        session.flush()
        call = VoiceCallSession(
            execution_id=execution.id,
            attempt_id=attempt.id,
            restaurant_id=IDS[0],
            transport_state="DIALING",
            external_call_sid="CA" + "b" * 32,
            media_token_hash=hashlib.sha256(b"nonce-for-this-call").hexdigest(),
            deadline=(datetime.now(UTC) + timedelta(seconds=30)).isoformat(),
            reserved_cost_eur=0.2,
        )
        session.add(call)
        session.flush()
        ids = {"booking": booking.id, "execution": execution.id, "attempt": attempt.id, "call": call.id}
    yield db, settings, authorization, ids
    db.engine.dispose()


def test_complete_real_authorization_is_validated_without_dialing(phone_store):
    db, settings, authorization, ids = phone_store
    with db.transaction() as session:
        validate_authorization(session, require_booking(session, ids["booking"]), authorization, settings)


@pytest.mark.parametrize(
    "failure,expected",
    [
        ("disabled", "real_telephony_disabled"),
        ("expired", "authorization_expired"),
        ("budget", "budget_exceeded"),
        ("phone", "phone_not_authorized"),
        ("hours", "outside_calling_hours"),
        ("credentials", "credentials_missing"),
        ("origin", "invalid_public_origin"),
        ("tariffs", "cost_limits_unconfigured"),
    ],
)
def test_real_authorization_guards(phone_store, failure, expected):
    db, settings, authorization, ids = phone_store
    if failure == "disabled":
        settings.real_telephony_enabled = False
    if failure == "expired":
        authorization.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    if failure == "budget":
        authorization.max_estimated_cost_eur = 0.01
    if failure == "phone":
        settings.telephony_allowed_numbers = []
    if failure == "hours":
        settings.telephony_start_hour, settings.telephony_end_hour = 23, 1
    if failure == "credentials":
        settings.twilio_auth_token = None
    if failure == "origin":
        settings.telephony_public_origin = "http://unsafe.test"
    if failure == "tariffs":
        settings.live_cost_per_minute = None
    with db.transaction() as session, pytest.raises(DomainError) as error:
        validate_authorization(session, require_booking(session, ids["booking"]), authorization, settings)
    assert error.value.code == expected


def stream_event(settings, ids):
    return {
        "event": "start",
        "streamSid": "MZ" + "c" * 32,
        "start": {
            "accountSid": settings.twilio_account_sid,
            "callSid": "CA" + "b" * 32,
            "streamSid": "MZ" + "c" * 32,
            "customParameters": {"session_id": ids["call"], "media_token": "nonce-for-this-call"},
            "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1},
        },
    }


def test_signed_stream_binds_exact_call_and_prevents_replay(phone_store):
    db, settings, _, ids = phone_store
    result = bind_stream(db, settings, stream_event(settings, ids))
    assert result[:3] == (ids["call"], ids["booking"], "MZ" + "c" * 32)
    with pytest.raises(LiveProtocolError):
        bind_stream(db, settings, stream_event(settings, ids))


@pytest.mark.parametrize("tamper", ["token", "account", "call", "codec"])
def test_untrusted_stream_metadata_is_rejected(phone_store, tamper):
    db, settings, _, ids = phone_store
    event = stream_event(settings, ids)
    if tamper == "token":
        event["start"]["customParameters"]["media_token"] = "wrong"
    if tamper == "account":
        event["start"]["accountSid"] = "AC" + "f" * 32
    if tamper == "call":
        event["start"]["callSid"] = "CA" + "f" * 32
    if tamper == "codec":
        event["start"]["mediaFormat"]["sampleRate"] = 24000
    with pytest.raises(LiveProtocolError):
        bind_stream(db, settings, event)


def test_gateway_has_only_signed_telephony_routes(phone_store):
    db, settings, _, ids = phone_store
    app = create_gateway(settings)
    with TestClient(app) as client:
        assert client.get("/api/bookings").status_code == 404
        assert client.get("/docs").status_code == 404
        path = f"/twilio/status/{ids['call']}"
        payload = {
            "AccountSid": settings.twilio_account_sid,
            "CallSid": "CA" + "b" * 32,
            "To": settings.telephony_allowed_numbers[0],
            "CallStatus": "completed",
        }
        assert client.post(path, data=payload).status_code == 403
        signature = RequestValidator(settings.twilio_auth_token.get_secret_value()).compute_signature(
            signed_url(settings, path), payload
        )
        assert client.post(path, data=payload, headers={"X-Twilio-Signature": signature}).status_code == 204
        assert client.post(path, data=payload, headers={"X-Twilio-Signature": signature}).status_code == 204
        with pytest.raises(WebSocketDisconnect), client.websocket_connect("/twilio/media"):
            pass
    with db.transaction() as session:
        assert session.get(VoiceCallSession, ids["call"]).transport_state == "ENDED"


def test_twilio_request_contract_with_mock_http_and_recording_disabled(phone_store):
    _, settings, _, _ = phone_store
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(201, json={"sid": "CA" + "d" * 32, "status": "queued"})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            transport = TwilioTransport(settings, client)
            result = await transport.dial(
                "+34910000002", "<Response/>", "https://gateway.example.test/status", 30
            )
            assert result["sid"].startswith("CA")

    asyncio.run(run())
    assert len(requests) == 1
    payload = parse_qs(requests[0].content.decode())
    assert payload["Record"] == ["false"]
    assert payload["TimeLimit"] == ["30"]


def test_ambiguous_outbound_timeout_is_never_redialed(phone_store):
    db, settings, _, ids = phone_store
    with db.transaction(write=True) as session:
        session.delete(session.get(VoiceCallSession, ids["call"]))
        config = require_booking(session, ids["booking"]).configuration
    attempts = []

    class AmbiguousTransport:
        async def dial(self, *args):
            attempts.append(True)
            raise httpx.ReadTimeout("Simulated request timeout")

    provider = TwilioCallProvider(db, ids["execution"], settings, transport=AmbiguousTransport())
    from app.schemas import BookingConfiguration

    async def run():
        for _ in range(2):
            with pytest.raises(UncertainCallError):
                await provider.contact(
                    BookingConfiguration.model_validate(config), IDS[0], "unused", ids["attempt"]
                )

    asyncio.run(run())
    assert len(attempts) == 1
    with db.transaction() as session:
        assert session.scalar(select(VoiceCallSession)).transport_state == "UNCERTAIN"
