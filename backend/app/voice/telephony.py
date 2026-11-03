import asyncio
import hashlib
import re
import secrets
from datetime import UTC, datetime, timedelta
from xml.etree.ElementTree import Element, SubElement, tostring

import httpx
from sqlalchemy import func, select

from app.ai.agents import VerificationAgent
from app.ai.contracts import ReservationEvidence
from app.ai.models import AIExecution, VoiceCallSession
from app.core.errors import DomainError
from app.models import CallAttempt, ReservationOffer, now
from app.observability.recorder import append, bind, ensure_execution, observed_span
from app.providers.calls import CallOutcome, ConfirmationEvidence, UncertainCallError
from app.repositories import require_booking, require_restaurant
from app.schemas import BookingConfiguration, CallAuthorization
from app.voice.authorization import estimated_call_cost, validate_authorization


def media_twiml(origin: str, token: str, session_id: str) -> str:
    root = Element("Response")
    connect = SubElement(root, "Connect")
    stream = SubElement(
        connect, "Stream", url=origin.replace("https://", "wss://", 1).rstrip("/") + "/twilio/media"
    )
    SubElement(stream, "Parameter", name="session_id", value=session_id)
    SubElement(stream, "Parameter", name="media_token", value=token)
    SubElement(root, "Hangup")
    return tostring(root, encoding="unicode")


class TwilioTransport:
    """No automatic POST retries. Never retry an ambiguous outbound request."""

    def __init__(self, settings, client=None):
        self.settings = settings
        self.client = client

    async def _post(self, path, data):
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.settings.twilio_account_sid}/{path}"

        async def send(client):
            response = await client.post(
                url,
                data=data,
                auth=(self.settings.twilio_account_sid, self.settings.twilio_auth_token.get_secret_value()),
            )
            response.raise_for_status()
            return response.json()

        if self.client:
            return await send(self.client)
        async with httpx.AsyncClient(timeout=10, transport=httpx.AsyncHTTPTransport(retries=0)) as client:
            return await send(client)

    async def dial(self, destination, twiml, callback_url, seconds):
        return await self._post(
            "Calls.json",
            {
                "To": destination,
                "From": self.settings.twilio_phone_number,
                "Twiml": twiml,
                "StatusCallback": callback_url,
                "StatusCallbackMethod": "POST",
                "StatusCallbackEvent": "completed",
                "Record": "false",
                "Timeout": "20",
                "TimeLimit": str(seconds),
            },
        )

    async def hangup(self, call_sid):
        return await self._post(f"Calls/{call_sid}.json", {"Status": "completed"})

    async def inspect(self, call_sid):
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.settings.twilio_account_sid}/Calls/{call_sid}.json"
        async with httpx.AsyncClient(timeout=10) as client:
            result = await client.get(
                url,
                auth=(self.settings.twilio_account_sid, self.settings.twilio_auth_token.get_secret_value()),
            )
            result.raise_for_status()
            return result.json()


