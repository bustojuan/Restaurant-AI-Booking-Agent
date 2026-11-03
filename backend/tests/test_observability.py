import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest
from conftest import TOKEN, configuration, make_booking, start_booking, versioned, wait_for
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from starlette.websockets import WebSocketDisconnect
from test_ai_integration import start_ai, wait_ai
from test_voice_protocol import FakeConnector, FakeLiveSocket

from app.main import create_app
from app.observability.models import ObservationEvent, ObservedExecution
from app.observability.recorder import (
    bind,
    ensure_execution,
    observed_span,
    prune,
    record,
    safe_data,
    tool_io,
    usage_projection,
)
from app.repositories import require_booking
from app.voice.live import LiveSession

ADMIN = "admin-observability-only-test-token-1234"
ROOT = "/api/admin/observability"


def admin(client, path):
    return client.get(ROOT + path, headers={"Authorization": f"Bearer {ADMIN}"})


def all_events(client, identity):
    cursor, high, items = 0, None, []
    while True:
        params = f"/events?execution_id={identity}&limit=17&after_event_id={cursor}"
        if high is not None:
            params += f"&until_event_id={high}"
        response = admin(client, params)
        assert response.status_code == 200, response.text
        page = response.json()
        high = page["high_watermark"]
        items.extend(page["items"])
        cursor = page["next_after_event_id"]
        if not page["has_more"]:
            return items


def test_history_correlates_agents_calls_tools_graph_and_redacts_content(client, settings):
    settings.admin_api_token = SecretStr(ADMIN)
    config = {
        **configuration(),
        "customer_name": "PRIVATE_CUSTOMER_MARKER",
        "notes": "PRIVATE_NOTES_MARKER",
        "dietary_requirements": [{"kind": "allergy", "code": "PRIVATE_DIET_MARKER", "mandatory": False}],
    }
    booking = make_booking(client, ids=["madrid-1", "madrid-2", "madrid-3"], config=config)
    start_ai(client, booking)
    wait_for(client, booking["id"], {"CONFIRMED"})
    ai = wait_ai(client, booking["id"])
    # The drive may still be committing its final graph/checkpoint event.
    import time

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        view = admin(client, f"/executions/{ai['id']}").json()
        if not view["open_span_ids"]:
            break
        time.sleep(0.02)
    events = all_events(client, ai["id"])
    assert len(events) > 40
    assert [e["id"] for e in events] == sorted({e["id"] for e in events})
    assert all(e["booking_id"] == booking["id"] for e in events)
    starts = {e["span_id"]: e for e in events if e["phase"] == "started"}
    ends = [e for e in events if e["phase"] == "completed"]
    assert starts and ends
    for end in ends:
        assert end["span_id"] in starts
        assert end["elapsed_ms"] >= 0
        assert end["occurred_at"] >= starts[end["span_id"]]["occurred_at"]
    tools = [e for e in events if e["kind"] == "tool"]
    assert tools and all(e["tool_call_id"] == e["span_id"] for e in tools)
    assert any(e["agent_run_id"] and e["parent_span_id"] for e in tools)
    assert {
        "planning",
        "research",
        "supervisor",
        "voice",
        "negotiation",
        "verification",
        "memory",
        "evaluation",
    } <= {e["agent"] for e in events if e["kind"] == "agent"}
    assert any(e["node"] == "planning" for e in events if e["kind"] == "graph.node")
    graph = admin(client, f"/graphs/{view['graph_version']}").json()
    assert "voice_session" in {n["id"] for n in graph["definition"]["nodes"]}
    assert any(
        e["kind"] == "graph.transition"
        and e["data"].get("from_node") == "supervisor"
        and e["data"].get("to_node") == "research"
        for e in events
    )
    assert any(e["checkpoint_id"] and e["graph_thread_id"] == ai["id"] for e in events)
    calls = client.get(f"/api/bookings/{booking['id']}").json()["summary"]["contacted_restaurants"]
    assert {call["id"] for call in calls} <= {e["call_attempt_id"] for e in events}
    assert any(e["data"].get("confirmation_id") for e in events)
    assert any(e["prompt_sha256"] and e["prompt_version"] for e in events)
    serialized = json.dumps(events)
    for secret in [
        "PRIVATE_CUSTOMER_MARKER",
        "PRIVATE_NOTES_MARKER",
        "PRIVATE_DIET_MARKER",
        config["contact_phone"],
        TOKEN,
        ADMIN,
    ]:
        assert secret not in serialized
    before = [e["event_id"] for e in events]

    # Read-only replay never invokes the graph, tools, provider or model.
    async def forbidden(*args, **kwargs):
        pytest.fail("Replay tried to execute work")

    original = client.app.state.ai.graph.ainvoke
    client.app.state.ai.graph.ainvoke = forbidden
    try:
        assert [e["event_id"] for e in all_events(client, ai["id"])] == before
    finally:
        client.app.state.ai.graph.ainvoke = original
    persisted = client.get(f"/api/bookings/{booking['id']}").json()
    erased = versioned(client, "DELETE", f"/api/bookings/{booking['id']}/ai/data", persisted["version"])
    assert erased.status_code == 204
    assert admin(client, f"/executions/{ai['id']}").status_code == 404
    assert client.get(f"/api/bookings/{booking['id']}").json()["summary"]["confirmation"]


