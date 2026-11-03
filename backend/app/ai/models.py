from sqlalchemy import JSON, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, new_id, now


class AIExecution(Base):
    __tablename__ = "ai_executions"
    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)
    booking_id: Mapped[str] = mapped_column(
        ForeignKey("booking_requests.id", ondelete="CASCADE"), unique=True
    )
    mode: Mapped[str]
    paused: Mapped[bool] = mapped_column(default=False)
    active_agent: Mapped[str | None]
    prompts: Mapped[dict] = mapped_column(JSON)
    authorization: Mapped[dict | None] = mapped_column(JSON)
    summary_text: Mapped[str | None]
    quality_report: Mapped[dict | None] = mapped_column(JSON)
    error_code: Mapped[str | None]
    created_at: Mapped[str] = mapped_column(default=now)


class AgentTrace(Base):
    __tablename__ = "agent_traces"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    execution_id: Mapped[str] = mapped_column(ForeignKey("ai_executions.id", ondelete="CASCADE"), index=True)
    agent: Mapped[str]
    tool: Mapped[str | None]
    phase: Mapped[str]
    elapsed_ms: Mapped[int | None]
    model: Mapped[str | None]
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    estimated_cost_eur: Mapped[float | None]
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(default=now)


class AgentMemory(Base):
    __tablename__ = "agent_memories"
    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)
    scope: Mapped[str]
    owner_id: Mapped[str]
    key: Mapped[str]
    value: Mapped[dict] = mapped_column(JSON)
    provenance: Mapped[str]
    expires_at: Mapped[str] = mapped_column(index=True)
    created_at: Mapped[str] = mapped_column(default=now)
    __table_args__ = (UniqueConstraint("scope", "owner_id", "key"),)


class ToolOperation(Base):
    __tablename__ = "agent_tool_operations"
    id: Mapped[str] = mapped_column(primary_key=True)
    execution_id: Mapped[str] = mapped_column(ForeignKey("ai_executions.id", ondelete="CASCADE"), index=True)
    tool: Mapped[str]
    input_hash: Mapped[str]
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(default=now)


class VoiceCallSession(Base):
    __tablename__ = "voice_call_sessions"
    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)
    execution_id: Mapped[str] = mapped_column(ForeignKey("ai_executions.id", ondelete="CASCADE"), index=True)
    attempt_id: Mapped[str] = mapped_column(ForeignKey("call_attempts.id", ondelete="CASCADE"), unique=True)
    restaurant_id: Mapped[str] = mapped_column(ForeignKey("restaurants.id"))
    transport_state: Mapped[str] = mapped_column(default="PREPARED")
    external_call_sid: Mapped[str | None] = mapped_column(unique=True)
    external_session_id: Mapped[str | None]
    media_token_hash: Mapped[str]
    connected_once: Mapped[bool] = mapped_column(default=False)
    action: Mapped[str] = mapped_column(default="CONSULT")
    proposed_offer: Mapped[dict | None] = mapped_column(JSON)
    accepted_offer: Mapped[dict | None] = mapped_column(JSON)
    evidence: Mapped[dict | None] = mapped_column(JSON)
    deadline: Mapped[str]
    approval_deadline: Mapped[str | None]
    reserved_cost_eur: Mapped[float]
    usage: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(default=now)
    ended_at: Mapped[str | None]
    __table_args__ = (Index("ix_voice_session_state", "transport_state"),)
