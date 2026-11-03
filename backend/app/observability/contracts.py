from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas import Contract

Identifier = Annotated[str, Field(max_length=250, pattern=r"^[A-Za-z0-9_:/.-]+$")]
Code = Annotated[str, Field(max_length=100, pattern=r"^[A-Za-z_][A-Za-z0-9_.-]*$")]


class ModelUsage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    duration_seconds: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    input_audio_tokens: int | None = Field(default=None, ge=0)
    output_audio_tokens: int | None = Field(default=None, ge=0)
    cached_tokens: int | None = Field(default=None, ge=0)


class SafeIO(BaseModel):
    """Explicit projections only. Never arbitrary LLM/tool JSON."""

    model_config = ConfigDict(extra="ignore")
    redacted: Literal[True] = True
    supplied: bool | None = None
    count: int | None = Field(default=None, ge=0)
    status: (
        Literal[
            "DRAFT",
            "READY",
            "RUNNING",
            "WAITING_FOR_USER",
            "CONFIRMED",
            "EXHAUSTED",
            "CANCELLED",
            "FAILED",
            "PENDING",
            "REJECTED",
            "AMBIGUOUS",
            "NEEDS_USER_ACTION",
        ]
        | None
    ) = None
    evaluation: (
        Literal["ACCEPTABLE", "UNACCEPTABLE", "REQUIRES_USER_APPROVAL", "INSUFFICIENT_INFORMATION"] | None
    ) = None
    confirmation_id: Identifier | None = None
    attempt_id: Identifier | None = None
    restaurant_id: Identifier | None = None
    version: int | None = Field(default=None, ge=0)
    completed_attempts: int | None = Field(default=None, ge=0)
    passed: bool | None = None
    confirmed: bool | None = None


class EventData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    input: SafeIO | None = None
    output: SafeIO | None = None
    from_node: Code | None = None
    to_node: Code | None = None
    conditional: bool | None = None
    error_type: Code | None = None
    error_code: Code | None = None
    business_event_id: int | None = Field(default=None, ge=1)
    booking_version: int | None = Field(default=None, ge=1)
    status: SafeIO.model_fields["status"].annotation = None
    result: (
        Literal[
            "NO_AVAILABILITY",
            "OFFER",
            "OFFER_ACCEPTABLE",
            "CONFIRMED",
            "NOT_CONFIRMED",
            "ERROR",
            "TIMEOUT",
            "FAILED",
            "CANCELLED",
            "UNCERTAIN",
            "DECLINED",
            "DECLINED_AI",
            "AMBIGUOUS",
            "DISCONNECTED",
            "INCOMPATIBLE_OFFER",
            "USER_APPROVAL_REQUIRED",
            "INSUFFICIENT_INFORMATION",
        ]
        | None
    ) = None
    confirmation_id: Identifier | None = None
    offer_id: Identifier | None = None
    decision: Literal["APPROVED", "REJECTED"] | None = None
    role: Literal["assistant", "restaurant"] | None = None
    provisional: bool | None = None
    provider_event_type: Code | None = None
    provider_start_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    provider_end_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    provider_sequence: int | None = Field(default=None, ge=0)
    revision: int | None = Field(default=None, ge=0)
    turn_id: Identifier | None = None
    provider_stream_id: Identifier | None = None
    suppressed_events: int | None = Field(default=None, ge=0)
    transport_status: (
        Literal[
            "queued",
            "initiated",
            "ringing",
            "in-progress",
            "completed",
            "canceled",
            "failed",
            "busy",
            "no-answer",
        ]
        | None
    ) = None
    transport_state: Literal["PREPARED", "DIALING", "ACTIVE", "ENDED", "UNCERTAIN", "SIMULATED"] | None = None
    backend_action: (
        Literal[
            "CONSULT",
            "ACCEPT",
            "STOP",
            "RECONCILE",
            "RECONCILED_NO_RESERVATION",
            "NO_AVAILABILITY",
            "DECLINED_AI",
            "AMBIGUOUS",
        ]
        | None
    ) = None
    operator_attested_no_reservation: bool | None = None
    characters: int | None = Field(default=None, ge=0)
    simulated: bool | None = None
    cached: bool | None = None
    checkpoint_available: bool | None = None
    pending_nodes: int | None = Field(default=None, ge=0)
    usage: ModelUsage | None = None
    reserved_cost_eur: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    recording_retained: Literal[False] = False
    transcript_retained: Literal[False] = False


class ObservationEventOut(Contract):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: int
    event_id: str
    schema_version: Literal[1]
    execution_id: str
    booking_id: str
    call_attempt_id: str | None
    call_session_id: str | None
    graph_thread_id: str | None
    graph_version: str | None
    checkpoint_id: str | None
    span_id: str | None
    parent_span_id: str | None
    agent_run_id: str | None
    tool_call_id: str | None
    delegation_id: str | None
    external_call_id: str | None
    external_session_id: str | None
    kind: str
    phase: str
    agent: str | None
    node: str | None
    tool: str | None
    model: str | None
    reported_model: str | None
    prompt_version: str | None
    prompt_sha256: str | None
    occurred_at: datetime
    received_at: datetime
    elapsed_ms: int | None
    execution_offset_ms: int | None
    call_offset_ms: int | None
    data: EventData


class ObservationPage(Contract):
    items: list[ObservationEventOut]
    next_after_event_id: int
    has_more: bool
    high_watermark: int


class ObservedExecutionOut(Contract):
    id: str
    booking_id: str
    ai_execution_id: str | None
    mode: Literal["simulation", "ai_simulation", "real_telephony", "voice_sandbox"]
    graph_version: str | None
    graph_thread_id: str | None
    prompt_versions: dict
    configured_models: dict
    started_at: datetime
    instrumentation_started_at: datetime
    ended_at: datetime | None
    events_pruned_at: datetime | None
    dropped_events: int
    booking_status: str
    event_count: int
    open_span_ids: list[str]
    coverage: Literal["recorded", "pruned", "empty", "degraded"]
    content_policy: Literal["metadata_only"] = "metadata_only"


class ObservedExecutionPage(Contract):
    items: list[ObservedExecutionOut]
    total: int
    limit: int
    offset: int


class GraphVersionOut(Contract):
    id: str
    name: str
    definition: dict
    created_at: datetime