def test_classic_simulation_and_unknown_history_are_not_fake_ai(client, settings):
    settings.admin_api_token = SecretStr(ADMIN)
    draft = make_booking(client, ids=["madrid-1"])
    assert admin(client, f"/executions?booking_id={draft['id']}").json()["total"] == 0
    assert admin(client, f"/executions/{draft['id']}").status_code == 404
    start_booking(client, draft)
    wait_for(client, draft["id"], {"EXHAUSTED", "CONFIRMED"})
    run = admin(client, f"/executions/{draft['id']}").json()
    assert run["mode"] == "simulation"
    assert run["graph_version"] is None and run["ai_execution_id"] is None
    events = all_events(client, draft["id"])
    assert events and all(e["kind"].startswith("backend.") for e in events)
    assert all(e["model"] is None for e in events)
    assert all(
        e["call_attempt_id"] is None
        for e in events
        if e["kind"] in {"backend.booking.started", "backend.booking.exhausted"}
    )


def test_replay_after_process_restart_does_not_contact_or_run_graph(settings, monkeypatch):
    from app.ai.runtime import AIRuntime
    from app.migrate import upgrade
    from app.providers.calls import MockCallProvider

    settings.admin_api_token = SecretStr(ADMIN)
    upgrade(settings.database_url)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    with TestClient(create_app(settings), headers=headers) as first:
        booking = make_booking(first, ids=["madrid-1"])
        start_booking(first, booking)
        wait_for(first, booking["id"], {"EXHAUSTED", "CONFIRMED"})
        original = [e["event_id"] for e in all_events(first, booking["id"])]

    async def forbidden(*args, **kwargs):
        pytest.fail("Historical replay started external work")

    monkeypatch.setattr(MockCallProvider, "contact", forbidden)
    monkeypatch.setattr(AIRuntime, "drive", forbidden)
    with TestClient(create_app(settings), headers=headers) as second:
        assert [e["event_id"] for e in all_events(second, booking["id"])] == original


def test_admin_scope_and_websocket_replay(client, settings):
    booking = make_booking(client, ids=["madrid-1"])
    assert client.get(ROOT + "/events").status_code == 503
    settings.admin_api_token = SecretStr(ADMIN)
    assert client.get(ROOT + "/events").status_code == 401
    assert client.get(ROOT + "/events", headers={"Authorization": "Bearer wrong"}).status_code == 401
    start_booking(client, booking)
    wait_for(client, booking["id"], {"EXHAUSTED", "CONFIRMED"})
    expected = all_events(client, booking["id"])
    with client.websocket_connect(ROOT + "/events/ws") as ws:
        ws.send_json({"token": TOKEN})
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    cursor = expected[0]["id"]
    with client.websocket_connect(
        ROOT + f"/events/ws?execution_id={booking['id']}&after_event_id={cursor}"
    ) as ws:
        ws.send_json({"token": ADMIN})
        assert ws.receive_json()["event_id"] == expected[1]["event_id"]
    assert admin(client, "/events?limit=201").status_code == 422
    assert admin(client, "/events?after_event_id=-1").status_code == 422


def test_failure_cancelled_and_interrupted_spans_keep_parentage_without_error_text(client):
    from langgraph.errors import GraphInterrupt

    db = client.app.state.db
    booking = make_booking(client)
    with db.transaction(write=True) as session:
        ensure_execution(
            session,
            require_booking(session, booking["id"]),
            execution_id="sandbox-errors",
            mode="voice_sandbox",
        )
    for exception in [RuntimeError("PRIVATE_ERROR_SECRET"), asyncio.CancelledError(), GraphInterrupt(())]:
        with (
            pytest.raises(type(exception)),
            observed_span(db, "sandbox-errors", "agent", agent="voice"),
            observed_span(db, "sandbox-errors", "tool", tool="test_tool"),
        ):
            raise exception
    with db.transaction() as session:
        events = session.scalars(
            select(ObservationEvent).where(ObservationEvent.execution_id == "sandbox-errors")
        ).all()
        assert {"failed", "cancelled", "interrupted"} <= {e.phase for e in events}
        assert "PRIVATE_ERROR_SECRET" not in json.dumps([e.data for e in events])
        assert all(e.parent_span_id for e in events if e.kind == "tool")


