import asyncio
import hashlib
import json
import logging
import math
import re
from collections import OrderedDict
from collections.abc import Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from importlib.metadata import version
from pathlib import Path
from time import perf_counter
from types import MappingProxyType

from pydantic import ValidationError
from sqlalchemy import delete, or_, select
from sqlalchemy.exc import SQLAlchemyError

from app.ai.models import AIExecution, VoiceCallSession
from app.models import CallAttempt, ReservationConfirmation, ReservationOffer, new_id, now
from app.observability.contracts import EventData, ModelUsage, SafeIO
from app.observability.models import GraphVersion, ObservationEvent, ObservedExecution

context: ContextVar[Mapping] = ContextVar("observation_context", default=MappingProxyType({}))
logger = logging.getLogger(__name__)
_write_failures = OrderedDict()


@contextmanager
def bind(**values):
    token = context.set({**context.get(), **values})
    try:
        yield
    finally:
        context.reset(token)


def prompt_refs(prompts):
    return {name: {"version": value["version"], "sha256": value["sha256"]} for name, value in prompts.items()}


def ensure_execution(session, booking, *, execution_id=None, mode=None, prompts=None, settings=None):
    ai = session.scalar(select(AIExecution).where(AIExecution.booking_id == booking.id))
    identity = execution_id or (ai.id if ai else booking.id)
    run = session.get(ObservedExecution, identity)
    if run is None:
        run = ObservedExecution(
            id=identity,
            booking_id=booking.id,
            ai_execution_id=ai.id if ai and mode != "voice_sandbox" else None,
            mode=mode or (ai.mode if ai else "simulation"),
            started_at=booking.started_at or now(),
            ended_at=None,
            prompt_versions=prompt_refs(prompts or (ai.prompts if ai else {})),
            configured_models={"reasoning": settings.reasoning_model, "voice": settings.voice_model}
            if settings
            else {},
        )
        session.add(run)
        session.flush()
    return run


@lru_cache(maxsize=1)
def implementation_fingerprint():
    root = Path(__file__).resolve().parents[1]
    files = {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*.py"))
    }
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()


def register_graph(db, compiled, name):
    graph = compiled.get_graph()
    definition = {
        "name": name,
        "nodes": [{"id": key} for key in sorted(graph.nodes)],
        "edges": [
            {"source": e.source, "target": e.target, "conditional": e.conditional, "label": e.data}
            for e in graph.edges
        ],
        "implementation_sha256": implementation_fingerprint(),
        "libraries": {
            key: version(key) for key in ["langgraph", "langgraph-checkpoint-sqlite", "langchain-core"]
        },
    }
    identity = hashlib.sha256(json.dumps(definition, sort_keys=True).encode()).hexdigest()
    with db.transaction(write=True) as session:
        if session.get(GraphVersion, identity) is None:
            session.add(GraphVersion(id=identity, name=name, definition=definition))
    return identity


def safe_data(values):
    # Drop unknown and invalid fields, never serialize the rejected value/error message.
    allowed = {k: v for k, v in (values or {}).items() if k in EventData.model_fields}
    while True:
        try:
            return EventData.model_validate(allowed).model_dump(mode="json", exclude_none=True)
        except ValidationError as exc:
            invalid = {error["loc"][0] for error in exc.errors()}
            allowed = {k: v for k, v in allowed.items() if k not in invalid}


def usage_projection(raw):
    if not isinstance(raw, dict):
        return None
    values = {
        key: value
        for key, value in raw.items()
        if key in ModelUsage.model_fields
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    }
    for group, key, target in [
        ("input_token_details", "audio_tokens", "input_audio_tokens"),
        ("output_token_details", "audio_tokens", "output_audio_tokens"),
        ("input_token_details", "cached_tokens", "cached_tokens"),
    ]:
        value = raw.get(group, {}).get(key) if isinstance(raw.get(group), dict) else None
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            values[target] = value
    return safe_data({"usage": values}).get("usage") or None


def safe_identifier(value):
    return value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_:/.-]{1,250}", value) else None


