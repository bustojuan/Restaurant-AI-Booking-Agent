from datetime import datetime
from typing import Literal, TypedDict

from pydantic import Field

from app.schemas import CallAuthorization, Contract, OfferDetails

AgentName = Literal[
    "supervisor", "planning", "research", "voice", "negotiation", "verification", "memory", "evaluation"
]
Evaluation = Literal["ACCEPTABLE", "UNACCEPTABLE", "REQUIRES_USER_APPROVAL", "INSUFFICIENT_INFORMATION"]


class BookingPlan(Contract):
    objective: str
    mandatory_conditions: list[str]
    negotiable_conditions: list[str]
    questions: list[str]
    approval_conditions: list[str]
    success_criteria: list[str]
    voice_briefing: str
    uncertainties: list[str] = Field(default_factory=list)


class ResearchObservation(Contract):
    category: Literal["FACT", "HISTORICAL", "UNKNOWN"]
    key: str
    value: str | None
    observed_at: str | None = None


class ResearchResult(Contract):
    restaurant_id: str
    observations: list[ResearchObservation]


class NegotiationDecision(Contract):
    evaluation: Evaluation
    spoken_response: str


class ReservationEvidence(Contract):
    restaurant_id: str | None = None
    booking_name: str | None = None
    details: OfferDetails | None = None
    explicit_confirmation: bool = False
    pending_user_action: bool = False
    contradictory: bool = False
    reference: str | None = None
    evidence_kind: Literal["simulated", "provider_transcript"]
    # Source belongs to this attempt, not an ID chosen by a model.
    source_attempt_id: str
    confirmation_quote: str | None = Field(default=None, max_length=500)


class VerificationResult(Contract):
    status: Literal["CONFIRMED", "REJECTED", "PENDING", "AMBIGUOUS", "NEEDS_USER_ACTION"]
    reasons: list[str]


class ExtractedConversation(Contract):
    intent: Literal["requirements", "proposal", "confirmation", "no_availability", "refuses_ai", "unclear"]
    offer: OfferDetails | None = None
    evidence: ReservationEvidence | None = None
    # True when the latest correction supersedes earlier information.
    supersedes_prior_proposal: bool = False
    requirement_quotes: dict[str, str] = Field(default_factory=dict)
    financial_terms_quote: str | None = Field(default=None, max_length=500)


class QualityReport(Contract):
    checks: dict[str, bool]
    passed: bool
    completed_attempts: int
    confirmed: bool
    scope: Literal["offline_simulation", "runtime_records", "audio_protocol"] = "runtime_records"


class AIStartOptions(Contract):
    mode: Literal["simulation", "ai_simulation", "real_telephony"] = "simulation"
    call_authorization: CallAuthorization | None = None


class ExecutionView(Contract):
    id: str
    booking_id: str
    mode: Literal["ai_simulation", "real_telephony"]
    paused: bool
    active_agent: AgentName | None
    prompt_versions: dict[str, str]
    summary_text: str | None
    quality_report: QualityReport | None
    error_code: str | None
    created_at: str


class TraceView(Contract):
    id: int
    execution_id: str
    agent: AgentName
    tool: str | None
    phase: Literal["started", "completed", "failed"]
    elapsed_ms: int | None
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    estimated_cost_eur: float | None
    details: dict[str, str | int | bool | None]
    created_at: str


class MemoryInput(Contract):
    key: Literal[
        "table_type", "flexibility_minutes", "area", "dietary_requirements", "accessibility_required"
    ]
    value: str | bool | int | list[dict]
    authorized_by_user: Literal[True]
    expires_at: datetime


class MemoryView(Contract):
    id: str
    scope: Literal["booking", "restaurant", "preference"]
    owner_id: str
    key: str
    value: dict
    provenance: Literal["HISTORICAL", "USER_AUTHORIZED"]
    expires_at: str
    created_at: str


class GraphState(TypedDict, total=False):
    booking_id: str
    execution_id: str
    active_restaurant_id: str | None
    active_call_attempt_id: str | None
    booking_plan: dict
    call_context: dict
    extracted_proposals: list[str]
    negotiation_decision: dict | None
    verification_result: dict | None
    pending_user_approval: str | None
    route: str
    error_state: str | None
    steps: int
