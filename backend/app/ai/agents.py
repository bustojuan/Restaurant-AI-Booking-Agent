from datetime import datetime, timedelta

from sqlalchemy import select

from app.ai.contracts import (
    BookingPlan,
    NegotiationDecision,
    QualityReport,
    ResearchObservation,
    ResearchResult,
    ReservationEvidence,
    VerificationResult,
)
from app.ai.models import AgentMemory, AIExecution, VoiceCallSession
from app.db.session import Database
from app.models import BookingEvent, ReservationOffer, now
from app.repositories import attempts, queue, require_booking, require_restaurant
from app.schemas import BookingConfiguration, OfferDetails
from app.services.bookings import summary
from app.services.negotiation import NegotiationPolicyService
from app.services.verification import ReservationVerificationService


class PlanningAgent:
    def plan(self, config: BookingConfiguration) -> BookingPlan:
        mandatory = [
            "requested_date",
            "party_size",
            "authorized_time_window",
            *sorted(config.mandatory_keys()),
        ]
        if config.table_type_mandatory:
            mandatory.append("table_type")
        if config.strict_budget:
            mandatory.append("budget_per_person")
        preferences = [r.key for r in config.requirements if not r.mandatory]
        preferences += [f"dietary:{r.code}" for r in config.dietary_requirements if not r.mandatory]
        if config.table_type != "indifferent" and not config.table_type_mandatory:
            preferences.append(f"table_type:{config.table_type}")
        questions = [*sorted(config.mandatory_keys()), "reservation_conditions", "explicit_confirmation"]
        return BookingPlan(
            objective="Obtener una reserva que cumpla la solicitud siguiendo la prioridad indicada.",
            mandatory_conditions=mandatory,
            negotiable_conditions=preferences,
            questions=questions,
            approval_conditions=["deposit_or_financial_obligation"],
            success_criteria=[
                "matching_restaurant",
                "matching_booking_name",
                "verified_mandatory_requirements",
                "explicit_restaurant_confirmation",
                "no_pending_user_action",
            ],
            voice_briefing=(
                f"Solicita mesa para {config.party_size} personas el {config.requested_date} "
                f"a las {config.preferred_time}, con flexibilidad de {config.flexibility_minutes} minutos. "
                f"Preferencia de mesa: {config.table_type}. "
                "Pregunta y verifica los requisitos obligatorios antes de comprometer la reserva."
            ),
            uncertainties=["missing_schedule"]
            if not config.requested_date or not config.preferred_time
            else [],
        )


class ResearchAgent:
    def __init__(self, db: Database):
        self.db = db

    def research(self, restaurant_id: str) -> ResearchResult:
        with self.db.transaction() as session:
            restaurant = require_restaurant(session, restaurant_id)
            observations = [
                ResearchObservation(
                    category="FACT" if value is not None else "UNKNOWN",
                    key=key,
                    value=value,
                    observed_at=restaurant.updated_at,
                )
                for key, value in {
                    "name": restaurant.name,
                    "municipality": restaurant.municipality,
                    "address": restaurant.address,
                    "phone": restaurant.phone,
                }.items()
            ]
            observations.append(
                ResearchObservation(category="UNKNOWN", key="current_availability", value=None)
            )
            for memory in session.scalars(
                select(AgentMemory).where(
                    AgentMemory.scope == "restaurant",
                    AgentMemory.owner_id == restaurant_id,
                    AgentMemory.expires_at > now(),
                )
            ):
                observations.append(
                    ResearchObservation(
                        category="HISTORICAL",
                        key=memory.key,
                        value=str(memory.value),
                        observed_at=memory.created_at,
                    )
                )
            return ResearchResult(restaurant_id=restaurant_id, observations=observations)


class NegotiationAgent:
    def evaluate(self, config: BookingConfiguration, offer: OfferDetails) -> NegotiationDecision:
        decision = NegotiationPolicyService().evaluate(config, offer)
        responses = {
            "ACCEPTABLE": "La propuesta cumple los límites. Debemos pedir confirmación explícita al restaurante.",
            "UNACCEPTABLE": "Esa propuesta no cumple las condiciones autorizadas. Pregunta por otra alternativa.",
            "REQUIRES_USER_APPROVAL": "Necesitamos autorización del usuario; no aceptes todavía esa condición.",
            "INSUFFICIENT_INFORMATION": "Faltan datos por confirmar. Pregunta por los requisitos pendientes.",
        }
        return NegotiationDecision(evaluation=decision, spoken_response=responses[decision])


class VerificationAgent:
    def verify(
        self,
        config: BookingConfiguration,
        restaurant_id: str,
        attempt_id: str,
        offer: OfferDetails,
        evidence: ReservationEvidence,
        *,
        approved: bool = False,
    ) -> VerificationResult:
        return ReservationVerificationService().verify(
            config, restaurant_id, attempt_id, offer, evidence, deposit_approved=approved
        )


