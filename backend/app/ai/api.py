from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import delete, select

from app.ai.contracts import ExecutionView, MemoryInput, MemoryView, TraceView
from app.ai.models import AgentMemory, AgentTrace, AIExecution, VoiceCallSession
from app.api.dependencies import Version, authenticate
from app.core.errors import DomainError
from app.models import BookingEvent, now
from app.repositories import require_booking
from app.schemas import BookingConfiguration
from app.services.bookings import check_version, emit

router = APIRouter(prefix="/api", dependencies=[Depends(authenticate)], tags=["AI"])


def execution_row(session, booking_id):
    require_booking(session, booking_id)
    execution = session.scalar(select(AIExecution).where(AIExecution.booking_id == booking_id))
    if execution is None:
        raise DomainError("not_found", "This booking has no AI execution", 404)
    return execution


@router.get("/ai/capabilities")
def capabilities(request: Request) -> dict:
    settings = request.app.state.settings
    return {
        "ai_simulation": True,
        "voice_sandbox_enabled": settings.voice_sandbox_enabled,
        "real_telephony_enabled": settings.real_telephony_enabled,
        "openai_credentials_configured": bool(settings.openai_api_key),
        "reasoning_model": settings.reasoning_model,
        "voice_model": settings.voice_model,
        "extraction_mode": settings.ai_extraction_mode,
        "recording_enabled": False,
    }


@router.get("/bookings/{booking_id}/ai", response_model=ExecutionView)
def ai_execution(request: Request, booking_id: str):
    with request.app.state.db.transaction() as session:
        row = execution_row(session, booking_id)
        return ExecutionView(
            **{key: getattr(row, key) for key in ExecutionView.model_fields if hasattr(row, key)},
            prompt_versions={k: f"{v['version']}:{v['sha256']}" for k, v in row.prompts.items()},
        )


@router.get("/bookings/{booking_id}/ai/state")
async def graph_state(request: Request, booking_id: str) -> dict:
    with request.app.state.db.transaction() as session:
        row = execution_row(session, booking_id)
        execution_id = row.id
        business_status = require_booking(session, booking_id).status
    snapshot = await request.app.state.ai.graph.aget_state({"configurable": {"thread_id": execution_id}})
    return {
        "execution_id": execution_id,
        "business_status": business_status,
        "next_nodes": list(snapshot.next),
        "values": snapshot.values,
        "interrupts": [i.value for t in snapshot.tasks for i in t.interrupts],
    }


@router.get("/bookings/{booking_id}/ai/traces", response_model=list[TraceView])
def traces(
    request: Request,
    booking_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    after_id: int = Query(default=0, ge=0),
):
    with request.app.state.db.transaction() as session:
        row = execution_row(session, booking_id)
        return [
            TraceView.model_validate(t)
            for t in session.scalars(
                select(AgentTrace)
                .where(
                    AgentTrace.execution_id == row.id,
                    AgentTrace.id > after_id,
                )
                .order_by(AgentTrace.id)
                .limit(limit)
            )
        ]


def set_pause(request, booking_id, version, paused):
    with request.app.state.db.transaction(write=True) as session:
        execution = execution_row(session, booking_id)
        booking = require_booking(session, booking_id)
        check_version(booking, version)
        if booking.status not in {"RUNNING", "WAITING_FOR_USER"}:
            raise DomainError("invalid_transition", "Only an active AI execution can pause or resume")
        if execution.paused != paused:
            execution.paused = paused
            emit(session, booking, "booking.updated")
        return {
            "paused": execution.paused,
            "version": booking.version,
            "effective_at": "next_attempt_boundary",
            "approval_still_required": booking.status == "WAITING_FOR_USER",
        }


@router.post("/bookings/{booking_id}/ai/pause")
def pause(request: Request, booking_id: str, version: Version) -> dict:
    return set_pause(request, booking_id, version, True)