def tool_io(name, value, *, output=False):
    value = value if isinstance(value, dict) else {}
    # No requirements, offers, quotes, contact fields, restaurant names or free text.
    safe = {"supplied": bool(value)}
    if output:
        for key in ["negotiation_decision", "verification_result"]:
            if isinstance(value.get(key), dict):
                value = value[key]
                break
        for key in [
            "status",
            "evaluation",
            "confirmation_id",
            "restaurant_id",
            "attempt_id",
            "version",
            "completed_attempts",
            "passed",
            "confirmed",
        ]:
            if key in value:
                safe[key] = value[key]
        for key in ["restaurant_ids", "attempts", "observations", "reasons"]:
            if isinstance(value.get(key), list):
                safe["count"] = len(value[key])
    # Validate as part of EventData so unexpected new status values are safely omitted.
    return safe_data({"output" if output else "input": safe}).get(
        "output" if output else "input", SafeIO().model_dump()
    )


def _offset(timestamp, origin):
    if not origin:
        return None
    return max(
        0, int((datetime.fromisoformat(timestamp) - datetime.fromisoformat(origin)).total_seconds() * 1000)
    )


def append(
    session, execution_id, kind, phase="observed", *, data=None, elapsed_ms=None, occurred_at=None, **scope
):
    run = session.get(ObservedExecution, execution_id)
    if run is None or run.events_pruned_at:
        return None
    values = {**context.get(), **scope}
    timestamp = occurred_at or now()
    attempt = (
        session.get(CallAttempt, values.get("call_attempt_id")) if values.get("call_attempt_id") else None
    )
    if attempt and attempt.booking_id != run.booking_id:
        raise ValueError("Observation attempt outside execution scope")
    call = (
        session.scalar(select(VoiceCallSession).where(VoiceCallSession.attempt_id == attempt.id))
        if attempt
        else None
    )
    agent = values.get("agent")
    prompt = run.prompt_versions.get(agent, {})
    fields = {
        key: safe_identifier(values.get(key))
        for key in [
            "span_id",
            "parent_span_id",
            "agent_run_id",
            "tool_call_id",
            "delegation_id",
            "checkpoint_id",
            "model",
            "reported_model",
            "tool",
            "agent",
            "node",
        ]
    }
    row = ObservationEvent(
        execution_id=run.id,
        booking_id=run.booking_id,
        kind=kind,
        phase=phase,
        call_attempt_id=attempt.id if attempt else None,
        call_session_id=call.id if call else safe_identifier(values.get("call_session_id")),
        graph_thread_id=safe_identifier(values.get("graph_thread_id")) or run.graph_thread_id,
        graph_version=values.get("graph_version") or run.graph_version,
        external_call_id=call.external_call_sid if call else values.get("external_call_id"),
        external_session_id=safe_identifier(values.get("external_session_id"))
        or (call.external_session_id if call else None),
        prompt_version=prompt.get("version"),
        prompt_sha256=prompt.get("sha256"),
        occurred_at=timestamp,
        received_at=now(),
        elapsed_ms=elapsed_ms,
        execution_offset_ms=_offset(timestamp, run.started_at),
        call_offset_ms=_offset(timestamp, attempt.started_at) if attempt else None,
        data=safe_data(data),
        **fields,
    )
    session.add(row)
    session.flush()
    return row


def record(db, execution_id, kind, phase="observed", **kwargs):
    key = (str(db.engine.url), execution_id)
    try:
        with db.transaction(write=True) as session:
            run = session.get(ObservedExecution, execution_id)
            missed = _write_failures.get(key, 0)
            if missed and run:
                run.dropped_events += missed
                append(session, execution_id, "telemetry.gap", data={"suppressed_events": missed})
            result = append(session, execution_id, kind, phase, **kwargs)
        _write_failures.pop(key, None)
        return result
    except SQLAlchemyError:
        # Telemetry must never convert an already-dialed call into a retryable failure.
        # A missing end/start remains an explicit coverage gap in the read API.
        logger.error("observation_write_failed")
        _write_failures[key] = _write_failures.get(key, 0) + 1
        if len(_write_failures) > 1000:
            _write_failures.popitem(last=False)
        return None


