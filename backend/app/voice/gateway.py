import asyncio
import hashlib
import re
import secrets
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from urllib.parse import parse_qsl

from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from sqlalchemy import select
from starlette.datastructures import FormData
from twilio.request_validator import RequestValidator

from app.ai.models import AIExecution, VoiceCallSession
from app.core.config import get_settings
from app.db.session import Database
from app.models import CallAttempt, ReservationOffer, now
from app.observability.recorder import append, bind, ensure_execution, observed_span, record, usage_projection
from app.repositories import require_booking, require_restaurant
from app.services.bookings import emit
from app.services.execution import finish_attempt
from app.voice.delegation import VoiceDelegationService
from app.voice.live import LiveProtocolError, LiveSession
from app.voice.telephony import TwilioTransport


def signed_url(settings, path, *, websocket=False):
    origin = (settings.telephony_public_origin or "").rstrip("/")
    if websocket:
        origin = origin.replace("https://", "wss://", 1)
    return origin + path


def valid_signature(settings, path, signature, params=None, *, websocket=False):
    if not settings.real_telephony_enabled or not settings.twilio_auth_token or not signature:
        return False
    validator = RequestValidator(settings.twilio_auth_token.get_secret_value())
    urls = [signed_url(settings, path, websocket=websocket)]
    if websocket:
        # HTTP upgrade/proxy variants, always pinned to the configured origin and exact media path.
        urls += [urls[0] + "/", signed_url(settings, path), signed_url(settings, path) + "/"]
    return any(validator.validate(url, params or {}, signature) for url in urls)


