from datetime import date, datetime
from datetime import time as TimeValue
from typing import Literal

from pydantic import Field

from app.schemas import Contract


class AttemptTerms(Contract):
    requested_date: date | None = None
    time: TimeValue | None = None
    party_size: int | None = None
    table_type: str | None = None
    flexibility_minutes: int | None = None
    deposit: float | None = None


class AttemptEvidence(Contract):
    kind: Literal["request", "offer", "evaluation", "confirmation", "event", "call"]
    id: str
    label: str
    event_cursor: int | None = None


class AttemptFact(Contract):
    code: str
    message: str
    evidence: list[AttemptEvidence]


class AttemptOffer(Contract):
    id: str
    terms: AttemptTerms
    evaluation: str
    approval_pending: bool
    decision: str | None


class AttemptReview(Contract):
    category: Literal["none", "continue", "review_required", "unknown", "reconciled"]
    title: str
    message: str
    steps: list[str] = Field(default_factory=list)
    automatic_continuation: bool | None = None
    reconciliation_available: bool = False


class AttemptExplanation(Contract):
    # Explicitly selected projections: no contacts, dietary values or provider free text.
    requested: AttemptTerms | None
    offers: list[AttemptOffer]
    facts: list[AttemptFact]
    review: AttemptReview
    booking_status: str
    booking_version: int
    simulated: bool | None


class CallOut(Contract):
    id: str
    booking_id: str
    restaurant_id: str
    restaurant_name: str
    sequence: int
    started_at: datetime
    completed_at: datetime | None
    duration_ms: int | None
    status: str
    result: str | None
    mode: str
    execution_id: str | None
    call_session_id: str | None
    transport_state: str | None
    cost_eur: float | None = None
    coverage: str
    models: list[str]
    prompt_versions: list[str]
    confirmation_id: str | None
    execution_summary: str | None = None
    explanation: AttemptExplanation | None = None


class CallPage(Contract):
    items: list[CallOut]
    total: int
    limit: int
    offset: int


class BookingHistoryOut(Contract):
    id: str
    status: str
    mode: str
    started_at: datetime
    finished_at: datetime | None
    calls: list[CallOut]
    confirmation_id: str | None


class BookingHistoryPage(Contract):
    items: list[BookingHistoryOut]
    total: int
    limit: int
    offset: int


class CountMetric(Contract):
    name: str
    count: int


class AgentMetric(Contract):
    name: str
    invocations: int
    completed: int
    errors: int
    average_ms: float | None


class DayMetric(Contract):
    date: date
    calls: int
    confirmations: int
    average_ms: float | None


class AnalyticsOut(Contract):
    calls: int
    bookings: int
    confirmed_bookings: int
    confirmation_rate: float | None
    average_duration_ms: float | None
    attempts_per_booking: float | None
    known_cost_eur: float | None = None
    cost_coverage: int = 0
    errors: int
    human_interventions: int
    instrumented_executions: int
    days: list[DayMetric]
    results: list[CountMetric]
    agents: list[AgentMetric]
    tools: list[CountMetric]
    models: list[str]
    prompt_versions: list[str]
    input_tokens: int | None
    output_tokens: int | None
    model_latency_ms: float | None


class AdminSettingsOut(Contract):
    backend_status: Literal["online"] = "online"
    administrative_api: Literal["authenticated"] = "authenticated"
    reasoning_model: str
    voice_model: str
    extraction_mode: str
    voice_provider: str
    telephone_provider: str
    voice_enabled: bool
    telephony_enabled: bool
    retention_days: int
    content_policy: Literal["metadata_only"] = "metadata_only"
    recording_enabled: Literal[False] = False
    transcript_enabled: Literal[False] = False
    instrumentation: Literal["enabled"] = "enabled"
    prompts: dict[str, dict[str, str]]
    playground_available: bool
    read_only: Literal[True] = True


class AdminScenarioOut(Contract):
    id: str
    name: str
    available: bool
    mode: Literal["ai_simulation"] = "ai_simulation"


class PlaygroundInput(Contract):
    scenario_id: str = Field(min_length=1, max_length=100)
    adults: int = Field(default=4, ge=1, le=20)
    flexibility_minutes: int = Field(default=30, ge=0, le=120)


class PlaygroundOut(Contract):
    booking_id: str
    scenario_id: str
    mode: Literal["ai_simulation"] = "ai_simulation"
    status: str


class EvaluationOut(Contract):
    booking_id: str
    scenario_id: str | None
    status: str
    passed: bool | None
    confirmed: bool | None
    checks: dict[str, bool]
    agent_count: int
    tools: list[str]
    duration_ms: int | None
