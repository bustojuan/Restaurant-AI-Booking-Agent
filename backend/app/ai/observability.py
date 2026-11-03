from contextlib import contextmanager
from time import perf_counter

from app.ai.models import AgentTrace, AIExecution
from app.db.session import Database
from app.observability.recorder import append, observed_span
from app.repositories import require_booking
from app.services.bookings import emit


def trace(
    db: Database,
    execution_id: str,
    agent: str,
    phase: str,
    *,
    tool: str | None = None,
    elapsed_ms: int | None = None,
    details: dict | None = None,
    model: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    observe: bool = True,
):
    # Callers pass machine codes/counts, never prompts, transcripts, configuration or tool inputs.
    with db.transaction(write=True) as session:
        execution = session.get(AIExecution, execution_id)
        if execution is None:
            return
        execution.active_agent = agent if phase == "started" else None
        row = AgentTrace(
            execution_id=execution_id,
            agent=agent,
            phase=phase,
            tool=tool,
            elapsed_ms=elapsed_ms,
            details=details or {},
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        session.add(row)
        session.flush()
        if observe:
            append(
                session,
                execution_id,
                "model.usage" if model else "legacy.activity",
                "observed",
                agent=agent,
                tool=tool,
                model=model,
                elapsed_ms=elapsed_ms,
                data={
                    "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
                    "error_type": (details or {}).get("error_type"),
                },
            )
        emit(
            session,
            require_booking(session, execution.booking_id),
            "agent.activity",
            bump=False,
            activity={
                "trace_id": row.id,
                "execution_id": execution_id,
                "agent": agent,
                "phase": phase,
                "tool": tool,
                "elapsed_ms": elapsed_ms,
            },
        )


@contextmanager
def span(db: Database, execution_id: str, agent: str, tool: str | None = None, *, input=None):
    started = perf_counter()
    with observed_span(
        db, execution_id, "tool" if tool else "agent", agent=agent, tool=tool, input=input
    ) as observation:
        trace(db, execution_id, agent, "started", tool=tool, observe=False)
        try:
            yield observation
        except Exception as exc:
            trace(
                db,
                execution_id,
                agent,
                "failed",
                tool=tool,
                elapsed_ms=int((perf_counter() - started) * 1000),
                details={"error_type": type(exc).__name__},
                observe=False,
            )
            raise
        else:
            trace(
                db,
                execution_id,
                agent,
                "completed",
                tool=tool,
                elapsed_ms=int((perf_counter() - started) * 1000),
                observe=False,
            )