def test_projection_does_not_copy_tool_or_provider_contents():
    source = {
        "customer_name": "PRIVATE",
        "contact_phone": "+34911111111",
        "dietary_requirements": ["PRIVATE_DIET"],
        "offer": {"reference": "PRIVATE"},
        "status": "RUNNING",
    }
    assert "PRIVATE" not in json.dumps(tool_io("get_booking_requirements", source, output=True))
    assert safe_data(
        {"usage": {"input_tokens": 10, "secret": "PRIVATE"}, "transcript": "PRIVATE", "audio": "PRIVATE"}
    )["usage"] == {"input_tokens": 10}
    assert usage_projection(
        {
            "input_tokens": 3,
            "secret": "PRIVATE",
            "input_token_details": {"audio_tokens": 2, "secret": "PRIVATE"},
        }
    ) == {"input_tokens": 3, "input_audio_tokens": 2}
    assert safe_data({"provider_end_ms": float("nan")}).get("provider_end_ms") is None


def test_frozen_replay_cutoff_does_not_include_new_live_events(client, settings):
    settings.admin_api_token = SecretStr(ADMIN)
    db = client.app.state.db
    booking = make_booking(client)
    with db.transaction(write=True) as session:
        ensure_execution(
            session, require_booking(session, booking["id"]), execution_id="cursor-test", mode="voice_sandbox"
        )
    initial = [record(db, "cursor-test", "test.event") for _ in range(3)]
    first = admin(client, "/events?execution_id=cursor-test&limit=1").json()
    added = record(db, "cursor-test", "test.event")
    rest = admin(
        client,
        f"/events?execution_id=cursor-test&after_event_id={first['next_after_event_id']}&until_event_id={first['high_watermark']}",
    ).json()
    assert [e["id"] for e in first["items"] + rest["items"]] == [e.id for e in initial]
    assert added.id > first["high_watermark"]
    assert not rest["has_more"]


def test_concurrent_invocations_keep_separate_context_and_parent_spans(client):
    db = client.app.state.db
    booking = make_booking(client)
    with db.transaction(write=True) as session:
        for identity in ["concurrent-a", "concurrent-b"]:
            ensure_execution(
                session, require_booking(session, booking["id"]), execution_id=identity, mode="voice_sandbox"
            )

    async def work(identity):
        with observed_span(db, identity, "agent", agent="voice"):
            await asyncio.sleep(0)
            with observed_span(db, identity, "tool", agent="voice", tool="concurrent_test"):
                await asyncio.sleep(0)

    async def run():
        await asyncio.gather(work("concurrent-a"), work("concurrent-b"))

    asyncio.run(run())
    with db.transaction() as session:
        events = session.scalars(
            select(ObservationEvent).where(
                ObservationEvent.execution_id.in_(["concurrent-a", "concurrent-b"])
            )
        ).all()
        parents = {e.span_id: e.execution_id for e in events if e.kind == "agent"}
        assert all(parents[e.parent_span_id] == e.execution_id for e in events if e.kind == "tool")


def test_backend_decision_and_graph_interrupt_are_correlated(client, settings):
    import time

    settings.admin_api_token = SecretStr(ADMIN)
    booking = make_booking(client, ids=["madrid-1", "madrid-2"])
    start_ai(client, booking, "approval")
    waiting = wait_for(client, booking["id"], {"WAITING_FOR_USER"})
    execution = client.get(f"/api/bookings/{booking['id']}/ai").json()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        captured = all_events(client, execution["id"])
        if any(e["phase"] == "interrupted" and e["node"] == "human_approval" for e in captured):
            break
        time.sleep(0.02)
    else:
        pytest.fail("No graph interruption was recorded")
    waiting = client.get(f"/api/bookings/{booking['id']}").json()
    offer = waiting["summary"]["pending_approvals"][0]
    response = versioned(
        client,
        "POST",
        f"/api/bookings/{booking['id']}/decisions",
        waiting["version"],
        {"offer_id": offer["id"], "approve": True},
    )
    assert response.status_code == 200
    wait_for(client, booking["id"], {"CONFIRMED"})
    wait_ai(client, booking["id"])
    captured = all_events(client, execution["id"])
    decision = next(e for e in captured if e["kind"] == "backend.user.decision_received")
    assert decision["data"]["decision"] == "APPROVED" and decision["data"]["offer_id"] == offer["id"]
    assert decision["call_attempt_id"] == offer["attempt_id"]


