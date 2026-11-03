import asyncio
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.db.session import Database
from app.models import (
    BookingRequest,
    CallAttempt,
    ReservationConfirmation,
    ReservationOffer,
    SimulationScenario,
    WorkspaceState,
    now,
)
from app.providers.calls import CallProvider, UncertainCallError
from app.repositories import attempts, queue, require_booking
from app.schemas import BookingConfiguration, BookingSummary, OfferDetails
from app.services.bookings import check_version, emit, summary
from app.services.negotiation import NegotiationPolicyService

logger = logging.getLogger(__name__)
TERMINAL = {"CONFIRMED", "EXHAUSTED", "CANCELLED", "FAILED"}


def finish_attempt(attempt: CallAttempt, result: str, status: str = "COMPLETED") -> None:
    attempt.status, attempt.result = status, result
    attempt.completed_at = now()
    attempt.duration_ms = max(
        0,
        int(
            (
                datetime.fromisoformat(attempt.completed_at) - datetime.fromisoformat(attempt.started_at)
            ).total_seconds()
            * 1000
        ),
    )


def start(
    session: Session,
    booking_id: str,
    expected: int,
    scenario_id: str,
    *,
    mode: str = "simulation",
    authorization=None,
    settings=None,
) -> BookingSummary:
    booking = require_booking(session, booking_id)
    # A retry cannot create a second run or switch the scenario of an existing run.
    if booking.started_at is not None and booking.scenario_id == scenario_id:
        from app.ai.models import AIExecution

        existing = session.scalar(select(AIExecution).where(AIExecution.booking_id == booking_id))
        if (existing.mode if existing else "simulation") != mode:
            raise DomainError("execution_mode_conflict", "An existing execution cannot change modes")
        return summary(session, booking)
    check_version(booking, expected)
    if booking.status != "DRAFT":
        raise DomainError("invalid_transition", "Only a draft can be started")
    config = BookingConfiguration.model_validate(booking.configuration)
    try:
        config.validate_start()
    except ValueError as exc:
        raise DomainError("incomplete_booking", str(exc), 422) from None
    if not queue(session, booking_id):
        raise DomainError("empty_queue", "Select at least one restaurant", 422)
    if session.get(SimulationScenario, scenario_id) is None:
        raise DomainError("not_found", "Simulation scenario not found", 404)
    if mode != "simulation":
        from app.ai.starting import prepare_execution

        prepare_execution(session, booking, mode, authorization, settings)
    elif authorization is not None:
        raise DomainError(
            "invalid_authorization", "Call authorization is only accepted for real telephony", 422
        )
    booking.status, booking.scenario_id, booking.started_at = "RUNNING", scenario_id, now()
    workspace = session.get(WorkspaceState, 1)
    if workspace and workspace.active_draft_id == booking_id:
        workspace.active_draft_id = None
        workspace.version += 1
    emit(session, booking, "booking.started")
    return summary(session, booking)


def cancel(session: Session, booking_id: str, expected: int) -> BookingSummary:
    booking = require_booking(session, booking_id)
    if booking.status == "CANCELLED":
        return summary(session, booking)
    check_version(booking, expected)
    if booking.status not in {"DRAFT", "READY", "RUNNING", "WAITING_FOR_USER"}:
        raise DomainError("invalid_transition", "Booking cannot be cancelled in its current state")
    booking.status, booking.finished_at = "CANCELLED", now()
    for attempt in attempts(session, booking_id):
        if attempt.status == "RUNNING":
            finish_attempt(attempt, "CANCELLED", "CANCELLED")
    for offer in session.scalars(select(ReservationOffer).where(ReservationOffer.booking_id == booking_id)):
        offer.approval_pending = False
    from app.ai.models import AIExecution, VoiceCallSession

    execution_id = session.scalar(select(AIExecution.id).where(AIExecution.booking_id == booking_id))
    if execution_id:
        for call in session.scalars(
            select(VoiceCallSession).where(VoiceCallSession.execution_id == execution_id)
        ):
            call.action = "STOP"
    workspace = session.get(WorkspaceState, 1)
    if workspace and workspace.active_draft_id == booking_id:
        workspace.active_draft_id = None
        workspace.version += 1
    emit(session, booking, "booking.cancelled")
    return summary(session, booking)


