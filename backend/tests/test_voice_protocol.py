import asyncio
import base64
import json

import pytest
from pydantic import SecretStr

from app.voice.live import LiveProtocolError, LiveSession


class FakeLiveSocket:
    def __init__(self, *, codec="pcm", correction=False, error=False):
        self.codec, self.correction, self.error = codec, correction, error
        self.incoming = asyncio.Queue()
        self.sent = []
        self.audio_count = 0
        self.delegated = False

    async def send(self, raw):
        event = json.loads(raw)
        self.sent.append(event)
        kind = event["type"]
        if kind == "session.start":
            await self.incoming.put({"type": "session.started", "session": {"id": "live-test"}})
            if self.error:
                await self.incoming.put({"type": "error", "error": {"message": "private-provider-detail"}})
        elif kind == "session.input_audio.append":
            self.audio_count += 1
            if not self.delegated:
                self.delegated = True
                await self.incoming.put(
                    {"type": "session.input_transcript.delta", "delta": "Hay mesa para cuatro a las nueve."}
                )
                request = {
                    "type": "session.delegation.created",
                    "delegation": {"id": "deleg-1", "target": "client"},
                }
                await self.incoming.put(request)
                await self.incoming.put(request)  # provider replay must not duplicate work
            elif self.correction and self.audio_count == 2:
                await self.incoming.put(
                    {"type": "session.input_transcript.delta", "delta": "Corrijo: a las diez y media."}
                )
        elif kind in {"session.commentary.append", "session.thinking.append"} and event.get("delegation_id"):
            raw_audio = b"\x7f" * 160 if self.codec == "pcmu" else b"\x00\x01" * 480
            await self.incoming.put(
                {"type": "session.output_audio.delta", "delta": base64.b64encode(raw_audio).decode()}
            )
            await asyncio.sleep(0.06)
            await self.incoming.put({"type": "session.closed", "usage": {"duration_seconds": 1}})
        elif kind == "session.close":
            await self.incoming.put({"type": "session.closed", "usage": {"duration_seconds": 1}})

    def __aiter__(self):
        return self

    async def __anext__(self):
        return json.dumps(await self.incoming.get())


class FakeConnector:
    def __init__(self, socket):
        self.socket = socket
        self.uri, self.options = None, None

    def __call__(self, uri, **kwargs):
        self.uri, self.options = uri, kwargs
        return self

    async def __aenter__(self):
        return self.socket

    async def __aexit__(self, *args):
        pass


@pytest.mark.parametrize("codec", ["pcm", "pcmu"])
def test_live_audio_client_delegation_is_independent_and_correct(settings, codec):
    settings.openai_api_key = SecretStr("fake-key-not-used-for-network")
    socket = FakeLiveSocket(codec=codec)
    connector = FakeConnector(socket)
    calls, outputs, clears = [], [], []

    async def scenario():
        live = LiveSession(settings, "Prompt de prueba", codec=codec, connector=connector)

        async def frames():
            while not live.closed.is_set():
                yield b"\x7f" * 160 if codec == "pcmu" else b"\x00\x01" * 480
                await asyncio.sleep(0.01)

        async def delegate(text, identity, revision):
            calls.append((text, identity, revision))
            await asyncio.sleep(0.04)
            assert socket.audio_count >= 2  # audio continued while backend work awaited
            return "Propuesta válida, pendiente de confirmación."

        async def output(raw):
            outputs.append(raw)

        async def clear():
            clears.append(True)

        usage = await live.run(frames(), output, delegate, greeting="Identifícate como IA.", on_clear=clear)
        assert usage == {"duration_seconds": 1}
        assert not live.transcripts

    asyncio.run(scenario())
    assert connector.uri == "wss://api.openai.com/v1/live/sessions"
    assert len(calls) == 1
    assert calls[0][1] == "deleg-1"
    assert "Hay mesa" in calls[0][0]
    assert outputs
    config = socket.sent[0]["session"]
    assert config["delegation"] == {"type": "client"}
    assert config["store"] is False
    assert config["audio"]["format"]["rate"] == (8000 if codec == "pcmu" else 24000)
    assert not any(e["type"] in {"response.cancel", "input_audio_buffer.append"} for e in socket.sent)


