"""Administrative projections; the booking engine remains the only execution owner."""

from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from statistics import mean
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import Depends, Query, Request
from sqlalchemy import and_, func, or_, select

from app.ai.models import AIExecution, VoiceCallSession
from app.ai.prompts import prompt_bundle
from app.core.errors import DomainError
from app.models import (
    BookingRequest,
    CallAttempt,
    ReservationConfirmation,
    ReservationOffer,
    Restaurant,
    SimulationScenario,
)
from app.observability.api import router
from app.observability.center_contracts import (
    AdminScenarioOut,
    AdminSettingsOut,
    AnalyticsOut,
    BookingHistoryOut,
    BookingHistoryPage,
    CallOut,
    CallPage,
    EvaluationOut,
    PlaygroundInput,
    PlaygroundOut,
)
from app.observability.models import ObservationEvent, ObservedExecution
from app.schemas import BookingConfiguration, BookingCreate, DietaryRequirement
from app.services import bookings, execution


class Filters:
    def __init__(
        self,
        q: str = Query("", max_length=200),
        mode: Literal["simulation", "ai_simulation", "real_telephony", "voice_sandbox"] | None = None,
        status: str | None = Query(None, max_length=60),
        result: str | None = Query(None, max_length=60),
        date_from: date | None = None,
        date_to: date | None = None,
        model: str | None = Query(None, max_length=250),
        prompt: str | None = Query(None, max_length=250),
    ):
        if date_from and date_to and date_from > date_to:
            raise DomainError("invalid_period", "Start date must precede end date", 422)
        self.q, self.mode, self.status, self.result = q, mode, status, result
        self.date_from, self.date_to, self.model, self.prompt = date_from, date_to, model, prompt


def history_statement(filters):
    # Sandbox sessions have no CallAttempt and are not silently presented as phone calls.
    statement = (
        select(CallAttempt, Restaurant, BookingRequest, AIExecution, ObservedExecution, VoiceCallSession)
        .join(Restaurant, CallAttempt.restaurant_id == Restaurant.id)
        .join(BookingRequest, CallAttempt.booking_id == BookingRequest.id)
        .outerjoin(AIExecution, AIExecution.booking_id == BookingRequest.id)
        .outerjoin(
            ObservedExecution,
            and_(
                ObservedExecution.booking_id == BookingRequest.id,
                ObservedExecution.mode != "voice_sandbox",
            ),
        )
        .outerjoin(VoiceCallSession, VoiceCallSession.attempt_id == CallAttempt.id)
    )
    mode = func.coalesce(AIExecution.mode, ObservedExecution.mode, "unknown")
    if filters.mode:
        statement = statement.where(mode == filters.mode)
    if filters.status:
        statement = statement.where(CallAttempt.status == filters.status)
    if filters.result:
        statement = statement.where(CallAttempt.result == filters.result)
    if filters.q:
        # Escape SQL wildcard characters; search is a literal substring.
        statement = statement.where(
            or_(
                Restaurant.name.contains(filters.q, autoescape=True),
                CallAttempt.id.contains(filters.q, autoescape=True),
                BookingRequest.id.contains(filters.q, autoescape=True),
            )
        )
    for value, end in [(filters.date_from, False), (filters.date_to, True)]:
        if value:
            day = value + timedelta(days=1) if end else value
            boundary = datetime.combine(day, datetime.min.time(), ZoneInfo("Europe/Madrid"))
            timestamp = boundary.astimezone(UTC).isoformat()
            statement = statement.where(
                CallAttempt.started_at < timestamp if end else CallAttempt.started_at >= timestamp
            )
    if filters.model or filters.prompt:
        event = select(ObservationEvent.id).where(ObservationEvent.execution_id == ObservedExecution.id)
        if filters.model:
            event = event.where(
                or_(ObservationEvent.model == filters.model, ObservationEvent.reported_model == filters.model)
            )
        if filters.prompt:
            event = event.where(ObservationEvent.prompt_version == filters.prompt)
        statement = statement.where(event.exists())
    return statement


