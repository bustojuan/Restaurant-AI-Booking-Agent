from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from app.ai.models import AIExecution, VoiceCallSession
from app.ai.observability import trace
from app.api.dependencies import Version, authenticate
from app.core.errors import DomainError
from app.models import now
from app.observability.recorder import append
from app.repositories import require_booking, require_restaurant
from app.schemas import Contract
from app.services.bookings import check_version, emit
from app.voice.telephony import TwilioTransport

router = APIRouter(prefix="/api/voice", dependencies=[Depends(authenticate)], tags=["Voice"])


class ReconciliationInput(Contract):
    # Explicit operator attestation; this capability is never exposed to an agent.
    no_reservation_verified_by_user: bool = False


@router.get("/bookings/{booking_id}/calls")
def calls(request: Request, booking_id: str) -> list[dict]:
    with request.app.state.db.transaction() as session:
        require_booking(session, booking_id)
        execution = session.scalar(select(AIExecution).where(AIExecution.booking_id == booking_id))
        if execution is None:
            return []
        return [
            {
                "id": call.id,
                "attempt_id": call.attempt_id,
                "restaurant_id": call.restaurant_id,
                "transport_state": call.transport_state,
                "external_call_sid": call.external_call_sid,
                "external_session_id": call.external_session_id,
                "action": call.action,
                "reserved_cost_eur": call.reserved_cost_eur,
                "usage": call.usage,
                "deadline": call.deadline,
                "ended_at": call.ended_at,
            }
            for call in session.scalars(
                select(VoiceCallSession)
                .where(VoiceCallSession.execution_id == execution.id)
                .order_by(VoiceCallSession.created_at)
            )
        ]


@router.post("/calls/{call_id}/reconcile")
async def reconcile(request: Request, call_id: str, payload: ReconciliationInput, version: Version) -> dict:
    settings = request.app.state.settings
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        raise DomainError(
            "credentials_missing", "Twilio credentials are required to inspect the external call", 422
        )
    with request.app.state.db.transaction() as session:
        call = session.get(VoiceCallSession, call_id)
        if call is None:
            raise DomainError("not_found", "Call not found", 404)
        execution = session.get(AIExecution, call.execution_id)
        booking = require_booking(session, execution.booking_id)
        check_version(booking, version)
        if booking.status not in {"FAILED", "CANCELLED"}:
            raise DomainError("invalid_transition", "Only stopped executions can be reconciled")
        if not call.external_call_sid:
            raise DomainError(
                "external_id_unknown",
                "Find the original call in Twilio; automatic reconciliation is unavailable",
            )
        sid, phone, booking_id = (
            call.external_call_sid,
            require_restaurant(session, call.restaurant_id).phone,
            booking.id,
        )
    observed = await TwilioTransport(settings).inspect(sid)
    if (
        observed.get("sid") != sid
        or observed.get("account_sid") != settings.twilio_account_sid
        or observed.get("to") != phone
    ):
        raise DomainError(
            "external_identity_mismatch", "Provider call does not match the stored destination", 403
        )
    terminal = observed.get("status") in {"completed", "canceled", "failed", "busy", "no-answer"}
    if payload.no_reservation_verified_by_user:
        if not terminal:
            raise DomainError("call_not_ended", "The provider has not confirmed termination")
        with request.app.state.db.transaction(write=True) as session:
            booking = require_booking(session, booking_id)
            check_version(booking, version)
            call = session.get(VoiceCallSession, call_id)
            call.transport_state, call.action, call.ended_at = "ENDED", "RECONCILED_NO_RESERVATION", now()
            append(
                session,
                execution.id,
                "backend.call_reconciliation",
                "committed",
                call_attempt_id=call.attempt_id,
                data={
                    "backend_action": call.action,
                    "operator_attested_no_reservation": True,
                    "transport_state": call.transport_state,
                },
            )
            emit(session, booking, "booking.updated")
        trace(
            request.app.state.db,
            execution.id,
            "verification",
            "completed",
            tool="operator_reconciliation",
            details={"operator_attested_no_reservation": True},
        )
    return {
        "call_ended": terminal,
        "reservation_reconciled": payload.no_reservation_verified_by_user and terminal,
        "automatic_redial": False,
        "business_status": booking.status,
    }
