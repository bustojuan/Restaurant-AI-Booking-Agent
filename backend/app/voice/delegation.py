from datetime import UTC, datetime, timedelta
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langsmith import tracing_context
from sqlalchemy import select

from app.ai.agents import NegotiationAgent, PlanningAgent, VerificationAgent
from app.ai.contracts import ExtractedConversation
from app.ai.extraction import ResponsesExtractor
from app.ai.models import AIExecution, VoiceCallSession
from app.ai.observability import span
from app.ai.prompts import prompt_bundle
from app.core.errors import DomainError
from app.models import ReservationOffer
from app.observability.graph import instrument_node
from app.observability.models import ObservedExecution
from app.observability.recorder import append, bind, ensure_execution, observed_span, record, register_graph
from app.repositories import require_booking
from app.schemas import BookingConfiguration, OfferDetails


class DelegationState(TypedDict, total=False):
    booking_id: str
    call_session_id: str | None
    extracted: dict
    route: str
    result: str
    session_scope: str
    revision: int


class VoiceDelegationService:
    """A short persistent graph per delegation. Audio never passes through a graph."""

    def __init__(self, db, settings, saver, *, extractor=None):
        self.db, self.settings, self.saver = db, settings, saver
        self.extractor = extractor
        self.revision_guards = {}
        graph = StateGraph(DelegationState)
        for name in ["route", "negotiate", "verify", "requirements", "decline"]:
            graph.add_node(
                name,
                instrument_node(
                    db,
                    name,
                    getattr(self, name),
                    lambda: self.graph,
                    agent={
                        "negotiate": "negotiation",
                        "verify": "verification",
                        "requirements": "planning",
                    }.get(name),
                ),
            )
        graph.add_node(
            "clarify",
            instrument_node(
                db,
                "clarify",
                lambda s: {
                    "result": "Faltan datos claros. Pregunta por fecha, hora, personas y condiciones; no aceptes todavía."
                },
                lambda: self.graph,
            ),
        )
        graph.add_edge(START, "route")
        graph.add_conditional_edges(
            "route",
            lambda s: s["route"],
            {k: k for k in ["negotiate", "verify", "requirements", "decline", "clarify"]},
        )
        for name in ["negotiate", "verify", "requirements", "decline", "clarify"]:
            graph.add_edge(name, END)
        self.graph = graph.compile(checkpointer=saver)

    def context(self, state):
        with self.db.transaction() as session:
            booking = require_booking(session, state["booking_id"])
            config = BookingConfiguration.model_validate(booking.configuration)
            call = (
                session.get(VoiceCallSession, state["call_session_id"])
                if state.get("call_session_id")
                else None
            )
            if call:
                execution = session.get(AIExecution, call.execution_id)
                if execution.booking_id != booking.id:
                    raise DomainError(
                        "call_scope_invalid", "Voice session does not belong to this booking", 403
                    )
            return config, call

    async def handle(
        self,
        text,
        delegation_id,
        revision,
        *,
        booking_id,
        call_session_id=None,
        sandbox_id=None,
        is_current=None,
    ):
        scope = call_session_id or sandbox_id
        if not scope:
            raise DomainError("voice_scope_required", "A scoped voice session is required", 403)
        _, call = self.context({"booking_id": booking_id, "call_session_id": call_session_id})
        execution_id = call.execution_id if call else sandbox_id
        with self.db.transaction(write=True) as session:
            ensure_execution(
                session,
                require_booking(session, booking_id),
                execution_id=execution_id,
                mode=None if call else "voice_sandbox",
                prompts=None if call else prompt_bundle(),
                settings=self.settings,
            )
        graph_version = register_graph(self.db, self.graph, "voice_delegation")
        with self.db.transaction(write=True) as session:
            run = session.get(ObservedExecution, execution_id)
            run.graph_version = run.graph_version or graph_version
        thread = f"voice:{scope}:{delegation_id}"
        with (
            bind(
                execution_id=execution_id,
                call_attempt_id=call.attempt_id if call else None,
                call_session_id=scope,
                graph_thread_id=thread,
                graph_version=graph_version,
                delegation_id=delegation_id,
            ),
            observed_span(self.db, execution_id, "delegation", agent="voice"),
        ):
            result = await self._handle(
                text,
                delegation_id,
                revision,
                booking_id=booking_id,
                call_session_id=call_session_id,
                sandbox_id=sandbox_id,
                is_current=is_current,
            )
            snapshot = await self.graph.aget_state({"configurable": {"thread_id": thread}})
            checkpoint = (snapshot.config or {}).get("configurable", {}).get("checkpoint_id")
            record(
                self.db,
                execution_id,
                "graph.checkpoint",
                checkpoint_id=checkpoint,
                data={"checkpoint_available": checkpoint is not None, "pending_nodes": len(snapshot.next)},
            )
            return result

    async def _handle(
        self,
        text,
        delegation_id,
        revision,
        *,
        booking_id,
        call_session_id=None,
        sandbox_id=None,
        is_current=None,
    ):
        scope = call_session_id or sandbox_id
        if not scope:
            raise DomainError("voice_scope_required", "A scoped voice session is required", 403)
        self.revision_guards[scope] = is_current or (lambda: True)
        thread = f"voice:{scope}:{delegation_id}"
        options = {"configurable": {"thread_id": thread}, "recursion_limit": 10}
        previous = await self.graph.aget_state(options)
        if previous.values.get("result"):
            return previous.values["result"]
        config, call = self.context({"booking_id": booking_id, "call_session_id": call_session_id})
        if call:
            with self.db.transaction() as session:
                prompts = session.get(AIExecution, call.execution_id).prompts
            restaurant_id, attempt_id = call.restaurant_id, call.attempt_id
        else:
            prompts = prompt_bundle()
            restaurant_id, attempt_id = "sandbox", "sandbox"
        if self.extractor is None:
            self.extractor = ResponsesExtractor(
                self.settings, db=self.db, execution_id=call.execution_id if call else None
            )
        extractor = self.extractor
        extracted = await extractor.extract(
            text,
            config,
            restaurant_id,
            attempt_id,
            prompt=prompts["negotiation"]["text"],
            evidence_kind="provider_transcript",
        )
        if not self.revision_guards[scope]():
            return "La información ha cambiado. Aclara las condiciones actuales antes de continuar."
        with tracing_context(enabled=self.settings.langsmith_tracing_enabled):
            previous = await self.graph.aget_state(options)
            if previous.values.get("result"):
                return previous.values["result"]

            async def run_graph():
                return await self.graph.ainvoke(
                    {
                        "booking_id": booking_id,
                        "call_session_id": call_session_id,
                        "session_scope": scope,
                        "revision": revision,
                        "extracted": extracted.model_dump(mode="json"),
                    },
                    options,
                    durability="sync",
                )

            if call:
                with span(self.db, call.execution_id, "voice", "client_delegation"):
                    result = await run_graph()
            else:
                result = await run_graph()
        return result["result"]

    async def aclose(self):
        if isinstance(self.extractor, ResponsesExtractor):
            await self.extractor.client.close()

    async def route(self, state):
        extraction = ExtractedConversation.model_validate(state["extracted"])
        mapping = {
            "proposal": "negotiate",
            "confirmation": "verify",
            "requirements": "requirements",
            "no_availability": "decline",
            "refuses_ai": "decline",
            "unclear": "clarify",
        }
        return {"route": mapping[extraction.intent]}

    async def requirements(self, state):
        config, _ = self.context(state)
        return {
            "result": PlanningAgent().plan(config).voice_briefing
            + " Los requisitos obligatorios deben preguntarse explícitamente; no están verificados por la ficha."
        }

    async def negotiate(self, state):
        if not self.revision_guards.get(state["session_scope"], lambda: False)():
            return {"result": "Ha habido una corrección. No aceptes la propuesta anterior."}
        config, call = self.context(state)
        extraction = ExtractedConversation.model_validate(state["extracted"])
        if extraction.offer is None:
            return {"result": "La propuesta está incompleta. Pide los datos que faltan."}
        if call and not extraction.financial_terms_quote:
            return {
                "result": "Pregunta por depósito, cargos y condiciones económicas. No aceptes hasta aclararlas explícitamente."
            }
        decision = NegotiationAgent().evaluate(config, extraction.offer)
        record(
            self.db,
            call.execution_id if call else state["session_scope"],
            "agent.decision",
            data={"output": {"evaluation": decision.evaluation}},
        )
        if call:
            with self.db.transaction(write=True) as session:
                current = session.get(VoiceCallSession, call.id)
                booking = require_booking(session, state["booking_id"])
                if current.transport_state != "ACTIVE" or booking.status not in {
                    "RUNNING",
                    "WAITING_FOR_USER",
                }:
                    return {
                        "result": "La ejecución se ha detenido. Finaliza la conversación sin aceptar una reserva."
                    }
                if decision.evaluation in {"ACCEPTABLE", "REQUIRES_USER_APPROVAL"}:
                    current.proposed_offer = extraction.offer.model_dump(mode="json")
                    if decision.evaluation == "REQUIRES_USER_APPROVAL" and current.approval_deadline is None:
                        current.approval_deadline = (
                            datetime.now(UTC) + timedelta(seconds=self.settings.approval_wait_seconds)
                        ).isoformat()
        suffix = (
            " Espera la autorización de aceptación del motor antes de comprometerte."
            if call
            else " Esto es una prueba; no se ha creado ninguna reserva."
        )
        return {"result": decision.spoken_response + suffix}

    async def verify(self, state):
        if not self.revision_guards.get(state["session_scope"], lambda: False)():
            return {"result": "La confirmación necesita revisarse con los datos corregidos."}
        config, call = self.context(state)
        extraction = ExtractedConversation.model_validate(state["extracted"])
        if extraction.evidence is None:
            return {"result": "Falta una confirmación explícita con todos los datos. Pide aclaración."}
        if call is None:
            return {"result": "Evidencia recibida en una prueba de voz. No se persiste ninguna reserva real."}
        with self.db.transaction(write=True) as session:
            current = session.get(VoiceCallSession, call.id)
            if current.accepted_offer is None:
                current.evidence = extraction.evidence.model_dump(mode="json")
                current.action = "RECONCILE"
                append(
                    session,
                    call.execution_id,
                    "backend.voice_action",
                    "committed",
                    call_attempt_id=call.attempt_id,
                    data={"backend_action": current.action},
                )
                return {
                    "result": "No había aceptación autorizada. Aclara que no debes comprometer la reserva y solicita revisión."
                }
            approved = (
                session.scalar(
                    select(ReservationOffer.id).where(
                        ReservationOffer.attempt_id == call.attempt_id,
                        ReservationOffer.decision == "APPROVED",
                    )
                )
                is not None
            )
            verified = VerificationAgent().verify(
                config,
                call.restaurant_id,
                call.attempt_id,
                OfferDetails.model_validate(current.accepted_offer),
                extraction.evidence,
                approved=approved,
            )
            current.evidence = extraction.evidence.model_dump(mode="json")
        record(
            self.db,
            call.execution_id,
            "agent.decision",
            data={"output": {"status": verified.status, "count": len(verified.reasons)}},
        )
        return {
            "result": "La evidencia coincide con lo autorizado. Agradece y despídete; el backend registrará el resultado."
            if verified.status == "CONFIRMED"
            else "La confirmación no está verificada. No anuncies una reserva conseguida; pide aclaración."
        }

    async def decline(self, state):
        _, call = self.context(state)
        extraction = ExtractedConversation.model_validate(state["extracted"])
        if call:
            with self.db.transaction(write=True) as session:
                current = session.get(VoiceCallSession, call.id)
                current.action = (
                    "RECONCILE"
                    if current.accepted_offer
                    else "DECLINED_AI"
                    if extraction.intent == "refuses_ai"
                    else "NO_AVAILABILITY"
                )
                append(
                    session,
                    call.execution_id,
                    "backend.voice_action",
                    "committed",
                    call_attempt_id=call.attempt_id,
                    data={"backend_action": current.action},
                )
        return {"result": "Respeta la negativa. Agradece el tiempo y termina educadamente sin insistir."}