@router.post("/bookings/{booking_id}/ai/resume")
def resume(request: Request, booking_id: str, version: Version) -> dict:
    return set_pause(request, booking_id, version, False)


@router.get("/ai/memories", response_model=list[MemoryView])
def memories(
    request: Request,
    scope: Literal["booking", "restaurant", "preference"] | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    with request.app.state.db.transaction() as session:
        query = select(AgentMemory).where(AgentMemory.expires_at > now())
        if scope:
            query = query.where(AgentMemory.scope == scope)
        return [
            MemoryView.model_validate(m)
            for m in session.scalars(
                query.order_by(AgentMemory.created_at.desc()).offset(offset).limit(limit)
            )
        ]


@router.post("/ai/memories/preferences", response_model=MemoryView)
def save_preference(request: Request, payload: MemoryInput):
    current = datetime.now(UTC)
    if payload.expires_at.tzinfo is None or not current < payload.expires_at <= current + timedelta(
        days=request.app.state.settings.ai_retention_days
    ):
        raise DomainError(
            "invalid_expiry", "Preference expiry must be within the configured retention period", 422
        )
    try:
        config = BookingConfiguration.model_validate({payload.key: payload.value})
    except ValueError:
        raise DomainError(
            "invalid_preference", "Preference value does not match its configuration field", 422
        ) from None
    value = config.model_dump(mode="json")[payload.key]
    with request.app.state.db.transaction(write=True) as session:
        row = session.scalar(
            select(AgentMemory).where(
                AgentMemory.scope == "preference",
                AgentMemory.owner_id == "local",
                AgentMemory.key == payload.key,
            )
        )
        if row is None:
            row = AgentMemory(
                scope="preference",
                owner_id="local",
                key=payload.key,
                provenance="USER_AUTHORIZED",
                value={},
                expires_at="",
            )
            session.add(row)
        row.value, row.expires_at = {"value": value}, payload.expires_at.astimezone(UTC).isoformat()
        session.flush()
        return MemoryView.model_validate(row)


@router.delete("/ai/memories/{memory_id}", status_code=204)
def delete_memory(request: Request, memory_id: str):
    with request.app.state.db.transaction(write=True) as session:
        row = session.get(AgentMemory, memory_id)
        if row:
            session.delete(row)


@router.delete("/bookings/{booking_id}/ai/data", status_code=204)
async def delete_ai_data(request: Request, booking_id: str, version: Version):
    with request.app.state.db.transaction() as session:
        row = execution_row(session, booking_id)
        booking = require_booking(session, booking_id)
        check_version(booking, version)
        if booking.status not in {"CONFIRMED", "FAILED", "EXHAUSTED", "CANCELLED"}:
            raise DomainError("execution_active", "AI data can only be erased after the execution finishes")
        if session.scalar(
            select(VoiceCallSession.id).where(
                VoiceCallSession.execution_id == row.id,
                VoiceCallSession.transport_state.in_(["DIALING", "ACTIVE", "UNCERTAIN"]),
            )
        ):
            raise DomainError(
                "call_reconciliation_required", "Reconcile the external call before erasing its records"
            )
        execution_id = row.id
    await request.app.state.ai.erase_checkpoints(execution_id)
    with request.app.state.db.transaction(write=True) as session:
        # Recheck before deletion; terminal bookings cannot transition back into RUNNING.
        check_version(require_booking(session, booking_id), version)
        session.execute(
            delete(BookingEvent).where(
                BookingEvent.booking_id == booking_id, BookingEvent.event_type == "agent.activity"
            )
        )
        session.execute(
            delete(AgentMemory).where(AgentMemory.scope == "booking", AgentMemory.owner_id == booking_id)
        )
        for memory in session.scalars(select(AgentMemory).where(AgentMemory.scope == "restaurant")):
            if memory.value.get("booking_id") == booking_id:
                session.delete(memory)
        session.delete(session.get(AIExecution, execution_id))
