from datetime import datetime

from app.schemas import BookingConfiguration, OfferDetails


class NegotiationPolicyService:
    def evaluate(self, config: BookingConfiguration, offer: OfferDetails) -> str:
        if offer.requested_date != config.requested_date or offer.party_size != config.party_size:
            return "UNACCEPTABLE"
        difference = (
            abs(
                (
                    datetime.combine(offer.requested_date, offer.time)
                    - datetime.combine(config.requested_date, config.preferred_time)
                ).total_seconds()
            )
            / 60
        )
        if difference > config.flexibility_minutes:
            return "UNACCEPTABLE"
        if config.table_type_mandatory and offer.table_type != config.table_type:
            return "UNACCEPTABLE"
        mandatory = config.mandatory_keys()
        if any(offer.verified_requirements.get(key) is False for key in mandatory):
            return "UNACCEPTABLE"
        if any(key not in offer.verified_requirements for key in mandatory):
            return "INSUFFICIENT_INFORMATION"
        if config.strict_budget:
            if offer.price_per_person is None or config.budget_per_person is None:
                return "INSUFFICIENT_INFORMATION"
            if offer.price_per_person > config.budget_per_person:
                return "UNACCEPTABLE"
        if offer.deposit > 0 or offer.financial_conditions:
            return "REQUIRES_USER_APPROVAL"
        return "ACCEPTABLE"
