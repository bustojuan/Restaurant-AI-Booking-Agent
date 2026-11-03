import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from langchain_core.tools import StructuredTool
from sqlalchemy import select

from app.ai.agents import NegotiationAgent, VerificationAgent
from app.ai.contracts import ReservationEvidence
from app.ai.models import AIExecution, ToolOperation, VoiceCallSession
from app.ai.observability import span
from app.core.errors import DomainError
from app.db.session import Database
from app.models import CallAttempt
from app.observability.recorder import bind, context, observed_span, tool_io
from app.repositories import attempts, queue, require_booking
from app.schemas import BookingConfiguration, Contract, OfferDetails
from app.services.bookings import summary


class NoArgs(Contract):
    pass


class EvaluateArgs(Contract):
    offer: OfferDetails


class EvidenceArgs(Contract):
    evidence: ReservationEvidence


@dataclass(frozen=True)
class ToolScope:
    execution_id: str
    booking_id: str
    agent: str
    attempt_id: str | None = None


PERMISSIONS = {
    "supervisor": {
        "get_booking_status",
        "get_next_restaurant",
        "get_booking_priority_queue",
        "persist_call_outcome",
    },
    "planning": {"get_booking_requirements", "get_booking_priority_queue"},
    "research": {"get_restaurant_information", "get_previous_attempts"},
    "voice": {
        "get_booking_requirements",
        "get_current_call_context",
        "evaluate_alternative",
        "request_user_approval",
        "submit_reservation_evidence",
        "finish_call",
    },
    "negotiation": {"get_booking_requirements", "evaluate_alternative"},
    "verification": {"get_current_call_context", "verify_reservation"},
    "memory": {"get_booking_status", "get_previous_attempts"},
    "evaluation": {"get_booking_status", "get_previous_attempts", "get_booking_priority_queue"},
}
MUTATIONS = {"persist_call_outcome", "request_user_approval", "submit_reservation_evidence", "finish_call"}