def test_live_discards_results_after_new_correction(settings):
    settings.openai_api_key = SecretStr("fake-key")
    socket = FakeLiveSocket(correction=True)

    async def scenario():
        live = LiveSession(settings, "Prompt", connector=FakeConnector(socket))

        async def frames():
            while not live.closed.is_set():
                yield b"\x00\x00" * 480
                await asyncio.sleep(0.01)

        async def delegate(*args):
            await asyncio.sleep(0.05)
            return "OUTDATED_ACCEPTANCE"

        async def output(raw):
            pass

        await live.run(frames(), output, delegate, greeting="Preséntate.")

    asyncio.run(scenario())
    assert not any(e.get("content") == "OUTDATED_ACCEPTANCE" for e in socket.sent)
    assert any(
        e["type"] == "session.thinking.append" and e.get("delegation_id") == "deleg-1" for e in socket.sent
    )


def test_live_provider_errors_are_controlled_and_not_exposed(settings):
    settings.openai_api_key = SecretStr("fake-key")
    socket = FakeLiveSocket(error=True)

    async def scenario():
        live = LiveSession(settings, "Prompt", connector=FakeConnector(socket))

        async def frames():
            yield b"\0\0" * 100
            await asyncio.sleep(1)

        async def output(raw):
            pass

        async def delegate(*args):
            return "unused"

        with pytest.raises(LiveProtocolError, match="rejected a session command") as error:
            await live.run(frames(), output, delegate, greeting="Preséntate.")
        assert "private-provider-detail" not in str(error.value)

    asyncio.run(scenario())


def test_silent_protocol_session_closes_at_limit_without_delegation_or_confirmation(settings):
    settings.openai_api_key = SecretStr("fake-key-never-sent")
    settings.voice_max_seconds = 0.1

    class SilentSocket(FakeLiveSocket):
        async def send(self, raw):
            event = json.loads(raw)
            self.sent.append(event)
            if event["type"] == "session.start":
                await self.incoming.put({"type": "session.started", "session": {"id": "silent-fixture"}})
            elif event["type"] == "session.close":
                await self.incoming.put({"type": "session.closed"})

    socket = SilentSocket()
    delegated = []

    async def scenario():
        live = LiveSession(settings, "Protocol fixture", connector=FakeConnector(socket))

        async def frames():
            while not live.closed.is_set():
                yield b"\0\0" * 480
                await asyncio.sleep(0.01)

        async def output(raw):
            raise AssertionError("The silent fixture must not fabricate output audio")

        async def delegate(*args):
            delegated.append(True)

        await asyncio.wait_for(live.run(frames(), output, delegate, greeting="Prueba de silencio"), 2)
        assert live.closed.is_set() and not live.transcripts

    asyncio.run(scenario())
    assert not delegated
    assert sum(e["type"] == "session.start" for e in socket.sent) == 1
    assert any(e["type"] == "session.close" for e in socket.sent)


def test_protocol_disconnect_does_not_reconnect_or_fabricate_a_result(settings):
    settings.openai_api_key = SecretStr("fake-key-never-sent")

    class DisconnectedSocket(FakeLiveSocket):
        async def send(self, raw):
            event = json.loads(raw)
            self.sent.append(event)
            if event["type"] == "session.start":
                await self.incoming.put({"type": "session.started", "session": {"id": "disconnect-fixture"}})
                await self.incoming.put({"type": "fixture.disconnect"})

        async def __anext__(self):
            event = await self.incoming.get()
            if event["type"] == "fixture.disconnect":
                raise StopAsyncIteration
            return json.dumps(event)

    socket = DisconnectedSocket()

    async def scenario():
        live = LiveSession(settings, "Protocol fixture", connector=FakeConnector(socket))

        async def frames():
            while True:
                yield b"\0\0" * 480
                await asyncio.sleep(0.01)

        async def unused(*args):
            raise AssertionError("No output or delegation expected")

        with pytest.raises(LiveProtocolError, match="ended without session.closed"):
            await asyncio.wait_for(live.run(frames(), unused, unused, greeting="Prueba de desconexión"), 2)
        assert not live.transcripts and live.socket is None

    asyncio.run(scenario())
    assert sum(e["type"] == "session.start" for e in socket.sent) == 1
