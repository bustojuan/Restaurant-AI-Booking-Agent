import asyncio
from types import SimpleNamespace

from conftest import make_booking, start_booking, wait_for
from pydantic import SecretStr
from test_ai_agents import sample
from test_voice_protocol import FakeConnector, FakeLiveSocket

from app.ai.contracts import ExtractedConversation
from app.ai.extraction import ResponsesExtractor
from app.providers.calls import MockCallProvider
from app.schemas import OfferDetails
from app.voice.delegation import VoiceDelegationService
from app.voice.live import LiveSession


def test_live_client_delegation_runs_persistent_graph_without_mutating_draft(client):
    booking = make_booking(client)
    settings = client.app.state.settings
    settings.openai_api_key = SecretStr("fake-key-never-sent")
    socket = FakeLiveSocket()
    model_calls = []

    class FixtureExtractor:
        async def extract(self, *args, **kwargs):
            model_calls.append(True)
            return ExtractedConversation(
                intent="proposal",
                offer=OfferDetails(
                    requested_date=booking["configuration"]["requested_date"],
                    time="21:00",
                    party_size=4,
                    table_type="inside",
                ),
            )

    async def scenario():
        service = VoiceDelegationService(
            client.app.state.db, settings, client.app.state.ai.saver, extractor=FixtureExtractor()
        )
        live = LiveSession(settings, "Prueba identificada como IA", connector=FakeConnector(socket))

        async def frames():
            while not live.closed.is_set():
                yield b"\0\0" * 480
                await asyncio.sleep(0.01)

        async def output(raw):
            pass

        async def delegate(text, identity, revision):
            return await service.handle(
                text, identity, revision, booking_id=booking["id"], sandbox_id="scoped-sandbox"
            )

        await live.run(frames(), output, delegate, greeting="Preséntate como IA en una prueba.")
        snapshot = await service.graph.aget_state(
            {"configurable": {"thread_id": "voice:scoped-sandbox:deleg-1"}}
        )
        assert snapshot.next == ()
        assert "cumple los límites" in snapshot.values["result"]
        assert "Hay mesa para cuatro" not in str(snapshot.values)
        repeated = await service.handle(
            "PRIVATE_NEW_TRANSCRIPT", "deleg-1", 2, booking_id=booking["id"], sandbox_id="scoped-sandbox"
        )
        assert repeated == snapshot.values["result"]

    client.portal.call(scenario)
    assert len(model_calls) == 1
    assert client.get(f"/api/bookings/{booking['id']}").json()["status"] == "DRAFT"
    assert any(
        e.get("delegation_id") == "deleg-1" and e["type"] == "session.commentary.append" for e in socket.sent
    )


def test_extractor_requires_real_restaurant_quotes_for_confirmation(settings):
    config, offer, evidence = sample()
    evidence.confirmation_quote = "Queda confirmada a nombre del cliente"

    class FakeResponses:
        async def parse(self, **kwargs):
            return SimpleNamespace(
                output_parsed=ExtractedConversation(
                    intent="confirmation",
                    offer=offer,
                    evidence=evidence,
                    requirement_quotes={"dietary:gluten": "Podemos atender el requisito sin gluten"},
                ),
                usage=None,
            )

    extractor = ResponsesExtractor(settings, client=SimpleNamespace(responses=FakeResponses()))
    result = asyncio.run(
        extractor.extract(
            "assistant: Queda confirmada a nombre del cliente\nrestaurant: Creo que quizá",
            config,
            "restaurant",
            "attempt",
            prompt="Extrae hechos",
        )
    )
    assert result.evidence.explicit_confirmation is False
    assert not result.offer.verified_requirements


def test_external_contact_timeout_stops_and_requires_reconciliation(client):
    class ExternalProvider(MockCallProvider):
        external_effects = True

        async def contact(self, *args, **kwargs):
            raise TimeoutError("External placement may have happened")

    client.app.state.executor.provider = ExternalProvider(0)
    booking = make_booking(client)
    start_booking(client, booking, "confirm-first")
    failed = wait_for(client, booking["id"], {"FAILED"})["summary"]
    assert failed["completed_attempts"] == 1
    assert failed["contacted_restaurants"][0]["result"] == "UNCERTAIN"
    assert len(failed["pending_restaurants"]) == 3