def call_view(session, row, *, explain=False):
    attempt, restaurant, booking, ai, run, voice = row
    confirmation = session.scalar(
        select(ReservationConfirmation).where(ReservationConfirmation.attempt_id == attempt.id)
    )
    from app.observability.explanation import explain_attempt

    return CallOut(
        id=attempt.id,
        booking_id=booking.id,
        restaurant_id=restaurant.id,
        restaurant_name=restaurant.name,
        sequence=attempt.sequence,
        started_at=attempt.started_at,
        completed_at=attempt.completed_at,
        duration_ms=attempt.duration_ms,
        status=attempt.status,
        result=attempt.result,
        mode=ai.mode if ai else run.mode if run else "unknown",
        execution_id=run.id if run else None,
        call_session_id=voice.id if voice else None,
        transport_state=voice.transport_state if voice else None,
        coverage="unavailable"
        if not run
        else "pruned"
        if run.events_pruned_at
        else "degraded"
        if run.dropped_events
        else "recorded",
        models=sorted(set(run.configured_models.values())) if run else [],
        prompt_versions=sorted(
            {v["version"] for v in run.prompt_versions.values() if isinstance(v, dict) and "version" in v}
        )
        if run
        else [],
        confirmation_id=confirmation.id if confirmation else None,
        execution_summary=ai.summary_text if ai else None,
        explanation=explain_attempt(session, attempt, booking, ai, run, voice, confirmation)
        if explain
        else None,
    )


@router.get("/calls", response_model=CallPage)
def calls(
    request: Request,
    filters: Annotated[Filters, Depends()],
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    sort: Literal["started_at", "duration_ms", "restaurant", "status"] = "started_at",
    direction: Literal["asc", "desc"] = "desc",
):
    statement = history_statement(filters)
    column = {
        "started_at": CallAttempt.started_at,
        "duration_ms": CallAttempt.duration_ms,
        "restaurant": Restaurant.name,
        "status": CallAttempt.status,
    }[sort]
    with request.app.state.db.transaction() as session:
        total = session.scalar(select(func.count()).select_from(statement.subquery()))
        rows = session.execute(
            statement.order_by(column.asc() if direction == "asc" else column.desc(), CallAttempt.id)
            .offset(offset)
            .limit(limit)
        )
        return CallPage(
            items=[call_view(session, row) for row in rows], total=total, limit=limit, offset=offset
        )


@router.get("/calls/{call_id}", response_model=CallOut)
def call(request: Request, call_id: str):
    with request.app.state.db.transaction() as session:
        row = session.execute(
            history_statement(Filters(q="", status=None, result=None, model=None, prompt=None)).where(
                CallAttempt.id == call_id
            )
        ).first()
        if row is None:
            raise DomainError("not_found", "Call not found", 404)
        return call_view(session, row, explain=True)


