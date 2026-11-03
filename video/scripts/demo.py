"""Isolated video archive. Uses the real app/engine; never reads a personal .env."""

import asyncio
import json
import os
import random
import secrets
import shutil
import sqlite3
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
HOME = ROOT / "video" / "private" / "demo"
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")
from app.ai.models import AIExecution
from app.core.config import Settings
from app.main import create_app
from app.migrate import upgrade
from fastapi.testclient import TestClient
from sqlalchemy import select


def owned():
    assert HOME.resolve() == (ROOT / "video/private/demo").resolve()
    assert (HOME / "owned.json").is_file(), "Not an owned video environment"
    config = json.loads((HOME / "owned.json").read_text())
    assert config.get("purpose") == "baria-video-only-v1", "Foreign ownership marker"
    return config


def settings():
    cfg = owned()
    return Settings(
        _env_file=None,
        database_url=f"sqlite:///{cfg.get('runtime_database', str(HOME / 'booking.db'))}",
        local_api_token=cfg["token"],
        admin_api_token=cfg["admin"],
        call_delay_seconds=0.25,
        ai_extraction_mode="deterministic",
        ai_retention_days=90,
        openai_api_key=None,
        twilio_account_sid=None,
        twilio_auth_token=None,
        real_telephony_enabled=False,
        voice_sandbox_enabled=False,
        langsmith_tracing_enabled=False,
    )


def request(client, method, path, payload=None, version=None, admin=False):
    cfg = owned()
    headers = {"Authorization": f"Bearer {cfg['admin' if admin else 'token']}"}
    if version is not None:
        headers["If-Match"] = str(version)
    r = client.request(method, path, json=payload, headers=headers)
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {path}: {r.status_code} {r.text[:700]}")
    return r.json()


def configuration(anchor):
    return {
        "customer_name": "Demo Guest",
        "contact_phone": "000000000",
        "requested_date": str(anchor + timedelta(days=14)),
        "preferred_time": "21:00:00",
        "adults": 4,
        "flexibility_minutes": 30,
        "table_type": "terrace",
        "table_type_mandatory": False,
        "dietary_requirements": [
            {"kind": "celiac", "code": "gluten", "mandatory": True}
        ],
        "notes": "Quiet area if available.",
    }


def configure_demo_storage():
    """WAL permits history readers alongside the real engine's periodic writer."""
    owned()
    with sqlite3.connect(
        Path(settings().database_url.removeprefix("sqlite:///")), timeout=30
    ) as connection:
        mode = connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]
        assert mode.lower() == "wal"


