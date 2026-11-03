import asyncio
import secrets
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPAuthorizationCredentials

from app.api.dependencies import bearer
from app.core.errors import DomainError
from app.observability import queries
from app.observability.contracts import (
    GraphVersionOut,
    ObservationPage,
    ObservedExecutionOut,
    ObservedExecutionPage,
)
from app.observability.models import GraphVersion


def authorized(settings, token):
    expected = settings.admin_api_token
    return bool(
        expected
        and isinstance(token, str)
        and not secrets.compare_digest(
            expected.get_secret_value().encode(), settings.local_api_token.get_secret_value().encode()
        )
        and secrets.compare_digest(token.encode(), expected.get_secret_value().encode())
    )


def authenticate_admin(
    request: Request, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
):
    if request.app.state.settings.admin_api_token is None:
        raise DomainError("admin_not_configured", "Historical telemetry access is not configured", 503)
    if credentials is None or not authorized(request.app.state.settings, credentials.credentials):
        raise DomainError("unauthorized", "Valid administrator bearer token required", 401)


router = APIRouter(
    prefix="/api/admin/observability", tags=["Observability"], dependencies=[Depends(authenticate_admin)]
)
ws_router = APIRouter(prefix="/api/admin/observability")


@router.get("/executions", response_model=ObservedExecutionPage)
def executions(
    request: Request,
    booking_id: str | None = None,
    mode: Literal["simulation", "ai_simulation", "real_telephony", "voice_sandbox"] | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    with request.app.state.db.transaction() as session:
        return queries.executions(session, booking_id=booking_id, mode=mode, limit=limit, offset=offset)


@router.get("/executions/{execution_id}", response_model=ObservedExecutionOut)
def execution(request: Request, execution_id: str):
    with request.app.state.db.transaction() as session:
        return queries.execution_view(session, queries.require_execution(session, execution_id))


@router.get("/events", response_model=ObservationPage)
def events(
    request: Request,
    execution_id: str | None = None,
    call_attempt_id: str | None = None,
    after_event_id: int = Query(0, ge=0),
    until_event_id: int | None = Query(None, ge=0),
    limit: int = Query(100, ge=1, le=200),
):
    with request.app.state.db.transaction() as session:
        return queries.events(
            session,
            execution_id=execution_id,
            call_attempt_id=call_attempt_id,
            after_event_id=after_event_id,
            until_event_id=until_event_id,
            limit=limit,
        )


@router.get("/graphs/{graph_version}", response_model=GraphVersionOut)
def graph(request: Request, graph_version: str):
    with request.app.state.db.transaction() as session:
        row = session.get(GraphVersion, graph_version)
        if row is None:
            raise DomainError("not_found", "No recorded graph with this version", 404)
        return GraphVersionOut(**{field: getattr(row, field) for field in GraphVersionOut.model_fields})


@ws_router.websocket("/events/ws")
async def stream(websocket: WebSocket, execution_id: str | None = None, after_event_id: int = Query(0, ge=0)):
    settings = websocket.app.state.settings
    origin = websocket.headers.get("origin")
    if origin is not None and origin not in settings.cors_origins:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        auth = await asyncio.wait_for(websocket.receive_json(), timeout=5)
        if not isinstance(auth, dict) or not authorized(settings, auth.get("token")):
            await websocket.close(code=1008)
            return
        cursor = after_event_id

        def read_page(after):
            # A bounded SQLAlchemy pool can wait; never wait on the ASGI event loop.
            with websocket.app.state.db.transaction() as session:
                return queries.events(session, execution_id=execution_id, after_event_id=after)

        while True:
            page = await asyncio.to_thread(read_page, cursor)
            for event in page.items:
                await websocket.send_json(event.model_dump(mode="json"))
            cursor = page.next_after_event_id
            if page.has_more:
                continue
            try:
                message = await asyncio.wait_for(websocket.receive(), timeout=0.1)
                if message["type"] == "websocket.disconnect":
                    return
            except TimeoutError:
                continue
    except (WebSocketDisconnect, RuntimeError):
        return
    except (TimeoutError, ValueError, DomainError):
        await websocket.close(code=1008)