class ObservationSpan:
    def __init__(self):
        self.output = None
        self.usage = None
        self.reported_model = None
        self.cached = None


@contextmanager
def observed_span(db, execution_id, kind, *, agent=None, tool=None, input=None, **scope):
    identity = new_id()
    parent = context.get()
    fields = {
        "span_id": identity,
        "parent_span_id": parent.get("span_id"),
        "agent": agent or parent.get("agent"),
        "tool": tool,
        **scope,
    }
    if kind in {"agent", "voice.session"}:
        fields["agent_run_id"] = identity
    elif kind == "tool":
        fields["tool_call_id"] = identity
    state = ObservationSpan()
    started = perf_counter()
    with bind(**fields):
        record(db, execution_id, kind, "started", data={"input": input} if input is not None else {})
        try:
            yield state
        except BaseException as exc:
            # LangGraph interrupts are control flow, never reported as failed agents.
            from langgraph.errors import GraphInterrupt

            phase = (
                "interrupted"
                if isinstance(exc, GraphInterrupt)
                else "cancelled"
                if isinstance(exc, asyncio.CancelledError)
                else "failed"
            )
            record(
                db,
                execution_id,
                kind,
                phase,
                elapsed_ms=int((perf_counter() - started) * 1000),
                data={"error_type": type(exc).__name__, "error_code": getattr(exc, "code", None)},
            )
            raise
        else:
            record(
                db,
                execution_id,
                kind,
                "completed",
                elapsed_ms=int((perf_counter() - started) * 1000),
                reported_model=state.reported_model,
                data={"output": state.output, "usage": state.usage, "cached": state.cached},
            )


def record_business(session, booking, event_type, event_id):
    if not booking.started_at or event_type == "agent.activity":
        return
    run = ensure_execution(session, booking)
    run.ended_at = booking.finished_at
    call = session.scalar(
        select(CallAttempt)
        .where(CallAttempt.booking_id == booking.id)
        .order_by(CallAttempt.sequence.desc())
        .limit(1)
    )
    call_events = {
        "call.started",
        "call.completed",
        "alternative.proposed",
        "user.approval_required",
        "user.decision_received",
        "booking.confirmed",
        "booking.failed",
    }
    if event_type not in call_events and not (
        event_type == "booking.cancelled" and call and call.result == "CANCELLED"
    ):
        call = None
    offer = (
        session.scalar(select(ReservationOffer).where(ReservationOffer.attempt_id == call.id).limit(1))
        if call
        else None
    )
    confirmation = session.scalar(
        select(ReservationConfirmation).where(ReservationConfirmation.booking_id == booking.id)
    )
    append(
        session,
        run.id,
        "backend." + event_type,
        "committed",
        call_attempt_id=call.id if call else None,
        data={
            "business_event_id": event_id,
            "booking_version": booking.version,
            "status": booking.status,
            "result": call.result if call else None,
            "offer_id": offer.id if offer else None,
            "decision": offer.decision if offer else None,
            "confirmation_id": confirmation.id if confirmation else None,
            "simulated": run.mode != "real_telephony",
        },
    )


def prune(session, days):
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    active_calls = select(VoiceCallSession.execution_id).where(
        VoiceCallSession.transport_state.in_(["ACTIVE", "DIALING", "UNCERTAIN"])
    )
    runs = session.scalars(
        select(ObservedExecution).where(
            or_(
                ObservedExecution.ended_at < cutoff,
                (ObservedExecution.mode == "voice_sandbox") & (ObservedExecution.started_at < cutoff),
            ),
            ObservedExecution.events_pruned_at.is_(None),
        )
    )
    protected = set(session.scalars(active_calls))
    for run in runs:
        if run.ai_execution_id in protected:
            continue
        session.execute(delete(ObservationEvent).where(ObservationEvent.execution_id == run.id))
        run.events_pruned_at = now()
