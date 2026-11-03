from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from app.core.errors import DomainError
from app.models import BookingRequest
from app.observability.contracts import (
    ObservationEventOut,
    ObservationPage,
    ObservedExecutionOut,
    ObservedExecutionPage,
)
from app.observability.models import ObservationEvent, ObservedExecution


def require_execution(session, identity):
    run = session.get(ObservedExecution, identity)
    if run is None:
        raise DomainError("not_found", "No recorded execution with this ID", 404)
    return run


def execution_view(session, run):
    end = aliased(ObservationEvent)
    closed = (
        select(end.id)
        .where(
            end.execution_id == run.id,
            end.span_id == ObservationEvent.span_id,
            end.phase.in_(["completed", "failed", "interrupted", "cancelled"]),
        )
        .exists()
    )
    open_spans = list(
        session.scalars(
            select(ObservationEvent.span_id)
            .where(ObservationEvent.execution_id == run.id, ObservationEvent.phase == "started", ~closed)
            .order_by(ObservationEvent.id)
            .limit(100)
        )
    )
    count = session.scalar(
        select(func.count()).select_from(ObservationEvent).where(ObservationEvent.execution_id == run.id)
    )
    return ObservedExecutionOut(
        **{key: getattr(run, key) for key in ObservedExecutionOut.model_fields if hasattr(run, key)},
        booking_status=session.get(BookingRequest, run.booking_id).status,
        event_count=count,
        open_span_ids=open_spans,
        coverage="pruned"
        if run.events_pruned_at
        else "degraded"
        if run.dropped_events
        else "recorded"
        if count
        else "empty",
    )


def executions(session, *, booking_id=None, mode=None, limit=50, offset=0):
    statement = select(ObservedExecution)
    if booking_id:
        statement = statement.where(ObservedExecution.booking_id == booking_id)
    if mode:
        statement = statement.where(ObservedExecution.mode == mode)
    total = session.scalar(select(func.count()).select_from(statement.subquery()))
    rows = session.scalars(
        statement.order_by(ObservedExecution.started_at.desc(), ObservedExecution.id)
        .offset(offset)
        .limit(limit)
    )
    return ObservedExecutionPage(
        items=[execution_view(session, run) for run in rows], total=total, limit=limit, offset=offset
    )


def events(
    session, *, after_event_id=0, until_event_id=None, execution_id=None, call_attempt_id=None, limit=100
):
    statement = select(ObservationEvent)
    if execution_id:
        require_execution(session, execution_id)
        statement = statement.where(ObservationEvent.execution_id == execution_id)
    if call_attempt_id:
        statement = statement.where(ObservationEvent.call_attempt_id == call_attempt_id)
    high = session.scalar(select(func.max(statement.subquery().c.id)))
    high = min(high or 0, until_event_id) if until_event_id is not None else high or 0
    rows = session.scalars(
        statement.where(ObservationEvent.id > after_event_id, ObservationEvent.id <= high)
        .order_by(ObservationEvent.id)
        .limit(limit + 1)
    ).all()
    page = rows[:limit]
    more = len(rows) > limit
    cursor = page[-1].id if more else max(after_event_id, high)
    return ObservationPage(
        items=[ObservationEventOut.model_validate(row) for row in page],
        next_after_event_id=cursor,
        has_more=more,
        high_watermark=high,
    )
