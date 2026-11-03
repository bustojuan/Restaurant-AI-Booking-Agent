from sqlalchemy import JSON, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, new_id, now


class GraphVersion(Base):
    __tablename__ = "observation_graph_versions"
    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    definition: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(default=now)


class ObservedExecution(Base):
    __tablename__ = "observed_executions"
    id: Mapped[str] = mapped_column(primary_key=True)
    booking_id: Mapped[str] = mapped_column(ForeignKey("booking_requests.id", ondelete="CASCADE"), index=True)
    ai_execution_id: Mapped[str | None] = mapped_column(
        ForeignKey("ai_executions.id", ondelete="CASCADE"), unique=True
    )
    mode: Mapped[str]
    graph_version: Mapped[str | None] = mapped_column(ForeignKey("observation_graph_versions.id"))
    graph_thread_id: Mapped[str | None]
    prompt_versions: Mapped[dict] = mapped_column(JSON, default=dict)
    configured_models: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[str]
    instrumentation_started_at: Mapped[str] = mapped_column(default=now)
    ended_at: Mapped[str | None]
    events_pruned_at: Mapped[str | None]
    dropped_events: Mapped[int] = mapped_column(default=0)
    __table_args__ = (Index("ix_observed_mode_started", "mode", "started_at"),)


class ObservationEvent(Base):
    __tablename__ = "observation_events"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(default=new_id, unique=True)
    schema_version: Mapped[int] = mapped_column(default=1)
    execution_id: Mapped[str] = mapped_column(ForeignKey("observed_executions.id", ondelete="CASCADE"))
    booking_id: Mapped[str] = mapped_column(ForeignKey("booking_requests.id", ondelete="CASCADE"))
    call_attempt_id: Mapped[str | None]
    call_session_id: Mapped[str | None]
    graph_thread_id: Mapped[str | None]
    graph_version: Mapped[str | None] = mapped_column(ForeignKey("observation_graph_versions.id"))
    checkpoint_id: Mapped[str | None]
    span_id: Mapped[str | None]
    parent_span_id: Mapped[str | None]
    agent_run_id: Mapped[str | None]
    tool_call_id: Mapped[str | None]
    delegation_id: Mapped[str | None]
    external_call_id: Mapped[str | None]
    external_session_id: Mapped[str | None]
    kind: Mapped[str]
    phase: Mapped[str]
    agent: Mapped[str | None]
    node: Mapped[str | None]
    tool: Mapped[str | None]
    model: Mapped[str | None]
    reported_model: Mapped[str | None]
    prompt_version: Mapped[str | None]
    prompt_sha256: Mapped[str | None]
    occurred_at: Mapped[str] = mapped_column(default=now)
    received_at: Mapped[str] = mapped_column(default=now)
    elapsed_ms: Mapped[int | None]
    execution_offset_ms: Mapped[int | None]
    call_offset_ms: Mapped[int | None]
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (
        Index("ix_observation_execution_cursor", "execution_id", "id"),
        Index("ix_observation_attempt_cursor", "call_attempt_id", "id"),
        Index("ix_observation_span", "span_id", "phase"),
        {"sqlite_autoincrement": True},
    )