class AgentTools:
    """Capabilities are bound by application code. Models never choose execution/booking IDs."""

    def __init__(self, db: Database, scope: ToolScope, advance: Callable[[], Awaitable[None]] | None = None):
        self.db, self.scope, self.advance = db, scope, advance

    def authorize(self, name: str):
        if name not in PERMISSIONS.get(self.scope.agent, set()):
            raise DomainError("tool_forbidden", "Tool is not permitted for this agent", 403)
        with self.db.transaction() as session:
            execution = session.get(AIExecution, self.scope.execution_id)
            if execution is None or execution.booking_id != self.scope.booking_id:
                raise DomainError("tool_scope_invalid", "Invalid execution scope", 403)
            if self.scope.attempt_id:
                attempt = session.get(CallAttempt, self.scope.attempt_id)
                if attempt is None or attempt.booking_id != self.scope.booking_id:
                    raise DomainError("tool_scope_invalid", "Attempt is outside execution scope", 403)

    async def invoke(
        self, name: str, arguments: dict | None = None, *, operation_id: str | None = None
    ) -> dict:
        self.authorize(name)
        args = arguments or {}
        schema = (
            EvaluateArgs
            if name in {"evaluate_alternative", "request_user_approval"}
            else EvidenceArgs
            if name in {"verify_reservation", "submit_reservation_evidence"}
            else NoArgs
        )
        parsed = schema.model_validate(args)
        digest = hashlib.sha256(
            json.dumps(parsed.model_dump(mode="json"), sort_keys=True).encode()
        ).hexdigest()
        cached_output = None
        if name in MUTATIONS:
            if not operation_id:
                raise DomainError("operation_id_required", "Mutating tools require an operation ID", 422)
            with self.db.transaction(write=True) as session:
                previous = session.get(ToolOperation, operation_id)
                if previous:
                    if (
                        previous.execution_id != self.scope.execution_id
                        or previous.tool != name
                        or previous.input_hash != digest
                    ):
                        raise DomainError(
                            "idempotency_conflict", "Operation ID is already bound to a different action"
                        )
                    if previous.result.get("state") != "COMPLETED":
                        raise DomainError(
                            "operation_uncertain", "Reconcile the previous operation before retrying"
                        )
                    cached_output = previous.result["output"]
                else:
                    session.add(
                        ToolOperation(
                            id=operation_id,
                            execution_id=self.scope.execution_id,
                            tool=name,
                            input_hash=digest,
                            result={"state": "STARTED"},
                        )
                    )
        if cached_output is not None:
            with (
                bind(call_attempt_id=self.scope.attempt_id),
                observed_span(
                    self.db,
                    self.scope.execution_id,
                    "tool",
                    agent=self.scope.agent,
                    tool=name,
                    input=tool_io(name, args),
                ) as observation,
            ):
                observation.output = tool_io(name, cached_output, output=True)
                observation.cached = True
            return cached_output
        with (
            bind(call_attempt_id=self.scope.attempt_id or context.get().get("call_attempt_id")),
            span(
                self.db, self.scope.execution_id, self.scope.agent, name, input=tool_io(name, args)
            ) as observation,
        ):
            output = await self._dispatch(name, parsed)
            observation.output = tool_io(name, output, output=True)
        if name in MUTATIONS:
            with self.db.transaction(write=True) as session:
                session.get(ToolOperation, operation_id).result = {"state": "COMPLETED", "output": output}
        return output

    async def _dispatch(self, name: str, args) -> dict:
        if name == "persist_call_outcome":
            if self.advance is None:
                raise DomainError("tool_forbidden", "Only the coordinator can advance execution", 403)
            await self.advance()
        with self.db.transaction(write=name in MUTATIONS) as session:
            booking = require_booking(session, self.scope.booking_id)
            config = BookingConfiguration.model_validate(booking.configuration)
            snap = summary(session, booking)
            if name in {"get_booking_status", "persist_call_outcome"}:
                return {
                    "status": snap.status,
                    "version": snap.version,
                    "completed_attempts": snap.completed_attempts,
                    "confirmation_id": snap.confirmation.id if snap.confirmation else None,
                }
            if name == "get_booking_requirements":
                return config.model_dump(mode="json", exclude={"contact_phone"})
            if name == "get_booking_priority_queue":
                return {"restaurant_ids": [r.restaurant_id for r in queue(session, booking.id)]}
            calls = attempts(session, booking.id)
            active = next((c for c in calls if c.status == "RUNNING"), None)
            if self.scope.attempt_id:
                active = session.get(CallAttempt, self.scope.attempt_id)
            contacted = {c.restaurant_id for c in calls}
            next_row = next((r for r in queue(session, booking.id) if r.restaurant_id not in contacted), None)
            restaurant_id = active.restaurant_id if active else next_row.restaurant_id if next_row else None
            if name == "get_next_restaurant":
                return {"restaurant_id": restaurant_id, "attempt_id": active.id if active else None}
            if name == "get_previous_attempts":
                return {
                    "attempts": [
                        {"id": c.id, "restaurant_id": c.restaurant_id, "result": c.result} for c in calls
                    ]
                }
            if name == "get_restaurant_information":
                # Resolve in the SAME read snapshot; no provider fetch or cross-booking lookup.
                if restaurant_id is None:
                    return {"restaurant_id": None, "observations": []}
                from app.repositories import require_restaurant

                restaurant = require_restaurant(session, restaurant_id)
                return {
                    "restaurant_id": restaurant_id,
                    "name": restaurant.name,
                    "phone": restaurant.phone,
                    "municipality": restaurant.municipality,
                    "is_simulated": restaurant.is_simulated,
                }
            if name == "get_current_call_context":
                return {
                    "booking_id": booking.id,
                    "attempt_id": active.id if active else None,
                    "restaurant_id": restaurant_id,
                    "status": active.status if active else None,
                }
            if name == "evaluate_alternative":
                return NegotiationAgent().evaluate(config, args.offer).model_dump(mode="json")
            if active is None or booking.status not in {"RUNNING", "WAITING_FOR_USER"}:
                raise DomainError("no_active_call", "No active call is authorized")
            call = session.scalar(select(VoiceCallSession).where(VoiceCallSession.attempt_id == active.id))
            if name == "verify_reservation":
                if call is None or call.accepted_offer is None:
                    return {"status": "PENDING", "reasons": ["no_authorized_acceptance"]}
                return (
                    VerificationAgent()
                    .verify(
                        config,
                        restaurant_id,
                        active.id,
                        OfferDetails.model_validate(call.accepted_offer),
                        args.evidence,
                        approved=False,
                    )
                    .model_dump(mode="json")
                )
            if (
                call is None
                or call.execution_id != self.scope.execution_id
                or call.transport_state != "ACTIVE"
            ):
                raise DomainError("no_active_call", "An authenticated active phone session is required")
            if name == "request_user_approval":
                decision = NegotiationAgent().evaluate(config, args.offer)
                if decision.evaluation != "REQUIRES_USER_APPROVAL":
                    raise DomainError("approval_not_required", "Offer does not require user approval")
                call.proposed_offer = args.offer.model_dump(mode="json")
                return {"queued_for_business_validation": True}
            if name == "submit_reservation_evidence":
                if call.accepted_offer is None:
                    raise DomainError("acceptance_not_authorized", "No authorized offer exists")
                from app.models import ReservationOffer

                approved = (
                    session.scalar(
                        select(ReservationOffer).where(
                            ReservationOffer.attempt_id == active.id, ReservationOffer.decision == "APPROVED"
                        )
                    )
                    is not None
                )
                verification = VerificationAgent().verify(
                    config,
                    restaurant_id,
                    active.id,
                    OfferDetails.model_validate(call.accepted_offer),
                    args.evidence,
                    approved=approved,
                )
                call.evidence = args.evidence.model_dump(mode="json")
                return verification.model_dump(mode="json")
            if name == "finish_call":
                call.action = "STOP"
                return {"stop_requested": True}
        raise DomainError("unknown_tool", "Unknown tool", 422)

    def as_langchain_tools(self) -> list[StructuredTool]:
        result = []
        for name in sorted(PERMISSIONS[self.scope.agent] - MUTATIONS):

            async def run_tool(_tool_name=name, **kwargs):
                return await self.invoke(_tool_name, kwargs)

            schema = (
                EvaluateArgs
                if name == "evaluate_alternative"
                else EvidenceArgs
                if name == "verify_reservation"
                else NoArgs
            )
            result.append(
                StructuredTool.from_function(
                    name=name,
                    description=f"Scoped backend capability: {name}",
                    coroutine=run_tool,
                    args_schema=schema,
                )
            )
        return result