def bind_stream(db, settings, event):
    start = event.get("start", {})
    params = start.get("customParameters", {})
    token, session_id = params.get("media_token"), params.get("session_id")
    if not isinstance(token, str) or not isinstance(session_id, str):
        raise LiveProtocolError("Missing stream authorization")
    with db.transaction(write=True) as session:
        call = session.get(VoiceCallSession, session_id)
        if call is None or not secrets.compare_digest(
            call.media_token_hash, hashlib.sha256(token.encode()).hexdigest()
        ):
            raise LiveProtocolError("Stream authorization failed")
        execution = session.get(AIExecution, call.execution_id)
        booking = require_booking(session, execution.booking_id)
        if call.connected_once or call.transport_state != "DIALING" or booking.status != "RUNNING":
            raise LiveProtocolError("Stream is not eligible for connection or replay")
        if (
            start.get("accountSid") != settings.twilio_account_sid
            or not call.external_call_sid
            or start.get("callSid") != call.external_call_sid
        ):
            raise LiveProtocolError("Unrecognized account or call SID")
        if start.get("mediaFormat") != {"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1}:
            raise LiveProtocolError("Unsupported telephony audio format")
        stream_sid = start.get("streamSid")
        if (
            not isinstance(stream_sid, str)
            or not stream_sid.startswith("MZ")
            or event.get("streamSid") != stream_sid
        ):
            raise LiveProtocolError("Invalid stream SID")
        call.connected_once, call.transport_state = True, "ACTIVE"
        append(
            session,
            execution.id,
            "voice.transport",
            "stream_bound",
            call_attempt_id=call.attempt_id,
            data={"transport_state": "ACTIVE", "provider_stream_id": stream_sid},
        )
        return call.id, execution.booking_id, stream_sid, execution.prompts["voice"]["text"]


async def serve_phone(
    websocket, db, settings, saver, call_id, booking_id, stream_sid, prompt, *, live_factory=LiveSession
):
    audio = asyncio.Queue(maxsize=50)
    stopped = asyncio.Event()
    delegate_service = VoiceDelegationService(db, settings, saver)
    live = live_factory(settings, prompt, codec="pcmu")
    with db.transaction(write=True) as session:
        call = session.get(VoiceCallSession, call_id)
        execution = session.get(AIExecution, call.execution_id)
        ensure_execution(session, require_booking(session, booking_id), settings=settings)
        execution_id, attempt_id = execution.id, call.attempt_id
    live.observer = lambda kind, phase, **values: record(
        db, execution_id, kind, phase, call_attempt_id=attempt_id, **values
    )
    last_action = None
    stream_sequence = 1

    async def receive_twilio():
        nonlocal stream_sequence
        first_media = True
        last_timestamp = None
        try:
            while True:
                message = await websocket.receive_json()
                if message.get("streamSid") != stream_sid:
                    raise LiveProtocolError("Stream identifier changed")
                sequence = int(message.get("sequenceNumber", 0))
                if sequence <= stream_sequence:
                    raise LiveProtocolError("Out-of-order or repeated audio packet")
                stream_sequence = sequence
                kind = message.get("event")
                if kind == "stop":
                    record(
                        db,
                        execution_id,
                        "voice.transport",
                        "stopped",
                        call_attempt_id=attempt_id,
                        data={"provider_sequence": sequence, "provider_end_ms": last_timestamp},
                    )
                    return
                if kind == "media":
                    import base64

                    raw = base64.b64decode(message["media"]["payload"], validate=True)
                    last_timestamp = message["media"].get("timestamp")
                    if first_media:
                        record(
                            db,
                            execution_id,
                            "voice.transport",
                            "media_observed",
                            call_attempt_id=attempt_id,
                            data={"provider_sequence": sequence, "provider_start_ms": last_timestamp},
                        )
                        first_media = False
                    if not raw or len(raw) > 8000:
                        raise LiveProtocolError("Invalid telephony audio packet")
                    await audio.put(raw)
        finally:
            stopped.set()

    async def audio_input():
        while not stopped.is_set():
            try:
                yield await asyncio.wait_for(audio.get(), timeout=0.1)
            except TimeoutError:
                continue

    async def output(raw):
        import base64

        await websocket.send_json(
            {"event": "media", "streamSid": stream_sid, "media": {"payload": base64.b64encode(raw).decode()}}
        )

    async def clear():
        await websocket.send_json({"event": "clear", "streamSid": stream_sid})

    async def on_started(session_id):
        with db.transaction(write=True) as session:
            session.get(VoiceCallSession, call_id).external_session_id = session_id

    async def delegate(text, identity, revision):
        return await delegate_service.handle(
            text,
            identity,
            revision,
            booking_id=booking_id,
            call_session_id=call_id,
            is_current=lambda: revision == live.revision,
        )

    async def control(connection):
        nonlocal last_action
        with db.transaction(write=True) as session:
            call = session.get(VoiceCallSession, call_id)
            booking = require_booking(session, booking_id)
            expired = datetime.now(UTC) >= datetime.fromisoformat(call.deadline)
            approval_expired = (
                booking.status == "WAITING_FOR_USER"
                and call.approval_deadline
                and datetime.now(UTC) >= datetime.fromisoformat(call.approval_deadline)
            )
            if approval_expired:
                for offer in session.scalars(
                    select(ReservationOffer).where(ReservationOffer.attempt_id == call.attempt_id)
                ):
                    offer.approval_pending = False
                finish_attempt(session.get(CallAttempt, call.attempt_id), "TIMEOUT", "FAILED")
                booking.status, booking.finished_at, call.action = "FAILED", now(), "STOP"
                emit(session, booking, "booking.failed")
            action = call.action
            should_stop = (
                stopped.is_set()
                or expired
                or action in {"STOP", "RECONCILE", "NO_AVAILABILITY", "DECLINED_AI", "AMBIGUOUS"}
                or booking.status in {"CANCELLED", "FAILED", "EXHAUSTED"}
            )
            accepted = call.accepted_offer
        if action == "ACCEPT" and last_action != action:
            await connection.append(
                "El motor autoriza aceptar únicamente estas condiciones: "
                + str(accepted)[:400]
                + ". Pide confirmación explícita de fecha, hora, personas, nombre y requisitos.",
                kind="instructions",
            )
        last_action = action
        return should_stop

    reader = asyncio.create_task(receive_twilio())
    try:
        with (
            bind(execution_id=execution_id, call_attempt_id=attempt_id, call_session_id=call_id),
            observed_span(
                db, execution_id, "voice.session", agent="voice", model=settings.voice_model
            ) as observation,
        ):
            usage = await live.run(
                audio_input(),
                output,
                delegate,
                on_started=on_started,
                on_clear=clear,
                control=control,
                greeting="Preséntate como asistente de IA que llama para consultar una reserva. Pregunta si puedes continuar.",
            )
            observation.usage = usage_projection(usage)
            observation.reported_model = getattr(live, "reported_model", None)
        with db.transaction(write=True) as session:
            session.get(VoiceCallSession, call_id).usage = usage_projection(usage)
    finally:
        reader.cancel()
        await asyncio.gather(reader, return_exceptions=True)
        await delegate_service.aclose()
        with db.transaction() as session:
            call = session.get(VoiceCallSession, call_id)
            sid, uncertain = (
                call.external_call_sid,
                bool(call.accepted_offer and not call.evidence) or call.action == "RECONCILE",
            )
        terminal = False
        if sid:
            try:
                result = await TwilioTransport(settings).hangup(sid)
                terminal = result.get("status") in {"completed", "canceled", "failed", "busy", "no-answer"}
            except Exception:  # noqa: BLE001 -- transport uncertainty is persisted; never retry dialing
                terminal = False
        with db.transaction(write=True) as session:
            call = session.get(VoiceCallSession, call_id)
            call.transport_state = "ENDED" if terminal and not uncertain else "UNCERTAIN"
            call.ended_at = now()
            append(
                session,
                execution_id,
                "voice.transport",
                "closed",
                call_attempt_id=attempt_id,
                data={"transport_state": call.transport_state},
            )


def create_gateway(settings=None):
    settings = settings or get_settings()
    db = Database(settings.database_url)

    @asynccontextmanager
    async def lifespan(app):
        from pathlib import Path

        checkpoint = str(Path(db.engine.url.database).resolve()) + ".ai-checkpoints.sqlite"
        async with AsyncSqliteSaver.from_conn_string(checkpoint) as saver:
            await saver.setup()
            app.state.saver = saver
            yield
        db.engine.dispose()

    # Deliberately separate ASGI app: no business routes, Swagger, CORS or local token exposure.
    app = FastAPI(
        title="Isolated voice gateway", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan
    )
    app.state.db, app.state.settings = db, settings

    @app.post("/twilio/status/{session_id}")
    async def status_callback(request: Request, session_id: str):
        body = await request.body()
        if len(body) > 64000 or request.url.query:
            return Response(status_code=403)
        try:
            params = FormData(parse_qsl(body.decode(), keep_blank_values=True))
        except (ValueError, UnicodeError):
            return Response(status_code=403)
        if not valid_signature(settings, request.url.path, request.headers.get("x-twilio-signature"), params):
            return Response(status_code=403)
        with db.transaction(write=True) as session:
            call = session.get(VoiceCallSession, session_id)
            if call is None or params.get("AccountSid") != settings.twilio_account_sid:
                return Response(status_code=403)
            if params.get("To") != require_restaurant(session, call.restaurant_id).phone:
                return Response(status_code=403)
            sid = params.get("CallSid")
            if (
                not isinstance(sid, str)
                or not re.fullmatch(r"CA[0-9a-fA-F]{32}", sid)
                or (call.external_call_sid and call.external_call_sid != sid)
            ):
                return Response(status_code=403)
            call.external_call_sid = sid
            append(
                session,
                call.execution_id,
                "voice.transport",
                "callback",
                call_attempt_id=call.attempt_id,
                data={"transport_status": params.get("CallStatus")},
            )
            if params.get("CallStatus") in {"completed", "canceled", "failed", "busy", "no-answer"}:
                call.transport_state = (
                    "UNCERTAIN"
                    if call.accepted_offer and not call.evidence or call.action == "RECONCILE"
                    else "ENDED"
                )
                call.ended_at = now()
        return Response(status_code=204)

    @app.websocket("/twilio/media")
    async def media(websocket: WebSocket):
        if websocket.url.query or not valid_signature(
            settings, websocket.url.path, websocket.headers.get("x-twilio-signature"), websocket=True
        ):
            await websocket.close(code=1008)
            return
        await websocket.accept()
        try:
            first = await asyncio.wait_for(websocket.receive_json(), timeout=5)
            if first.get("event") == "connected":
                first = await asyncio.wait_for(websocket.receive_json(), timeout=5)
            if first.get("event") != "start":
                raise LiveProtocolError("Expected authenticated stream startup")
            # A fast carrier can connect before the outbound HTTP response has been persisted.
            for _ in range(30):
                session_id = first.get("start", {}).get("customParameters", {}).get("session_id")
                with db.transaction() as session:
                    row = session.get(VoiceCallSession, session_id) if isinstance(session_id, str) else None
                    ready = row is not None and row.external_call_sid is not None
                if ready or row is None:
                    break
                await asyncio.sleep(0.1)
            call_id, booking_id, stream_sid, prompt = bind_stream(db, settings, first)
            await serve_phone(
                websocket, db, settings, app.state.saver, call_id, booking_id, stream_sid, prompt
            )
        except (WebSocketDisconnect, ValueError, LiveProtocolError, TimeoutError):
            with suppress(RuntimeError):
                await websocket.close(code=1008)

    return app


if __name__ == "__main__":
    import uvicorn

    config = get_settings()
    uvicorn.run(
        create_gateway(config), host="127.0.0.1", port=config.telephony_gateway_port, access_log=False
    )