class TwilioCallProvider:
    external_effects = True

    def __init__(self, db, execution_id, settings, *, transport=None):
        self.db, self.execution_id, self.settings = db, execution_id, settings
        self.transport = transport or TwilioTransport(settings)

    async def contact(self, config, restaurant_id, outcome, operation_id):
        token = secrets.token_urlsafe(32)
        with self.db.transaction(write=True) as session:
            execution = session.get(AIExecution, self.execution_id)
            attempt = session.get(CallAttempt, operation_id)
            booking = require_booking(session, execution.booking_id)
            if (
                attempt is None
                or attempt.booking_id != booking.id
                or attempt.restaurant_id != restaurant_id
                or booking.status != "RUNNING"
            ):
                raise DomainError("call_scope_invalid", "Call is outside the authorized active attempt", 403)
            authorization = CallAuthorization.model_validate(execution.authorization)
            validate_authorization(session, booking, authorization, self.settings)
            prior = session.scalar(
                select(VoiceCallSession).where(VoiceCallSession.attempt_id == operation_id)
            )
            if prior:
                raise UncertainCallError("Attempt already initiated; reconciliation required")
            count = session.scalar(
                select(func.count())
                .select_from(VoiceCallSession)
                .where(VoiceCallSession.execution_id == execution.id)
            )
            reserved = session.scalar(
                select(func.coalesce(func.sum(VoiceCallSession.reserved_cost_eur), 0)).where(
                    VoiceCallSession.execution_id == execution.id
                )
            )
            cost = estimated_call_cost(self.settings, authorization.max_duration_seconds)
            if count >= authorization.max_calls or reserved + cost > authorization.max_estimated_cost_eur:
                raise DomainError(
                    "call_limit_exceeded", "Authorized call count or estimated budget exhausted", 403
                )
            # Includes ringing: no unbounded holds or automatic callbacks.
            call = VoiceCallSession(
                execution_id=execution.id,
                attempt_id=operation_id,
                restaurant_id=restaurant_id,
                media_token_hash=hashlib.sha256(token.encode()).hexdigest(),
                transport_state="DIALING",
                deadline=(
                    datetime.now(UTC) + timedelta(seconds=authorization.max_duration_seconds)
                ).isoformat(),
                reserved_cost_eur=cost,
            )
            session.add(call)
            session.flush()
            call_id = call.id
            ensure_execution(session, booking, settings=self.settings)
            append(
                session,
                execution.id,
                "transport.dial",
                "prepared",
                call_attempt_id=attempt.id,
                data={"reserved_cost_eur": cost, "transport_state": call.transport_state},
            )
            destination = require_restaurant(session, restaurant_id).phone
        try:
            with (
                bind(call_attempt_id=operation_id),
                observed_span(self.db, self.execution_id, "transport.dial", agent="voice"),
            ):
                result = await self.transport.dial(
                    destination,
                    media_twiml(self.settings.telephony_public_origin, token, call_id),
                    self.settings.telephony_public_origin.rstrip("/") + f"/twilio/status/{call_id}",
                    authorization.max_duration_seconds,
                )
            sid = result.get("sid")
            if not isinstance(sid, str) or not re.fullmatch(r"CA[0-9a-fA-F]{32}", sid):
                raise UncertainCallError("No trustworthy external call identifier returned")
            with self.db.transaction(write=True) as session:
                call = session.get(VoiceCallSession, call_id)
                if call.external_call_sid and call.external_call_sid != sid:
                    raise UncertainCallError("Conflicting external call identifier")
                call.external_call_sid = sid
                append(
                    session,
                    self.execution_id,
                    "voice.transport",
                    "dial_response",
                    call_attempt_id=operation_id,
                    data={"transport_status": result.get("status")},
                )
        except (httpx.HTTPError, UncertainCallError):
            with self.db.transaction(write=True) as session:
                session.get(VoiceCallSession, call_id).transport_state = "UNCERTAIN"
                append(
                    session,
                    self.execution_id,
                    "voice.transport",
                    "uncertain",
                    call_attempt_id=operation_id,
                    data={"transport_state": "UNCERTAIN"},
                )
            raise UncertainCallError(
                "Outbound request outcome is uncertain; automatic retry is prohibited"
            ) from None
        while True:
            with self.db.transaction() as session:
                call = session.get(VoiceCallSession, call_id)
                booking = require_booking(session, execution.booking_id)
                if booking.status != "RUNNING":
                    raise UncertainCallError("Booking stopped during an external call")
                if call.transport_state == "UNCERTAIN":
                    raise UncertainCallError("External call state is uncertain")
                if call.action == "RECONCILE":
                    raise UncertainCallError("Unsolicited confirmation requires manual reconciliation")
                if call.proposed_offer:
                    from app.schemas import OfferDetails

                    return CallOutcome(result="OFFER", offer=OfferDetails.model_validate(call.proposed_offer))
                if call.transport_state == "ENDED":
                    return CallOutcome(
                        result=call.action
                        if call.action in {"NO_AVAILABILITY", "DECLINED_AI", "AMBIGUOUS"}
                        else "DISCONNECTED"
                    )
                expired = datetime.now(UTC) >= datetime.fromisoformat(call.deadline)
            if expired:
                await self._stop(call_id)
                raise UncertainCallError("Call duration elapsed before a conclusive outcome")
            await asyncio.sleep(0.1)

    async def before_advance(self, booking_id):
        with self.db.transaction() as session:
            uncertain = session.scalar(
                select(VoiceCallSession.id).where(
                    VoiceCallSession.execution_id == self.execution_id,
                    VoiceCallSession.transport_state == "UNCERTAIN",
                )
            )
            if uncertain:
                raise UncertainCallError("Reconcile the previous call before contacting another restaurant")
            ids = list(
                session.scalars(
                    select(VoiceCallSession.id)
                    .join(CallAttempt)
                    .where(
                        VoiceCallSession.execution_id == self.execution_id,
                        CallAttempt.status != "RUNNING",
                        VoiceCallSession.transport_state.in_(["ACTIVE", "DIALING", "UNCERTAIN"]),
                    )
                )
            )
        for call_id in ids:
            await self._stop(call_id)

    async def confirm(self, offer, *, operation_id, confirms_on_accept):
        with self.db.transaction(write=True) as session:
            call = session.scalar(
                select(VoiceCallSession).where(
                    VoiceCallSession.attempt_id == operation_id,
                    VoiceCallSession.execution_id == self.execution_id,
                )
            )
            if call is None or call.transport_state != "ACTIVE":
                raise UncertainCallError("Cannot accept an offer without an active authenticated call")
            call.accepted_offer, call.action = offer.model_dump(mode="json"), "ACCEPT"
            append(
                session,
                self.execution_id,
                "backend.voice_action",
                "committed",
                call_attempt_id=operation_id,
                data={"backend_action": "ACCEPT"},
            )
            call_id, restaurant_id = call.id, call.restaurant_id
        while True:
            with self.db.transaction() as session:
                call = session.get(VoiceCallSession, call_id)
                execution = session.get(AIExecution, self.execution_id)
                booking = require_booking(session, execution.booking_id)
                config = BookingConfiguration.model_validate(booking.configuration)
                if booking.status != "RUNNING":
                    raise UncertainCallError("Booking stopped while confirmation was pending")
                if call.evidence:
                    evidence = ReservationEvidence.model_validate(call.evidence)
                    approved = (
                        session.scalar(
                            select(ReservationOffer.id).where(
                                ReservationOffer.attempt_id == operation_id,
                                ReservationOffer.decision == "APPROVED",
                            )
                        )
                        is not None
                    )
                    verified = VerificationAgent().verify(
                        config, restaurant_id, operation_id, offer, evidence, approved=approved
                    )
                    if verified.status != "CONFIRMED":
                        raise UncertainCallError("Confirmation evidence is incomplete or contradictory")
                    confirmed = True
                else:
                    confirmed = False
                uncertain = call.transport_state in {"ENDED", "UNCERTAIN"} and not confirmed
                expired = datetime.now(UTC) >= datetime.fromisoformat(call.deadline)
            if confirmed:
                # Release the phone line and require an acknowledged terminal provider state first.
                await self._stop(call_id)
                return ConfirmationEvidence(
                    confirmed=True, reference=evidence.reference, simulated=False, reservation=evidence
                )
            if uncertain or expired:
                await self._stop(call_id)
                raise UncertainCallError("Connection closed or timed out during confirmation")
            await asyncio.sleep(0.1)

    async def _stop(self, call_id):
        with self.db.transaction(write=True) as session:
            call = session.get(VoiceCallSession, call_id)
            call.action = "STOP"
            append(
                session,
                self.execution_id,
                "backend.voice_action",
                "committed",
                call_attempt_id=call.attempt_id,
                data={"backend_action": "STOP"},
            )
            sid = call.external_call_sid
        if not sid:
            raise UncertainCallError("External call SID is unavailable")
        try:
            response = await self.transport.hangup(sid)
            terminal = response.get("status") in {"completed", "canceled", "failed", "busy", "no-answer"}
        except httpx.HTTPError:
            terminal = False
        with self.db.transaction(write=True) as session:
            call = session.get(VoiceCallSession, call_id)
            call.transport_state, call.ended_at = ("ENDED" if terminal else "UNCERTAIN"), now()
        if not terminal:
            raise UncertainCallError("External call termination has not been confirmed")
