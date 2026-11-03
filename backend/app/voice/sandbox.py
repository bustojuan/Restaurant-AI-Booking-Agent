import asyncio
import json
import secrets
from contextlib import suppress
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.ai.agents import PlanningAgent
from app.ai.prompts import prompt_bundle
from app.core.errors import DomainError
from app.models import now
from app.observability.models import ObservedExecution
from app.observability.recorder import bind, ensure_execution, observed_span, record, usage_projection
from app.repositories import require_booking
from app.schemas import BookingConfiguration
from app.voice.delegation import VoiceDelegationService
from app.voice.live import LiveProtocolError, LiveSession

router = APIRouter(prefix="/api/voice")


@router.websocket("/sandbox/ws")
async def voice_sandbox(websocket: WebSocket, booking_id: str):
    settings = websocket.app.state.settings
    origin = websocket.headers.get("origin")
    if origin is not None and origin not in settings.cors_origins:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    live = None
    delegate_service = None
    sandbox_id = str(uuid4())
    try:
        auth = await asyncio.wait_for(websocket.receive_json(), timeout=5)
        if (
            not isinstance(auth, dict)
            or not isinstance(auth.get("token"), str)
            or not secrets.compare_digest(
                auth["token"].encode(), settings.local_api_token.get_secret_value().encode()
            )
        ):
            await websocket.close(code=1008)
            return
        if not settings.voice_sandbox_enabled or not settings.openai_api_key:
            await websocket.send_json({"type": "error", "code": "voice_sandbox_not_configured"})
            await websocket.close(code=1008)
            return
        if auth.get("allow_api_costs") is not True or auth.get("audio_processing_consent") is not True:
            await websocket.close(code=1008)
            return
        with websocket.app.state.db.transaction() as session:
            booking = require_booking(session, booking_id)
            if booking.status != "DRAFT":
                raise DomainError("sandbox_requires_draft", "Use a draft for voice sandbox", 409)
            config = BookingConfiguration.model_validate(booking.configuration)
        with websocket.app.state.db.transaction(write=True) as session:
            ensure_execution(
                session,
                require_booking(session, booking_id),
                execution_id=sandbox_id,
                mode="voice_sandbox",
                prompts=prompt_bundle(),
                settings=settings,
            )
        briefing = PlanningAgent().plan(config).voice_briefing
        prompt = (
            prompt_bundle()["voice"]["text"] + "\nPrueba local sin llamadas ni reservas reales.\n" + briefing
        )
        live = LiveSession(settings, prompt)
        live.observer = lambda kind, phase, **values: record(
            websocket.app.state.db, sandbox_id, kind, phase, **values
        )
        delegate_service = VoiceDelegationService(
            websocket.app.state.db, settings, websocket.app.state.ai.saver
        )

        async def input_audio():
            while True:
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    return
                if message.get("bytes") is not None:
                    yield message["bytes"]
                elif message.get("text"):
                    command = json.loads(message["text"])
                    if command.get("type") == "close":
                        return
                    raise LiveProtocolError("Unsupported sandbox command")

        async def on_started(session_id):
            await websocket.send_json(
                {
                    "type": "session.ready",
                    "session_id": session_id,
                    "execution_id": sandbox_id,
                    "booking_id": booking_id,
                    "mode": "voice_sandbox",
                    "codec": "pcm16",
                    "sample_rate": 24000,
                    "channels": 1,
                }
            )

        async def clear():
            await websocket.send_json({"type": "audio.clear"})

        async def delegate(text, identity, revision):
            return await delegate_service.handle(
                text,
                identity,
                revision,
                booking_id=booking_id,
                sandbox_id=sandbox_id,
                is_current=lambda: revision == live.revision,
            )

        with (
            bind(execution_id=sandbox_id, call_session_id=sandbox_id),
            observed_span(
                websocket.app.state.db, sandbox_id, "voice.session", agent="voice", model=settings.voice_model
            ) as observation,
        ):
            usage = await live.run(
                input_audio(),
                websocket.send_bytes,
                delegate,
                on_started=on_started,
                on_clear=clear,
                greeting="Preséntate como asistente de IA en una prueba de voz local sin reservar ni llamar. Pregunta si empezamos.",
            )
            observation.usage = usage_projection(usage)
            observation.reported_model = getattr(live, "reported_model", None)
        await websocket.send_json({"type": "session.closed", "usage": usage})
        await websocket.close()
    except (WebSocketDisconnect, RuntimeError, ValueError, TimeoutError, DomainError):
        with suppress(RuntimeError, WebSocketDisconnect):
            await websocket.send_json(
                {"type": "error", "code": "voice_session_ended_without_verified_finalization"}
            )
            await websocket.close(code=1011)
    finally:
        with websocket.app.state.db.transaction(write=True) as session:
            run = session.get(ObservedExecution, sandbox_id)
            if run:
                run.ended_at = now()
        if delegate_service:
            await delegate_service.aclose()
        # Sandbox has no external effects and its conversational checkpoints are ephemeral.
        if live:
            for identity in live.delegations:
                await websocket.app.state.ai.saver.adelete_thread(f"voice:{sandbox_id}:{identity}")
