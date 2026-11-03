import asyncio
from datetime import datetime, timedelta
from typing import Literal, Protocol

from app.ai.contracts import ReservationEvidence
from app.schemas import BookingConfiguration, Contract, OfferDetails


class CallOutcome(Contract):
    result: Literal["NO_AVAILABILITY", "OFFER", "ERROR", "DECLINED_AI", "DISCONNECTED", "AMBIGUOUS"]
    offer: OfferDetails | None = None
    confirms_on_accept: bool = False


class ConfirmationEvidence(Contract):
    confirmed: bool
    reference: str | None = None
    simulated: bool = True
    reservation: ReservationEvidence | None = None


class UncertainCallError(RuntimeError):
    """The transport cannot exclude an external commitment; do not place another call."""


class CallProvider(Protocol):
    async def contact(
        self, config: BookingConfiguration, restaurant_id: str, outcome: str, operation_id: str
    ) -> CallOutcome: ...

    async def confirm(
        self, offer: OfferDetails, *, operation_id: str, confirms_on_accept: bool
    ) -> ConfirmationEvidence: ...


class MockCallProvider:
    def __init__(self, delay: float):
        self.delay = delay

    async def contact(
        self, config: BookingConfiguration, restaurant_id: str, outcome: str, operation_id: str
    ) -> CallOutcome:
        await asyncio.sleep(self.delay)
        if outcome == "TIMEOUT":
            raise TimeoutError("Simulated timeout")
        if outcome in {"NO_AVAILABILITY", "ERROR"}:
            return CallOutcome(result=outcome)
        local = datetime.combine(config.requested_date, config.preferred_time)
        if outcome == "INCOMPATIBLE_TIME":
            local += timedelta(minutes=config.flexibility_minutes + 60)
        offer = OfferDetails(
            requested_date=local.date(),
            time=local.time(),
            party_size=config.party_size,
            table_type=config.table_type,
            price_per_person=config.budget_per_person,
            deposit=20 if outcome == "REQUIRES_APPROVAL" else 0,
            verified_requirements={}
            if outcome == "INSUFFICIENT_INFORMATION"
            else dict.fromkeys(config.mandatory_keys(), True),
        )
        return CallOutcome(result="OFFER", offer=offer, confirms_on_accept=outcome != "NO_CONFIRMATION")

    async def confirm(
        self, offer: OfferDetails, *, operation_id: str, confirms_on_accept: bool
    ) -> ConfirmationEvidence:
        await asyncio.sleep(self.delay)
        return ConfirmationEvidence(
            confirmed=confirms_on_accept, reference=f"SIM-{operation_id}" if confirms_on_accept else None
        )