def decide(session: Session, booking_id: str, expected: int, offer_id: str, approve: bool) -> BookingSummary:
    booking = require_booking(session, booking_id)
    check_version(booking, expected)
    offer = session.get(ReservationOffer, offer_id)
    if offer is None or offer.booking_id != booking_id:
        raise DomainError("not_found", "Offer not found", 404)
    if booking.status != "WAITING_FOR_USER" or not offer.approval_pending:
        raise DomainError("invalid_decision", "Offer is not awaiting approval")
    if approve:
        from datetime import UTC

        from app.ai.models import AIExecution, VoiceCallSession

        ai_execution = session.scalar(select(AIExecution).where(AIExecution.booking_id == booking_id))
        if ai_execution and ai_execution.mode == "real_telephony":
            call = session.scalar(
                select(VoiceCallSession).where(VoiceCallSession.attempt_id == offer.attempt_id)
            )
            if (
                call is None
                or call.transport_state != "ACTIVE"
                or (
                    call.approval_deadline
                    and datetime.fromisoformat(call.approval_deadline) <= datetime.now(UTC)
                )
            ):
                raise DomainError("approval_expired", "The phone session is no longer awaiting a decision")
    offer.decision, offer.approval_pending = "APPROVED" if approve else "REJECTED", False
    booking.status = "RUNNING"
    attempt = session.get(CallAttempt, offer.attempt_id)
    if approve:
        attempt.status, attempt.result = "RUNNING", "OFFER_ACCEPTABLE"
        attempt.completed_at, attempt.duration_ms = None, None
    else:
        finish_attempt(attempt, "DECLINED")
    emit(session, booking, "user.decision_received")
    return summary(session, booking)