@router.get("/bookings", response_model=BookingHistoryPage)
def booking_history(
    request: Request,
    filters: Annotated[Filters, Depends()],
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    statement = history_statement(filters)
    with request.app.state.db.transaction() as session:
        matching = statement.with_only_columns(CallAttempt.booking_id).distinct().subquery()
        query = select(BookingRequest).where(BookingRequest.id.in_(select(matching.c.booking_id)))
        total = session.scalar(select(func.count()).select_from(query.subquery()))
        items = []
        for booking in session.scalars(
            query.order_by(BookingRequest.started_at.desc(), BookingRequest.id).offset(offset).limit(limit)
        ):
            # Expand all calls for a matching booking, including calls outside the row filters.
            rows = session.execute(
                history_statement(Filters(q="", status=None, result=None, model=None, prompt=None))
                .where(BookingRequest.id == booking.id)
                .order_by(CallAttempt.sequence)
            )
            children = [call_view(session, row) for row in rows]
            items.append(
                BookingHistoryOut(
                    id=booking.id,
                    status=booking.status,
                    mode=children[0].mode,
                    started_at=booking.started_at,
                    finished_at=booking.finished_at,
                    calls=children,
                    confirmation_id=next((c.confirmation_id for c in children if c.confirmation_id), None),
                )
            )
        return BookingHistoryPage(items=items, total=total, limit=limit, offset=offset)


@router.get("/analytics", response_model=AnalyticsOut)
def analytics(request: Request, filters: Annotated[Filters, Depends()]):
    with request.app.state.db.transaction() as session:
        rows = session.execute(history_statement(filters)).all()
        attempts = {row[0].id: row[0] for row in rows}
        booking_ids = {row[2].id for row in rows}
        runs = {row[4].id for row in rows if row[4]}
        # Include execution-wide coordination; restrict call-scoped events to matching calls.
        events = session.scalars(
            select(ObservationEvent)
            .where(
                ObservationEvent.execution_id.in_(runs),
                or_(
                    ObservationEvent.call_attempt_id.is_(None), ObservationEvent.call_attempt_id.in_(attempts)
                ),
            )
            .order_by(ObservationEvent.id)
        ).all()
        confirmations = list(
            session.scalars(
                select(ReservationConfirmation).where(ReservationConfirmation.booking_id.in_(booking_ids))
            )
        )
        daily = defaultdict(lambda: {"calls": 0, "confirmations": 0, "durations": []})
        for attempt in attempts.values():
            key = datetime.fromisoformat(attempt.started_at).astimezone(ZoneInfo("Europe/Madrid")).date()
            daily[key]["calls"] += 1
            if attempt.duration_ms is not None:
                daily[key]["durations"].append(attempt.duration_ms)
        for confirmation in confirmations:
            attempt = attempts.get(confirmation.attempt_id)
            if attempt:
                key = datetime.fromisoformat(attempt.started_at).astimezone(ZoneInfo("Europe/Madrid")).date()
                daily[key]["confirmations"] += 1
        agent_data = defaultdict(lambda: {"invocations": 0, "completed": 0, "errors": 0, "durations": []})
        tools, models, prompts, usage, model_durations = Counter(), set(), set(), [], []
        interventions = session.scalar(
            select(func.count())
            .select_from(ReservationOffer)
            .where(
                ReservationOffer.booking_id.in_(booking_ids),
                ReservationOffer.decision.in_(["APPROVED", "REJECTED"]),
            )
        )
        for event in events:
            if event.model:
                models.add(event.model)
            if event.reported_model:
                models.add(event.reported_model)
            if event.prompt_version:
                prompts.add(event.prompt_version)
            if event.kind == "agent" and event.agent:
                item = agent_data[event.agent]
                item["invocations"] += event.phase == "started"
                item["completed"] += event.phase == "completed"
                item["errors"] += event.phase == "failed"
                if event.elapsed_ms is not None:
                    item["durations"].append(event.elapsed_ms)
            if event.kind == "tool" and event.phase == "started" and event.tool:
                tools[event.tool] += 1
            # Canonical model/voice spans own usage; do not sum duplicate status events.
            if event.kind in {"model", "voice.session"} and event.phase == "completed":
                if event.data.get("usage"):
                    usage.append(event.data["usage"])
                if event.kind == "model" and event.elapsed_ms is not None:
                    model_durations.append(event.elapsed_ms)
        durations = [a.duration_ms for a in attempts.values() if a.duration_ms is not None]

        def token_sum(key):
            values = [u[key] for u in usage if u.get(key) is not None]
            return sum(values) if values else None

        return AnalyticsOut(
            calls=len(attempts),
            bookings=len(booking_ids),
            confirmed_bookings=len(confirmations),
            confirmation_rate=len(confirmations) / len(booking_ids) if booking_ids else None,
            average_duration_ms=mean(durations) if durations else None,
            attempts_per_booking=len(attempts) / len(booking_ids) if booking_ids else None,
            errors=sum(
                a.result in {"ERROR", "TIMEOUT", "UNCERTAIN"} or a.status == "FAILED"
                for a in attempts.values()
            ),
            human_interventions=interventions,
            instrumented_executions=len(runs),
            days=[
                {
                    "date": day,
                    "calls": v["calls"],
                    "confirmations": v["confirmations"],
                    "average_ms": mean(v["durations"]) if v["durations"] else None,
                }
                for day, v in sorted(daily.items())
            ],
            results=[
                {"name": name, "count": count}
                for name, count in Counter(a.result or "PENDING" for a in attempts.values()).items()
            ],
            agents=[
                {
                    "name": name,
                    "invocations": v["invocations"],
                    "completed": v["completed"],
                    "errors": v["errors"],
                    "average_ms": mean(v["durations"]) if v["durations"] else None,
                }
                for name, v in agent_data.items()
            ],
            tools=[{"name": name, "count": count} for name, count in tools.most_common()],
            models=sorted(models),
            prompt_versions=sorted(prompts),
            input_tokens=token_sum("input_tokens"),
            output_tokens=token_sum("output_tokens"),
            model_latency_ms=mean(model_durations) if model_durations else None,
        )


@router.get("/settings", response_model=AdminSettingsOut)
def settings(request: Request):
    config = request.app.state.settings
    return AdminSettingsOut(
        reasoning_model=config.reasoning_model,
        voice_model=config.voice_model,
        extraction_mode=config.ai_extraction_mode,
        voice_provider="OpenAI GPT-Live",
        telephone_provider="Twilio",
        voice_enabled=config.voice_sandbox_enabled,
        telephony_enabled=config.real_telephony_enabled,
        retention_days=config.ai_retention_days,
        prompts={k: {"version": v["version"], "sha256": v["sha256"]} for k, v in prompt_bundle().items()},
        playground_available=config.ai_extraction_mode == "deterministic",
    )


@router.get("/playground/scenarios", response_model=list[AdminScenarioOut])
def scenarios(request: Request):
    with request.app.state.db.transaction() as session:
        return [
            AdminScenarioOut(
                id=s.id,
                name=s.name,
                available=request.app.state.settings.ai_extraction_mode == "deterministic",
            )
            for s in session.scalars(select(SimulationScenario).order_by(SimulationScenario.id))
        ]


@router.post("/playground/runs", response_model=PlaygroundOut, status_code=201)
def simulate(request: Request, payload: PlaygroundInput):
    config = request.app.state.settings
    if config.ai_extraction_mode != "deterministic":
        raise DomainError(
            "playground_unavailable",
            "Playground requires deterministic extraction; paid models are not enabled here",
            409,
        )
    with request.app.state.db.transaction(write=True) as session:
        if session.get(SimulationScenario, payload.scenario_id) is None:
            raise DomainError("not_found", "Scenario not found", 404)
        ids = list(
            session.scalars(
                select(Restaurant.id)
                .where(Restaurant.is_simulated.is_(True))
                .order_by(Restaurant.id)
                .limit(3)
            )
        )
        if not ids:
            raise DomainError("simulation_catalog_missing", "No simulated restaurants are configured", 409)
        # Fixed non-personal simulation identity; no workspace/draft/favorites mutation.
        configuration = BookingConfiguration(
            customer_name="Playground simulation",
            contact_phone="+34000000000",
            requested_date=(datetime.now(ZoneInfo("Europe/Madrid")) + timedelta(days=14)).date(),
            preferred_time="21:00:00",
            adults=payload.adults,
            flexibility_minutes=payload.flexibility_minutes,
            dietary_requirements=[DietaryRequirement(kind="celiac", code="gluten", mandatory=True)]
            if payload.scenario_id == "missing-evidence"
            else [],
        )
        booking = bookings.create_booking(
            session, BookingCreate(configuration=configuration, restaurant_ids=ids)
        )
        summary = execution.start(
            session, booking.id, booking.version, payload.scenario_id, mode="ai_simulation", settings=config
        )
        return PlaygroundOut(booking_id=summary.id, scenario_id=payload.scenario_id, status=summary.status)


@router.get("/playground/runs/{booking_id}", response_model=EvaluationOut)
def evaluation(request: Request, booking_id: str):
    with request.app.state.db.transaction() as session:
        booking = session.get(BookingRequest, booking_id)
        if booking is None:
            raise DomainError("not_found", "Booking not found", 404)
        ai = session.scalar(select(AIExecution).where(AIExecution.booking_id == booking_id))
        if ai is None or ai.mode != "ai_simulation":
            raise DomainError("invalid_mode", "Only AI simulations are exposed here", 409)
        report = ai.quality_report or {}
        events = session.scalars(select(ObservationEvent).where(ObservationEvent.execution_id == ai.id)).all()
        duration = (
            int(
                (
                    datetime.fromisoformat(booking.finished_at) - datetime.fromisoformat(booking.started_at)
                ).total_seconds()
                * 1000
            )
            if booking.finished_at
            else None
        )
        return EvaluationOut(
            booking_id=booking.id,
            scenario_id=booking.scenario_id,
            status=booking.status,
            passed=report.get("passed"),
            confirmed=report.get("confirmed"),
            checks={k: v for k, v in report.get("checks", {}).items() if isinstance(v, bool)},
            agent_count=len({e.agent for e in events if e.kind == "agent" and e.agent}),
            tools=sorted({e.tool for e in events if e.tool}),
            duration_ms=duration,
        )