class MemorySummaryAgent:
    def __init__(self, db: Database, retention_days: int):
        self.db, self.retention_days = db, retention_days

    def summarize(self, booking_id: str) -> str:
        with self.db.transaction(write=True) as session:
            booking = require_booking(session, booking_id)
            execution = session.scalar(select(AIExecution).where(AIExecution.booking_id == booking_id))
            # Persisted business events are the evidence, rather than generated prose or model memory.
            final_event = session.scalar(
                select(BookingEvent)
                .where(
                    BookingEvent.booking_id == booking_id,
                    BookingEvent.event_type.in_(
                        [
                            "booking.confirmed",
                            "booking.exhausted",
                            "booking.cancelled",
                            "booking.failed",
                        ]
                    ),
                )
                .order_by(BookingEvent.event_id.desc())
            )
            snapshot = (
                final_event.payload["summary"]
                if final_event
                else summary(session, booking).model_dump(mode="json")
            )
            results = snapshot["contacted_restaurants"]
            parts = [f"Se completaron {snapshot['completed_attempts']} intentos."]
            descriptions = {
                "NO_AVAILABILITY": "no tenía disponibilidad",
                "INCOMPATIBLE_OFFER": "ofreció una opción incompatible",
                "CONFIRMED": "confirmó la reserva",
                "NOT_CONFIRMED": "no confirmó la reserva",
                "DECLINED": "recibió una propuesta rechazada por el usuario",
            }
            for attempt in results:
                result = attempt["result"]
                if result:
                    parts.append(f"{attempt['restaurant_name']}: {descriptions.get(result, result)}.")
                    observed_at = attempt["completed_at"] or attempt["started_at"]
                    expires = (
                        datetime.fromisoformat(observed_at) + timedelta(days=self.retention_days)
                    ).isoformat()
                    memory = session.scalar(
                        select(AgentMemory).where(
                            AgentMemory.scope == "restaurant",
                            AgentMemory.owner_id == attempt["restaurant_id"],
                            AgentMemory.key == "last_contact_result",
                        )
                    )
                    if memory is not None and memory.created_at > observed_at:
                        continue
                    if memory is None:
                        memory = AgentMemory(
                            scope="restaurant",
                            owner_id=attempt["restaurant_id"],
                            key="last_contact_result",
                            provenance="HISTORICAL",
                            expires_at=expires,
                            value={},
                        )
                        session.add(memory)
                    memory.value = {
                        "result": result,
                        "booking_id": booking_id,
                        "simulated": not execution or execution.mode != "real_telephony",
                    }
                    memory.expires_at, memory.created_at = expires, observed_at
            return " ".join(parts)


class EvaluationAgent:
    """Independent objective checks. Does not evaluate its own hidden reasoning or fabricate audio metrics."""

    def evaluate(self, db: Database, booking_id: str) -> QualityReport:
        with db.transaction() as session:
            booking = require_booking(session, booking_id)
            snap = summary(session, booking)
            rows = queue(session, booking_id)
            calls = attempts(session, booking_id)
            checks = {
                "priority_respected": [c.restaurant_id for c in calls]
                == [r.restaurant_id for r in rows[: len(calls)]],
                "no_duplicate_calls": len({c.restaurant_id for c in calls}) == len(calls),
                "at_most_one_active_call": sum(c.status == "RUNNING" for c in calls) <= 1,
                "confirmation_persisted_iff_confirmed": (booking.status == "CONFIRMED")
                == (snap.confirmation is not None),
                "confirmation_is_last_attempt": not snap.confirmation
                or (
                    bool(calls)
                    and snap.confirmation.attempt_id == calls[-1].id
                    and calls[-1].result == "CONFIRMED"
                ),
                "no_post_confirmation_calls": not snap.confirmation
                or all(c.started_at <= snap.confirmation.confirmed_at for c in calls),
            }
            if snap.confirmation:
                config = BookingConfiguration.model_validate(booking.configuration)
                offer = session.scalar(
                    select(ReservationOffer).where(
                        ReservationOffer.attempt_id == snap.confirmation.attempt_id
                    )
                )
                approval = offer is not None and offer.decision == "APPROVED"
                evaluation = NegotiationPolicyService().evaluate(config, snap.confirmation.details)
                checks["confirmed_conditions_authorized"] = (
                    evaluation == "ACCEPTABLE" or evaluation == "REQUIRES_USER_APPROVAL" and approval
                )
                call = session.scalar(
                    select(VoiceCallSession).where(
                        VoiceCallSession.attempt_id == snap.confirmation.attempt_id
                    )
                )
                checks["explicit_evidence_verified"] = bool(
                    call
                    and call.evidence
                    and call.accepted_offer
                    and VerificationAgent()
                    .verify(
                        config,
                        snap.confirmation.restaurant_id,
                        snap.confirmation.attempt_id,
                        OfferDetails.model_validate(call.accepted_offer),
                        ReservationEvidence.model_validate(call.evidence),
                        approved=approval,
                    )
                    .status
                    == "CONFIRMED"
                )
            return QualityReport(
                checks=checks,
                passed=all(checks.values()),
                completed_attempts=snap.completed_attempts,
                confirmed=booking.status == "CONFIRMED",
            )
