from app.ai.contracts import ReservationEvidence, VerificationResult
from app.schemas import BookingConfiguration, OfferDetails
from app.services.negotiation import NegotiationPolicyService


class ReservationVerificationService:
    """Business validation; extraction/agents cannot set booking state."""

    def verify(
        self,
        config: BookingConfiguration,
        restaurant_id: str,
        attempt_id: str,
        authorized_offer: OfferDetails,
        evidence: ReservationEvidence,
        *,
        deposit_approved: bool = False,
    ) -> VerificationResult:
        if evidence.source_attempt_id != attempt_id or evidence.restaurant_id != restaurant_id:
            return VerificationResult(status="REJECTED", reasons=["identity_mismatch"])
        if evidence.contradictory:
            return VerificationResult(status="AMBIGUOUS", reasons=["contradictory_evidence"])
        if evidence.pending_user_action:
            return VerificationResult(status="NEEDS_USER_ACTION", reasons=["further_action_required"])
        if not evidence.explicit_confirmation or evidence.details is None or not evidence.booking_name:
            return VerificationResult(status="PENDING", reasons=["explicit_confirmation_incomplete"])
        if evidence.booking_name.strip().casefold() != (config.customer_name or "").strip().casefold():
            return VerificationResult(status="REJECTED", reasons=["booking_name_mismatch"])
        offered = evidence.details
        if any(
            getattr(offered, key) != getattr(authorized_offer, key)
            for key in (
                "requested_date",
                "time",
                "party_size",
                "table_type",
                "deposit",
                "price_per_person",
                "financial_conditions",
            )
        ):
            return VerificationResult(status="REJECTED", reasons=["conditions_changed_after_acceptance"])
        evaluation = NegotiationPolicyService().evaluate(config, offered)
        if evaluation == "REQUIRES_USER_APPROVAL" and not deposit_approved:
            return VerificationResult(status="NEEDS_USER_ACTION", reasons=["deposit_not_authorized"])
        if evaluation not in {"ACCEPTABLE", "REQUIRES_USER_APPROVAL"}:
            return VerificationResult(status="REJECTED", reasons=[evaluation.lower()])
        return VerificationResult(status="CONFIRMED", reasons=["explicit_evidence_matches_authorized_offer"])
