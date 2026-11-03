import asyncio
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from langsmith import tracing_context
from openai import AsyncOpenAI
from sqlalchemy import delete, select

from app.ai.agents import (
    EvaluationAgent,
    MemorySummaryAgent,
    NegotiationAgent,
    PlanningAgent,
    ResearchAgent,
    VerificationAgent,
)
from app.ai.contracts import GraphState, ReservationEvidence
from app.ai.models import AgentMemory, AgentTrace, AIExecution, ToolOperation, VoiceCallSession
from app.ai.observability import span
from app.ai.simulation import AISimulationCallProvider
from app.ai.tools import AgentTools, ToolScope
from app.models import BookingRequest, CallAttempt, ReservationOffer
from app.observability.graph import instrument_node
from app.observability.recorder import bind, ensure_execution, observed_span, prune, record, register_graph
from app.repositories import attempts, require_booking
from app.schemas import BookingConfiguration, OfferDetails


class AIRuntime:
    def __init__(self, db, engine, settings, saver):
        self.db, self.engine, self.settings = db, engine, settings
        self.saver = saver
        self.graph = self._build().compile(checkpointer=saver)
        self.locks: dict[str, asyncio.Lock] = {}
        self.next_maintenance = 0.0
        self.next_trace_prune = 0.0
        self.model_client = (
            AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value(), timeout=15, max_retries=0)
            if settings.ai_extraction_mode == "responses" and settings.openai_api_key
            else None
        )

    @classmethod
    @asynccontextmanager
    async def open(cls, db, engine, settings):
        checkpoint_path = str(Path(db.engine.url.database).resolve()) + ".ai-checkpoints.sqlite"
        async with AsyncSqliteSaver.from_conn_string(checkpoint_path) as saver:
            await saver.setup()
            runtime = cls(db, engine, settings, saver)
            await runtime.prune_retained_data()
            try:
                yield runtime
            finally:
                if runtime.model_client:
                    await runtime.model_client.close()

    def maintenance(self):
        if time.monotonic() < self.next_maintenance:
            return
        self.next_maintenance = time.monotonic() + 1
        from app.models import now
        from app.services.bookings import emit
        from app.services.execution import finish_attempt

        current = now()
        with self.db.transaction(write=True) as session:
            if time.monotonic() >= self.next_trace_prune:
                prune(session, self.settings.ai_retention_days)
                self.next_trace_prune = time.monotonic() + 60
            session.execute(delete(AgentMemory).where(AgentMemory.expires_at <= current))
            for call, booking in session.execute(
                select(VoiceCallSession, BookingRequest)
                .join(AIExecution, VoiceCallSession.execution_id == AIExecution.id)
                .join(BookingRequest, AIExecution.booking_id == BookingRequest.id)
                .where(
                    BookingRequest.status == "WAITING_FOR_USER",
                    AIExecution.mode == "real_telephony",
                    VoiceCallSession.approval_deadline.is_not(None),
                    VoiceCallSession.approval_deadline <= current,
                )
            ):
                for offer in session.scalars(
                    select(ReservationOffer).where(ReservationOffer.attempt_id == call.attempt_id)
                ):
                    offer.approval_pending = False
                finish_attempt(session.get(CallAttempt, call.attempt_id), "TIMEOUT", "FAILED")
                booking.status, booking.finished_at, call.action = "FAILED", current, "STOP"
                emit(session, booking, "booking.failed")

    async def erase_checkpoints(self, execution_id):
        with self.db.transaction() as session:
            call_ids = list(
                session.scalars(
                    select(VoiceCallSession.id).where(VoiceCallSession.execution_id == execution_id)
                )
            )
        prefixes = tuple(f"voice:{identity}:" for identity in call_ids)
        threads = {execution_id}
        async for checkpoint in self.saver.alist(None):
            identity = checkpoint.config["configurable"]["thread_id"]
            if prefixes and identity.startswith(prefixes):
                threads.add(identity)
        for identity in threads:
            await self.saver.adelete_thread(identity)

    async def prune_retained_data(self):
        cutoff = (datetime.now(UTC) - timedelta(days=self.settings.ai_retention_days)).isoformat()
        with self.db.transaction() as session:
            expired = list(
                session.scalars(
                    select(AIExecution.id)
                    .join(BookingRequest)
                    .where(
                        AIExecution.created_at < cutoff,
                        BookingRequest.status.in_(["CONFIRMED", "EXHAUSTED", "CANCELLED", "FAILED"]),
                    )
                )
            )
        for execution_id in expired:
            with self.db.transaction() as session:
                unsafe = session.scalar(
                    select(VoiceCallSession.id).where(
                        VoiceCallSession.execution_id == execution_id,
                        VoiceCallSession.transport_state.in_(["ACTIVE", "DIALING", "UNCERTAIN"]),
                    )
                )
            if unsafe:
                continue
            await self.erase_checkpoints(execution_id)
            with self.db.transaction(write=True) as session:
                session.execute(delete(AgentTrace).where(AgentTrace.execution_id == execution_id))
                session.execute(delete(ToolOperation).where(ToolOperation.execution_id == execution_id))
                session.execute(delete(VoiceCallSession).where(VoiceCallSession.execution_id == execution_id))

    def execution(self, booking_id):
        with self.db.transaction() as session:
            return session.scalar(select(AIExecution).where(AIExecution.booking_id == booking_id))

    def has_execution(self, booking_id):
        return self.execution(booking_id) is not None

    def schedulable(self, booking_id):
        execution = self.execution(booking_id)
        return execution is None or not execution.paused

    def terminal_without_summary(self):
        with self.db.transaction() as session:
            return list(
                session.scalars(
                    select(AIExecution.booking_id)
                    .join(BookingRequest)
                    .where(
                        BookingRequest.status.in_(["CONFIRMED", "EXHAUSTED", "FAILED", "CANCELLED"]),
                        AIExecution.summary_text.is_(None),
                    )
                )
            )

    def provider_for(self, booking_id):
        execution = self.execution(booking_id)
        if execution.mode == "real_telephony":
            from app.voice.telephony import TwilioCallProvider

            return TwilioCallProvider(self.db, execution.id, self.settings)
        return AISimulationCallProvider(
            self.db,
            execution.id,
            self.settings.call_delay_seconds,
            self.settings,
            model_client=self.model_client,
        )

    def timeout_for(self, booking_id):
        execution = self.execution(booking_id)
        return (
            execution.authorization["max_duration_seconds"] + 10
            if execution.mode == "real_telephony"
            else self.engine.timeout
        )

    def tools(self, state, agent, *, advance=None):
        return AgentTools(self.db, ToolScope(state["execution_id"], state["booking_id"], agent), advance)

    def _build(self):
        graph = StateGraph(GraphState)
        for name, method in {
            "load": self.load,
            "planning": self.planning,
            "supervisor": self.supervisor,
            "research": self.research,
            "prepare_call": self.prepare_call,
            "voice_session": self.voice_session,
            "negotiation": self.negotiation,
            "verification": self.verification,
            "human_approval": self.human_approval,
            "pause": self.pause,
            "memory": self.memory,
            "evaluation": self.evaluation,
        }.items():
            graph.add_node(name, instrument_node(self.db, name, method, lambda: self.graph))
        graph.add_edge(START, "load")
        graph.add_edge("load", "planning")
        graph.add_edge("planning", "supervisor")
        graph.add_conditional_edges(
            "supervisor",
            lambda s: s["route"],
            {
                "call": "research",
                "approval": "human_approval",
                "pause": "pause",
                "finish": "memory",
            },
        )
        for a, b in [
            ("research", "prepare_call"),
            ("prepare_call", "voice_session"),
            ("voice_session", "negotiation"),
            ("negotiation", "verification"),
            ("verification", "supervisor"),
            ("human_approval", "supervisor"),
            ("pause", "supervisor"),
            ("memory", "evaluation"),
            ("evaluation", END),
        ]:
            graph.add_edge(a, b)
        return graph

    async def drive(self, booking_id):
        execution = self.execution(booking_id)
        lock = self.locks.setdefault(execution.id, asyncio.Lock())
        async with lock:
            config = {
                "configurable": {"thread_id": execution.id},
                "recursion_limit": self.settings.ai_max_steps,
            }
            with self.db.transaction() as session:
                terminal = require_booking(session, booking_id).status in {
                    "CONFIRMED",
                    "FAILED",
                    "EXHAUSTED",
                    "CANCELLED",
                }
            if terminal:
                snapshot = await self.graph.aget_state(config)
                if snapshot.values and snapshot.next:
                    await self.graph.aupdate_state(
                        config, {"route": "finish", "pending_user_approval": None}, as_node="supervisor"
                    )
                    with tracing_context(enabled=self.settings.langsmith_tracing_enabled):
                        await self._observed_invoke(None, config, execution)
                else:
                    await self.finalize(execution.id, booking_id)
                return
            snapshot = await self.graph.aget_state(config)
            if snapshot.next:
                # Resume values are only wake-up signals; human_approval reads the real business decision.
                value = Command(resume={"wake": True}) if any(t.interrupts for t in snapshot.tasks) else None
            elif snapshot.values:
                # A completed graph must never create new calls on retry.
                return
            else:
                value = {"booking_id": booking_id, "execution_id": execution.id, "steps": 0}
            with tracing_context(enabled=self.settings.langsmith_tracing_enabled):
                await self._observed_invoke(value, config, execution)

    async def _observed_invoke(self, value, config, execution):
        graph_version = register_graph(self.db, self.graph, "booking")
        with self.db.transaction(write=True) as session:
            run = ensure_execution(
                session, require_booking(session, execution.booking_id), settings=self.settings
            )
            run.graph_version = run.graph_version or graph_version
            run.graph_thread_id = execution.id
            run.configured_models = {
                "reasoning": self.settings.reasoning_model,
                "voice": self.settings.voice_model,
            }
        previous = await self.graph.aget_state(config)
        checkpoint = (previous.config or {}).get("configurable", {}).get("checkpoint_id")
        with (
            bind(
                execution_id=execution.id,
                graph_thread_id=execution.id,
                graph_version=graph_version,
                checkpoint_id=checkpoint,
                call_attempt_id=None,
            ),
            observed_span(self.db, execution.id, "graph.invocation"),
        ):
            result = await self.graph.ainvoke(value, config, durability="sync")
            snapshot = await self.graph.aget_state(config)
            checkpoint = (snapshot.config or {}).get("configurable", {}).get("checkpoint_id")
            record(
                self.db,
                execution.id,
                "graph.checkpoint",
                "observed",
                checkpoint_id=checkpoint,
                data={
                    "checkpoint_available": checkpoint is not None,
                    "pending_nodes": len(snapshot.next),
                },
            )
            return result

    async def load(self, state):
        with self.db.transaction() as session:
            require_booking(session, state["booking_id"])
        return {"error_state": None}

    async def planning(self, state):
        with span(self.db, state["execution_id"], "planning"):
            data = await self.tools(state, "planning").invoke("get_booking_requirements")
            config = BookingConfiguration.model_validate(data)
            plan = PlanningAgent().plan(config)
            # Store a concise plan, not phone numbers, whole request objects or conversation history.
            return {"booking_plan": plan.model_dump(mode="json")}

    async def supervisor(self, state):
        with span(self.db, state["execution_id"], "supervisor"):
            status = await self.tools(state, "supervisor").invoke("get_booking_status")
            execution = self.execution(state["booking_id"])
            if status["status"] in {"CONFIRMED", "EXHAUSTED", "FAILED", "CANCELLED"}:
                return {"route": "finish", "pending_user_approval": None}
            if status["status"] == "WAITING_FOR_USER":
                with self.db.transaction() as session:
                    offer_id = session.scalar(
                        select(ReservationOffer.id).where(
                            ReservationOffer.booking_id == state["booking_id"],
                            ReservationOffer.approval_pending.is_(True),
                        )
                    )
                return {"route": "approval", "pending_user_approval": offer_id}
            if execution.paused:
                return {"route": "pause"}
            target = await self.tools(state, "supervisor").invoke("get_next_restaurant")
            return {
                "route": "call",
                "active_restaurant_id": target["restaurant_id"],
                "active_call_attempt_id": target["attempt_id"],
                "pending_user_approval": None,
            }

    async def research(self, state):
        with span(self.db, state["execution_id"], "research"):
            if state.get("active_restaurant_id"):
                await self.tools(state, "research").invoke("get_restaurant_information")
                result = ResearchAgent(self.db).research(state["active_restaurant_id"])
                # No telephone or historical free text is copied into the checkpoint.
                return {
                    "call_context": {
                        "restaurant_id": result.restaurant_id,
                        "unknown_keys": [o.key for o in result.observations if o.category == "UNKNOWN"],
                    }
                }
            return {"call_context": {}}

    async def prepare_call(self, state):
        # The engine rechecks RUNNING status, order, active attempt and call authorization.
        return {"steps": state.get("steps", 0) + 1}

    async def voice_session(self, state):
        async def advance():
            await self.engine.step(state["booking_id"])

        identity = state.get("active_call_attempt_id") or state.get("active_restaurant_id") or "exhaust"
        phase = "resume" if state.get("active_call_attempt_id") else "contact"
        tools = self.tools(state, "supervisor", advance=advance)
        with span(self.db, state["execution_id"], "supervisor"):
            await tools.invoke(
                "persist_call_outcome", operation_id=f"{state['execution_id']}:{phase}:{identity}"
            )
        with self.db.transaction() as session:
            calls = attempts(session, state["booking_id"])
            return {"active_call_attempt_id": calls[-1].id if calls else None}

    async def negotiation(self, state):
        with (
            span(self.db, state["execution_id"], "negotiation") as observation,
            self.db.transaction() as session,
        ):
            offer = session.scalar(
                select(ReservationOffer).where(
                    ReservationOffer.attempt_id == state.get("active_call_attempt_id")
                )
            )
            config = BookingConfiguration.model_validate(
                require_booking(session, state["booking_id"]).configuration
            )
            if offer is None:
                return {"extracted_proposals": [], "negotiation_decision": None}
            decision = NegotiationAgent().evaluate(config, OfferDetails.model_validate(offer.details))
            observation.output = {"evaluation": decision.evaluation}
            return {
                "extracted_proposals": [offer.id],
                "negotiation_decision": decision.model_dump(mode="json"),
            }

    async def verification(self, state):
        with (
            span(self.db, state["execution_id"], "verification") as observation,
            self.db.transaction() as session,
        ):
            call = session.scalar(
                select(VoiceCallSession).where(
                    VoiceCallSession.attempt_id == state.get("active_call_attempt_id")
                )
            )
            if call is None or not call.evidence or not call.accepted_offer:
                return {"verification_result": None}
            config = BookingConfiguration.model_validate(
                require_booking(session, state["booking_id"]).configuration
            )
            approved = (
                session.scalar(
                    select(ReservationOffer.id).where(
                        ReservationOffer.attempt_id == call.attempt_id,
                        ReservationOffer.decision == "APPROVED",
                    )
                )
                is not None
            )
            result = VerificationAgent().verify(
                config,
                call.restaurant_id,
                call.attempt_id,
                OfferDetails.model_validate(call.accepted_offer),
                ReservationEvidence.model_validate(call.evidence),
                approved=approved,
            )
            observation.output = {"status": result.status, "count": len(result.reasons)}
            return {"verification_result": result.model_dump(mode="json")}

    async def human_approval(self, state):
        interrupt(
            {
                "type": "booking_approval",
                "booking_id": state["booking_id"],
                "offer_id": state.get("pending_user_approval"),
            }
        )
        return {}

    async def pause(self, state):
        interrupt({"type": "execution_paused", "booking_id": state["booking_id"]})
        return {}

    async def memory(self, state):
        with span(self.db, state["execution_id"], "memory"):
            text = MemorySummaryAgent(self.db, self.settings.ai_retention_days).summarize(state["booking_id"])
            with self.db.transaction(write=True) as session:
                session.get(AIExecution, state["execution_id"]).summary_text = text
        return {}

    async def evaluation(self, state):
        with span(self.db, state["execution_id"], "evaluation") as observation:
            report = EvaluationAgent().evaluate(self.db, state["booking_id"])
            from app.observability.recorder import tool_io

            observation.output = tool_io("evaluation", report.model_dump(mode="json"), output=True)
            with self.db.transaction(write=True) as session:
                execution = session.get(AIExecution, state["execution_id"])
                execution.quality_report = report.model_dump(mode="json")
                execution.active_agent = None
        return {}

    async def finalize(self, execution_id, booking_id):
        state = {"execution_id": execution_id, "booking_id": booking_id}
        await self.memory(state)
        await self.evaluation(state)