class BookingExecutionService:
    """Single local supervisor. Durable work is claimed through persisted RUNNING state.

    A process lock in the app lifespan enforces one executor per SQLite file. No network
    await runs inside a database transaction. Provider results are checked against
    persisted state after every await, so cancellation wins over late simulated results.
    """

    def __init__(self, db: Database, provider: CallProvider, timeout: float):
        self.db, self.provider, self.timeout = db, provider, timeout
        self.policy = NegotiationPolicyService()
        self.tasks: dict[str, asyncio.Task] = {}
        self.ai = None

    def recover(self) -> None:
        with self.db.transaction(write=True) as session:
            for booking in session.scalars(select(BookingRequest).where(BookingRequest.status == "RUNNING")):
                from app.ai.models import AIExecution, VoiceCallSession

                execution = session.scalar(select(AIExecution).where(AIExecution.booking_id == booking.id))
                if (
                    execution
                    and execution.paused
                    and not any(a.status == "RUNNING" for a in attempts(session, booking.id))
                ):
                    external = session.scalar(
                        select(VoiceCallSession.id).where(
                            VoiceCallSession.execution_id == execution.id,
                            VoiceCallSession.transport_state.in_(["ACTIVE", "DIALING", "UNCERTAIN"]),
                        )
                    )
                    if not external:
                        continue  # Persisted pause at a completed attempt boundary is safe to resume.
                self._fail(session, booking, "INTERRUPTED")

    @staticmethod
    def _fail(session: Session, booking: BookingRequest, result: str) -> None:
        for attempt in attempts(session, booking.id):
            if attempt.status == "RUNNING":
                finish_attempt(attempt, result, "FAILED")
        booking.status, booking.finished_at = "FAILED", now()
        from app.ai.models import AIExecution, VoiceCallSession

        execution = session.scalar(select(AIExecution).where(AIExecution.booking_id == booking.id))
        if execution:
            execution.error_code = result
            for call in session.scalars(
                select(VoiceCallSession).where(VoiceCallSession.execution_id == execution.id)
            ):
                if call.transport_state in {"ACTIVE", "DIALING", "UNCERTAIN"}:
                    call.action = "STOP"
        emit(session, booking, "booking.failed")

    async def _supervisor_io(self, operation):
        task = asyncio.create_task(asyncio.to_thread(operation))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            # Finish the transaction before lifespan releases the executor lock.
            await asyncio.gather(task, return_exceptions=True)
            raise

    def _scheduled_bookings(self):
        with self.db.transaction() as session:
            running = list(
                session.scalars(select(BookingRequest.id).where(BookingRequest.status == "RUNNING"))
            )
        if self.ai:
            running = [bid for bid in running if self.ai.schedulable(bid)]
            running += self.ai.terminal_without_summary()
        return running

    async def supervise(self) -> None:
        try:
            while True:
                if self.ai:
                    await self._supervisor_io(self.ai.maintenance)
                for booking_id, task in list(self.tasks.items()):
                    if task.done():
                        # run() records failures before returning.
                        task.result()
                        del self.tasks[booking_id]
                running = await self._supervisor_io(self._scheduled_bookings)
                for booking_id in running:
                    if booking_id not in self.tasks:
                        self.tasks[booking_id] = asyncio.create_task(self.run(booking_id))
                await asyncio.sleep(0.03)
        finally:
            for task in self.tasks.values():
                task.cancel()
            await asyncio.gather(*self.tasks.values(), return_exceptions=True)

    async def run(self, booking_id: str) -> None:
        try:
            if self.ai and self.ai.has_execution(booking_id):
                await self.ai.drive(booking_id)
            else:
                await self._run(booking_id)
        except asyncio.CancelledError:
            raise
        except UncertainCallError:
            with self.db.transaction(write=True) as session:
                booking = require_booking(session, booking_id)
                if booking.status == "RUNNING":
                    self._fail(session, booking, "UNCERTAIN")
        except Exception as exc:  # noqa: BLE001 -- supervisor must persist unexpected provider failures
            # Never log configuration, phone, dietary data or provider response contents.
            logger.error(
                "execution_failure", extra={"booking_id": booking_id, "error_type": type(exc).__name__}
            )
            with self.db.transaction(write=True) as session:
                booking = require_booking(session, booking_id)
                if booking.status == "RUNNING":
                    self._fail(session, booking, "ERROR")

    def provider_for(self, booking_id: str):
        return (
            self.ai.provider_for(booking_id)
            if self.ai and self.ai.has_execution(booking_id)
            else self.provider
        )

    def timeout_for(self, booking_id: str):
        return (
            self.ai.timeout_for(booking_id) if self.ai and self.ai.has_execution(booking_id) else self.timeout
        )

    async def step(self, booking_id: str) -> None:
        await self._run(booking_id, single_step=True)

    async def _run(self, booking_id: str, *, single_step: bool = False) -> None:
        iterations = 0
        while True:
            if single_step and iterations:
                return
            iterations += 1
            provider = self.provider_for(booking_id)
            if hasattr(provider, "before_advance"):
                await provider.before_advance(booking_id)
            offer_id = None
            with self.db.transaction(write=True) as session:
                booking = require_booking(session, booking_id)
                if booking.status != "RUNNING":
                    return
                config = BookingConfiguration.model_validate(booking.configuration)
                calls = attempts(session, booking_id)
                active = next((call for call in calls if call.status == "RUNNING"), None)
                if active:
                    offer = session.scalar(
                        select(ReservationOffer).where(
                            ReservationOffer.attempt_id == active.id,
                            ReservationOffer.decision == "APPROVED",
                        )
                    )
                    if offer is None:
                        raise RuntimeError("An active attempt must have a persisted approved offer to resume")
                    offer_id = offer.id
                    attempt_id, restaurant_id = active.id, active.restaurant_id
                else:
                    contacted = {call.restaurant_id for call in calls}
                    next_row = next(
                        (row for row in queue(session, booking_id) if row.restaurant_id not in contacted),
                        None,
                    )
                    if next_row is None:
                        booking.status, booking.finished_at = "EXHAUSTED", now()
                        emit(session, booking, "booking.exhausted")
                        return
                    active = CallAttempt(
                        booking_id=booking_id,
                        restaurant_id=next_row.restaurant_id,
                        sequence=len(calls),
                        status="RUNNING",
                    )
                    session.add(active)
                    session.flush()
                    attempt_id, restaurant_id = active.id, active.restaurant_id
                    scenario = session.get(SimulationScenario, booking.scenario_id)
                    outcome = scenario.outcomes[min(active.sequence, len(scenario.outcomes) - 1)]
                    emit(session, booking, "call.started")
            if offer_id:
                await self._confirm(booking_id, attempt_id, offer_id)
                continue
            try:
                response = await asyncio.wait_for(
                    self.provider_for(booking_id).contact(
                        config,
                        restaurant_id,
                        outcome,
                        attempt_id,
                    ),
                    timeout=self.timeout_for(booking_id),
                )
            except UncertainCallError:
                with self.db.transaction(write=True) as session:
                    booking = require_booking(session, booking_id)
                    if booking.status == "RUNNING":
                        self._fail(session, booking, "UNCERTAIN")
                return
            except TimeoutError:
                with self.db.transaction(write=True) as session:
                    booking = require_booking(session, booking_id)
                    if booking.status != "RUNNING":
                        return
                    if getattr(provider, "external_effects", False):
                        self._fail(session, booking, "UNCERTAIN")
                        return
                    finish_attempt(session.get(CallAttempt, attempt_id), "TIMEOUT", "FAILED")
                    emit(session, booking, "call.completed")
                continue
            with self.db.transaction(write=True) as session:
                booking = require_booking(session, booking_id)
                if booking.status != "RUNNING":
                    return
                attempt = session.get(CallAttempt, attempt_id)
                if response.result != "OFFER":
                    finish_attempt(
                        attempt, response.result, "FAILED" if response.result == "ERROR" else "COMPLETED"
                    )
                    emit(session, booking, "call.completed")
                    continue
                if response.offer is None:
                    raise RuntimeError("Provider returned an offer without details")
                evaluation = self.policy.evaluate(config, response.offer)
                offer = ReservationOffer(
                    booking_id=booking_id,
                    attempt_id=attempt_id,
                    details=response.offer.model_dump(mode="json"),
                    evaluation=evaluation,
                    approval_pending=evaluation == "REQUIRES_USER_APPROVAL",
                    provider_confirmation_expected=response.confirms_on_accept,
                )
                session.add(offer)
                session.flush()
                offer_id = offer.id
                emit(session, booking, "alternative.proposed")
                if evaluation != "ACCEPTABLE":
                    result = {
                        "UNACCEPTABLE": "INCOMPATIBLE_OFFER",
                        "REQUIRES_USER_APPROVAL": "USER_APPROVAL_REQUIRED",
                        "INSUFFICIENT_INFORMATION": "INSUFFICIENT_INFORMATION",
                    }[evaluation]
                    finish_attempt(attempt, result)
                    if evaluation == "REQUIRES_USER_APPROVAL":
                        booking.status = "WAITING_FOR_USER"
                    emit(session, booking, "call.completed")
                    if evaluation == "REQUIRES_USER_APPROVAL":
                        emit(session, booking, "user.approval_required")
                        return
                    continue
                attempt.result = "OFFER_ACCEPTABLE"
            await self._confirm(booking_id, attempt_id, offer_id)

    async def _confirm(self, booking_id: str, attempt_id: str, offer_id: str) -> None:
        with self.db.transaction() as session:
            booking = require_booking(session, booking_id)
            if booking.status != "RUNNING":
                return
            offer = session.get(ReservationOffer, offer_id)
            details = OfferDetails.model_validate(offer.details)
            expected = offer.provider_confirmation_expected
        try:
            evidence = await asyncio.wait_for(
                self.provider_for(booking_id).confirm(
                    details,
                    operation_id=attempt_id,
                    confirms_on_accept=expected,
                ),
                timeout=self.timeout_for(booking_id),
            )
        except UncertainCallError:
            with self.db.transaction(write=True) as session:
                booking = require_booking(session, booking_id)
                if booking.status == "RUNNING":
                    self._fail(session, booking, "UNCERTAIN")
            return
        except TimeoutError:
            # Confirmation might have happened: stop rather than contact another restaurant.
            with self.db.transaction(write=True) as session:
                booking = require_booking(session, booking_id)
                if booking.status == "RUNNING":
                    self._fail(
                        session,
                        booking,
                        "UNCERTAIN"
                        if getattr(self.provider_for(booking_id), "external_effects", False)
                        else "TIMEOUT",
                    )
            return
        with self.db.transaction(write=True) as session:
            booking = require_booking(session, booking_id)
            if booking.status != "RUNNING":
                return
            attempt = session.get(CallAttempt, attempt_id)
            offer = session.get(ReservationOffer, offer_id)
            if evidence.reservation is not None:
                if not evidence.simulated and evidence.reservation.evidence_kind != "provider_transcript":
                    self._fail(session, booking, "UNCERTAIN")
                    return
                from app.services.verification import ReservationVerificationService

                config = BookingConfiguration.model_validate(booking.configuration)
                verified = ReservationVerificationService().verify(
                    config,
                    attempt.restaurant_id,
                    attempt_id,
                    details,
                    evidence.reservation,
                    deposit_approved=offer.decision == "APPROVED",
                )
                if verified.status != "CONFIRMED":
                    self._fail(session, booking, "AMBIGUOUS")
                    return
            elif not evidence.simulated:
                self._fail(session, booking, "UNCERTAIN")
                return
            if not evidence.confirmed:
                finish_attempt(attempt, "NOT_CONFIRMED")
                emit(session, booking, "call.completed")
                return
            if not evidence.reference and evidence.reservation is None:
                self._fail(session, booking, "ERROR")
                return
            # The policy and explicit restaurant acknowledgment are both required.
            config = BookingConfiguration.model_validate(booking.configuration)
            evaluation = self.policy.evaluate(config, details)
            offer = session.get(ReservationOffer, offer_id)
            if evaluation != "ACCEPTABLE" and not (
                evaluation == "REQUIRES_USER_APPROVAL" and offer.decision == "APPROVED"
            ):
                self._fail(session, booking, "ERROR")
                return
            session.add(
                ReservationConfirmation(
                    booking_id=booking_id,
                    restaurant_id=attempt.restaurant_id,
                    attempt_id=attempt_id,
                    reference=evidence.reference,
                    details=details.model_dump(mode="json"),
                    simulated=evidence.simulated,
                )
            )
            finish_attempt(attempt, "CONFIRMED")
            booking.status, booking.finished_at = "CONFIRMED", now()
            emit(session, booking, "call.completed")
            emit(session, booking, "booking.confirmed")