def schedule(anchor):
    rng = random.Random(20261102)
    triples = (
        [("priority-success", None)] * 66
        + [("all-full", None)] * 10
        + [("errors", None)] * 5
        + [("timeout", None)] * 5
        + [("ai-ambiguous", None)] * 3
    )
    singles = (
        [("confirm-first", None)] * 3
        + [("ai-valid-alternative", None)] * 10
        + [("approval", True)] * 10
        + [("approval", False)] * 5
        + [("ai-incomplete-confirmation", None)] * 2
    )
    rng.shuffle(triples)
    rng.shuffle(singles)
    regions = ["madrid"] * 59 + ["navarra"] * 60
    rng.shuffle(regions)
    # Chronological generation keeps research-memory causality intact.
    result = []
    quotas = [(10, 6), (13, 5), (15, 5), (15, 3), (17, 5), (19, 6)]
    for week, (nt, ns) in enumerate(quotas):
        chunk = [triples.pop() for _ in range(nt)] + [singles.pop() for _ in range(ns)]
        rng.shuffle(chunk)
        days = 7 if week < 5 else 6
        for j, (scenario, approval) in enumerate(chunk):
            day = anchor - timedelta(days=41) + timedelta(days=week * 7 + j % days)
            result.append(
                {
                    "scenario": scenario,
                    "approval": approval,
                    "region": regions.pop(),
                    "calls": 3
                    if scenario
                    in (
                        "priority-success",
                        "all-full",
                        "errors",
                        "timeout",
                        "ai-ambiguous",
                    )
                    else 1,
                    "slot": datetime.combine(
                        day, datetime.min.time(), ZoneInfo("Europe/Madrid")
                    )
                    + timedelta(hours=10 + j // days, minutes=rng.randrange(5, 50)),
                }
            )
    result.sort(key=lambda x: x["slot"])
    assert len(result) == 119 and sum(x["calls"] for x in result) == 297
    return result


def generate():
    assert not HOME.exists(), (
        "Environment exists; use explicit demo:reset before preparing a fresh archive"
    )
    HOME.mkdir(parents=True)
    anchor = datetime.now(ZoneInfo("Europe/Madrid")).date()
    (HOME / "owned.json").write_text(
        json.dumps(
            {
                "purpose": "baria-video-only-v1",
                "token": secrets.token_urlsafe(32),
                "admin": secrets.token_urlsafe(32),
                "anchor": str(anchor),
            }
        ),
        encoding="utf-8",
    )
    s = settings()
    upgrade(s.database_url)
    configure_demo_storage()
    app = create_app(s)
    manifest = []
    with TestClient(app) as client:
        # Public catalog snapshots only; never import personal booking records.
        from app.providers.overpass import OverpassRestaurantProvider
        from app.services.catalog import import_catalog

        snapshots = ROOT / "backend/data"
        if all(
            (snapshots / f"overpass-{r}.json").exists() for r in ["madrid", "navarra"]
        ):
            records = [
                record
                for region in ("Madrid", "Navarra")
                for record in OverpassRestaurantProvider(region, snapshots).records(
                    offline=True
                )
            ]
            import_catalog(app.state.db, records)
        for i, item in enumerate(schedule(anchor)):
            region = item["region"]
            ids = [f"{region}-{n}" for n in range(1, 6)]
            random.Random(20261102 + i).shuffle(ids)
            s.call_delay_seconds = [0.08, 0.16, 0.3, 0.45, 0.65][i % 5]
            b = request(
                client,
                "POST",
                "/api/bookings",
                {
                    "configuration": configuration(anchor),
                    "restaurant_ids": ids[: item["calls"]],
                },
            )
            request(
                client,
                "POST",
                f"/api/bookings/{b['id']}/start",
                {"mode": "ai_simulation", "scenario_id": item["scenario"]},
                b["version"],
            )
            deadline = time.monotonic() + 60
            while True:
                if time.monotonic() > deadline:
                    raise TimeoutError(f"Demo run {i} not finalized")
                b = request(client, "GET", f"/api/bookings/{b['id']}")
                if b["status"] == "WAITING_FOR_USER":
                    offers = request(client, "GET", f"/api/bookings/{b['id']}/offers")
                    pending = next((o for o in offers if o["approval_pending"]), None)
                    if pending:
                        request(
                            client,
                            "POST",
                            f"/api/bookings/{b['id']}/decisions",
                            {"offer_id": pending["id"], "approve": item["approval"]},
                            b["version"],
                        )
                if b["status"] in ("CONFIRMED", "EXHAUSTED", "FAILED", "CANCELLED"):
                    with app.state.db.transaction() as session:
                        ai = session.scalar(
                            select(AIExecution).where(AIExecution.booking_id == b["id"])
                        )
                        if ai and ai.quality_report is not None:
                            item.update(
                                booking_id=b["id"],
                                execution_id=ai.id,
                                original_start=ai.created_at,
                                slot=item["slot"].isoformat(),
                            )
                            manifest.append(item)
                            break
                time.sleep(0.08)
            if i % 10 == 0:
                print(f"Generated {i + 1}/119 bookings", flush=True)
    archive(manifest)
    (HOME / "manifest.json").write_text(
        json.dumps(
            {"seed": 20261102, "anchor": str(anchor), "runs": manifest}, indent=2
        ),
        encoding="utf-8",
    )
    validate_db(expected_calls=297)
    shutil.copy2(HOME / "booking.db", HOME / "baseline.db")
    print("READY: 119 bookings / 297 calls / 89 simulated confirmations", flush=True)


def archive(manifest):
    """Uniform translation per newly generated run; no events/decisions are invented."""
    db = sqlite3.connect(HOME / "booking.db")
    db.row_factory = sqlite3.Row
    fields = {
        "booking_requests": ["created_at", "updated_at", "started_at", "finished_at"],
        "call_attempts": ["started_at", "completed_at"],
        "reservation_confirmations": ["confirmed_at"],
        "booking_events": ["timestamp"],
        "ai_executions": ["created_at"],
        "agent_traces": ["created_at"],
        "agent_tool_operations": ["created_at"],
        "voice_call_sessions": [
            "created_at",
            "ended_at",
            "deadline",
            "approval_deadline",
        ],
        "observed_executions": [
            "started_at",
            "instrumentation_started_at",
            "ended_at",
            "events_pruned_at",
        ],
        "observation_events": ["occurred_at", "received_at"],
    }
    json_fields = {
        "booking_events": ["payload"],
        "agent_traces": ["details"],
        "agent_tool_operations": ["result"],
        "voice_call_sessions": ["proposed_offer", "accepted_offer", "evidence"],
        "observation_events": ["data"],
    }
    updates = []
    known = {}
    for item in manifest:
        delta = datetime.fromisoformat(item["slot"]).astimezone(
            UTC
        ) - datetime.fromisoformat(item["original_start"])
        item["archive_delta_seconds"] = delta.total_seconds()
        for table, columns in fields.items():
            if table == "booking_requests":
                where, value = "id", item["booking_id"]
            elif table == "ai_executions":
                where, value = "id", item["execution_id"]
            elif table in (
                "agent_traces",
                "agent_tool_operations",
                "voice_call_sessions",
            ):
                where, value = "execution_id", item["execution_id"]
            else:
                where, value = "booking_id", item["booking_id"]
            rows = db.execute(
                f"SELECT rowid as _rowid_, * FROM {table} WHERE {where}=?", (value,)
            ).fetchall()
            for row in rows:
                values = {}
                for col in columns:
                    if row[col]:
                        translated = (
                            datetime.fromisoformat(row[col]) + delta
                        ).isoformat()
                        known[row[col]] = translated
                        values[col] = translated
                updates.append((table, row, values, delta))

    def embedded(value, delta, key=""):
        if isinstance(value, dict):
            return {k: embedded(v, delta, k) for k, v in value.items()}
        if isinstance(value, list):
            return [embedded(v, delta, key) for v in value]
        if isinstance(value, str) and (
            key.endswith("_at") or key in ("timestamp", "deadline", "approval_deadline")
        ):
            if value in known:
                return known[value]
            try:
                parsed = datetime.fromisoformat(value)
                if parsed.tzinfo:
                    return (parsed + delta).isoformat()
            except ValueError:
                pass
        return value

    with db:
        for table, row, values, delta in updates:
            for col in json_fields.get(table, []):
                if row[col]:
                    values[col] = json.dumps(
                        embedded(json.loads(row[col]), delta), ensure_ascii=False
                    )
            if values:
                db.execute(
                    f"UPDATE {table} SET "
                    + ",".join(f"{k}=?" for k in values)
                    + " WHERE rowid=?",
                    (*values.values(), row["_rowid_"]),
                )
        # Restaurant memories refer to the last actual generated contact for that restaurant.
        for row in db.execute(
            "SELECT rowid as _rowid_,* FROM agent_memories"
        ).fetchall():
            owner = db.execute(
                "SELECT a.execution_id FROM voice_call_sessions a WHERE a.restaurant_id=? ORDER BY a.created_at DESC LIMIT 1",
                (row["owner_id"],),
            ).fetchone()
            item = next(
                (r for r in manifest if owner and r["execution_id"] == owner[0]), None
            )
            if item:
                delta = timedelta(seconds=item["archive_delta_seconds"])
                db.execute(
                    "UPDATE agent_memories SET created_at=?,expires_at=?,value=? WHERE rowid=?",
                    (
                        (datetime.fromisoformat(row["created_at"]) + delta).isoformat(),
                        (datetime.fromisoformat(row["expires_at"]) + delta).isoformat(),
                        json.dumps(embedded(json.loads(row["value"]), delta)),
                        row["_rowid_"],
                    ),
                )
        first = min(r["slot"] for r in manifest)
        db.execute("UPDATE observation_graph_versions SET created_at=?", (first,))
    assert not db.execute("PRAGMA foreign_key_check").fetchall()
    db.close()

    # Terminal archived threads must not restart; delete via the saver API, not blob editing.
    async def clear():
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        async with AsyncSqliteSaver.from_conn_string(
            str(HOME / "booking.db") + ".ai-checkpoints.sqlite"
        ) as saver:
            for item in manifest:
                await saver.adelete_thread(item["execution_id"])

    asyncio.run(clear())


def validate_db(expected_calls=None):
    owned()
    db = sqlite3.connect(HOME / "booking.db")
    counts = {
        t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        for t in [
            "booking_requests",
            "call_attempts",
            "reservation_confirmations",
            "observation_events",
            "observed_executions",
        ]
    }
    assert not db.execute("PRAGMA foreign_key_check").fetchall()
    assert (
        db.execute(
            "SELECT COUNT(*) FROM booking_requests WHERE status IN ('RUNNING','WAITING_FOR_USER')"
        ).fetchone()[0]
        == 0
    )
    assert (
        db.execute(
            "SELECT COUNT(*) FROM reservation_confirmations WHERE simulated!=1"
        ).fetchone()[0]
        == 0
    )
    assert (
        db.execute(
            "SELECT COUNT(*) FROM observation_events WHERE kind IN ('model','delegation')"
        ).fetchone()[0]
        == 0
    )
    assert (
        db.execute(
            "SELECT COUNT(*) FROM call_attempts a JOIN reservation_confirmations c ON a.booking_id=c.booking_id WHERE a.started_at>c.confirmed_at"
        ).fetchone()[0]
        == 0
    )
    if expected_calls is not None:
        assert counts["call_attempts"] == expected_calls, counts
    report = {
        "counts": counts,
        "results": dict(
            db.execute("SELECT result,COUNT(*) FROM call_attempts GROUP BY result")
        ),
        "booking_statuses": dict(
            db.execute("SELECT status,COUNT(*) FROM booking_requests GROUP BY status")
        ),
        "days": db.execute(
            "SELECT COUNT(DISTINCT substr(started_at,1,10)) FROM call_attempts"
        ).fetchone()[0],
        "foreign_keys": "pass",
        "simulated_only": True,
        "external_provider_requests": 0,
    }
    (HOME / "reconciliation.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    db.close()
    return report


def configure_capture_pool(engine):
    """Keep the app's SQLite hooks when changing the demo connection policy."""
    from sqlalchemy.pool import NullPool

    original_pool = engine.pool
    creator = original_pool._creator
    engine.dispose()
    engine.pool = NullPool(
        creator=creator, dialect=engine.dialect, _dispatch=original_pool.dispatch
    )


def serve():
    import tempfile

    import uvicorn

    config = owned()
    if not config.get("runtime_database"):
        working = Path(tempfile.mkdtemp(prefix="baria-video-v1-"))
        database = working / "booking.db"
        with (
            sqlite3.connect(HOME / "booking.db") as source,
            sqlite3.connect(database) as target,
        ):
            source.backup(target)
        config["runtime_database"] = str(database)
        (HOME / "owned.json").write_text(json.dumps(config), encoding="utf-8")
    upgrade(settings().database_url)
    configure_demo_storage()
    if os.environ.get("BARIA_VIDEO_DIAGNOSTICS"):
        import faulthandler

        diagnostic = (HOME / "server-threads.log").open("w")
        faulthandler.dump_traceback_later(30, repeat=True, file=diagnostic)
    # The demo's many historical readers must not block the synchronous event-loop
    # maintenance task waiting for the default bounded QueuePool. This is a local
    # database connection policy, not a change to engine/agent business behavior.
    app = create_app(settings())
    configure_capture_pool(app.state.db.engine)
    try:
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=18011,
            access_log=False,
            http="h11",
            timeout_keep_alive=0,
        )
    finally:
        snapshot()


def snapshot():
    config = owned()
    runtime = config.get("runtime_database")
    if runtime:
        with (
            sqlite3.connect(runtime, timeout=30) as source,
            sqlite3.connect(HOME / "booking.db", timeout=30) as target,
        ):
            source.backup(target)
        checkpoint = Path(runtime + ".ai-checkpoints.sqlite")
        if checkpoint.exists():
            with (
                sqlite3.connect(checkpoint, timeout=30) as source,
                sqlite3.connect(
                    HOME / "booking.db.ai-checkpoints.sqlite", timeout=30
                ) as target,
            ):
                source.backup(target)
        print(
            "Demo working database and checkpoints snapshotted to the private production archive",
            flush=True,
        )


def reset():
    owned()
    import socket

    with socket.socket() as sock:
        assert sock.connect_ex(("127.0.0.1", 18011)) != 0, (
            "Stop the demo server before reset"
        )
    # Keep old takes intact rather than recursively deleting a computed path.
    destination = HOME.with_name(
        "demo-retired-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    )
    HOME.rename(destination)
    print("Retired demo to " + str(destination))


def restore():
    config = owned()
    import socket

    with socket.socket() as sock:
        assert sock.connect_ex(("127.0.0.1", 18011)) != 0, (
            "Stop the demo server and Electron before restore"
        )
    assert (HOME / "baseline.db").is_file(), "No sealed baseline"
    destination = HOME / "retakes" / datetime.now().strftime("%Y%m%d-%H%M%S")
    destination.mkdir(parents=True)
    for name in [
        "booking.db",
        "booking.db-wal",
        "booking.db-shm",
        "booking.db.ai-checkpoints.sqlite",
        "booking.db.ai-checkpoints.sqlite-wal",
        "booking.db.ai-checkpoints.sqlite-shm",
        "hero.json",
        "bookmarks.json",
        "analytics-300.json",
        "lab.json",
    ]:
        source = HOME / name
        assert source.resolve().parent == HOME.resolve()
        if source.exists():
            source.rename(destination / name)
    shutil.copy2(HOME / "baseline.db", HOME / "booking.db")
    config.pop("runtime_database", None)
    (HOME / "owned.json").write_text(json.dumps(config), encoding="utf-8")
    validate_db(297)
    print("Closed-process baseline restored; old take retained in " + str(destination))


if __name__ == "__main__":
    command = sys.argv[1]
    {
        "prepare": generate,
        "serve": serve,
        "reset": reset,
        "restore": restore,
        "validate": validate_db,
        "snapshot": snapshot,
    }[command]()