def test_voice_metadata_is_persistent_without_audio_or_transcript(client, settings):
    db = client.app.state.db
    booking = make_booking(client)
    with db.transaction(write=True) as session:
        ensure_execution(
            session,
            require_booking(session, booking["id"]),
            execution_id="sandbox-live",
            mode="voice_sandbox",
        )
    settings.openai_api_key = SecretStr("fake-key-not-used-for-network")
    socket = FakeLiveSocket()

    async def run():
        live = LiveSession(
            settings,
            "PRIVATE_SYSTEM_INSTRUCTIONS",
            connector=FakeConnector(socket),
            observer=lambda kind, phase, **values: record(db, "sandbox-live", kind, phase, **values),
        )

        async def frames():
            while not live.closed.is_set():
                yield b"\0\0" * 480
                await asyncio.sleep(0.01)

        async def output(raw):
            pass

        async def delegate(text, identity, revision):
            return "PRIVATE_DELEGATION_RESPONSE"

        with (
            bind(execution_id="sandbox-live"),
            observed_span(
                db, "sandbox-live", "voice.session", agent="voice", model=settings.voice_model
            ) as span,
        ):
            span.usage = await live.run(frames(), output, delegate, greeting="PRIVATE_GREETING")

    asyncio.run(run())
    with db.transaction() as session:
        rows = session.scalars(
            select(ObservationEvent).where(ObservationEvent.execution_id == "sandbox-live")
        ).all()
        serialized = json.dumps([r.data for r in rows])
        for private in [
            "Hay mesa para cuatro",
            "PRIVATE_SYSTEM_INSTRUCTIONS",
            "PRIVATE_GREETING",
            "PRIVATE_DELEGATION_RESPONSE",
            "private-provider-detail",
        ]:
            assert private not in serialized
        assert any(r.kind == "voice.turn" and r.data.get("provisional") is True for r in rows)
        assert any(r.external_session_id == "live-test" for r in rows)
        assert any(r.delegation_id == "deleg-1" for r in rows)
        assert any(r.kind == "voice.audio" and r.phase == "first_output" for r in rows)
        assert any(r.data.get("usage", {}).get("duration_seconds") == 1 for r in rows)


def test_retention_leaves_tombstone_and_event_cursors_are_never_reused(client):
    db = client.app.state.db
    booking = make_booking(client)
    with db.transaction(write=True) as session:
        run = ensure_execution(
            session, require_booking(session, booking["id"]), execution_id="expired", mode="voice_sandbox"
        )
        run.ended_at = (datetime.now(UTC) - timedelta(days=31)).isoformat()
    first = record(db, "expired", "test.event")
    with db.transaction(write=True) as session:
        prune(session, 30)
        assert session.get(ObservedExecution, "expired").events_pruned_at
        assert not list(
            session.scalars(select(ObservationEvent).where(ObservationEvent.execution_id == "expired"))
        )
        ensure_execution(
            session, require_booking(session, booking["id"]), execution_id="new-session", mode="voice_sandbox"
        )
    next_event = record(db, "new-session", "test.event")
    assert next_event.id > first.id
    with db.transaction(write=True) as session:
        orphan = ensure_execution(
            session,
            require_booking(session, booking["id"]),
            execution_id="orphaned-sandbox",
            mode="voice_sandbox",
        )
        orphan.started_at = (datetime.now(UTC) - timedelta(days=31)).isoformat()
    record(db, "orphaned-sandbox", "test.event")
    with db.transaction(write=True) as session:
        prune(session, 30)
        assert session.get(ObservedExecution, "orphaned-sandbox").events_pruned_at


def test_telemetry_write_failure_does_not_mask_work_and_reports_gap(client, monkeypatch):
    db = client.app.state.db
    booking = make_booking(client)
    with db.transaction(write=True) as session:
        ensure_execution(
            session,
            require_booking(session, booking["id"]),
            execution_id="write-failure",
            mode="voice_sandbox",
        )
    original = db.transaction

    def unavailable(**kwargs):
        raise OperationalError("PRIVATE_SQL", {}, Exception("PRIVATE_DB_MESSAGE"))

    with monkeypatch.context() as patch:
        patch.setattr(db, "transaction", unavailable)
        assert record(db, "write-failure", "test.event") is None
    assert db.transaction == original
    record(db, "write-failure", "test.event")
    with db.transaction() as session:
        assert session.get(ObservedExecution, "write-failure").dropped_events == 1
        gap = session.scalar(
            select(ObservationEvent).where(
                ObservationEvent.execution_id == "write-failure", ObservationEvent.kind == "telemetry.gap"
            )
        )
        assert gap.data["suppressed_events"] == 1
