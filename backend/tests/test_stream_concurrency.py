from concurrent.futures import ThreadPoolExecutor
from threading import Event

from pydantic import SecretStr
from sqlalchemy import text

from app.db.session import Database
from app.observability import queries


def test_waiting_observation_read_does_not_block_the_api(client, settings, monkeypatch):
    """A slow/pool-blocked WS read must leave the ASGI loop available to HTTP."""
    token = "isolated-admin-concurrency-test-token"
    settings.admin_api_token = SecretStr(token)
    entered, release = Event(), Event()
    read = queries.events

    def slow_read(*args, **kwargs):
        entered.set()
        assert release.wait(5), "Test did not release the blocked storage read"
        return read(*args, **kwargs)

    monkeypatch.setattr(queries, "events", slow_read)
    with (
        ThreadPoolExecutor(max_workers=1) as worker,
        client.websocket_connect("/api/admin/observability/events/ws") as socket,
    ):
        socket.send_json({"token": token})
        try:
            assert entered.wait(3), "WebSocket did not reach the storage read"
            health = worker.submit(client.get, "/api/health")
            assert health.result(timeout=2).status_code == 200
        finally:
            release.set()


def test_waiting_maintenance_does_not_block_the_api(client, monkeypatch):
    """Background SQLite commits can wait while the desktop still needs HTTP."""
    entered, release = Event(), Event()

    def slow_maintenance():
        entered.set()
        assert release.wait(5), "Test did not release maintenance storage"

    monkeypatch.setattr(client.app.state.ai, "maintenance", slow_maintenance)
    with ThreadPoolExecutor(max_workers=1) as worker:
        try:
            assert entered.wait(3), "Supervisor did not reach maintenance"
            health = worker.submit(client.get, "/api/health")
            assert health.result(timeout=2).status_code == 200
        finally:
            release.set()


def test_sqlite_reader_snapshot_does_not_block_writer_commit(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'reader-writer.db'}")
    try:
        with db.transaction(write=True) as session:
            session.execute(text("CREATE TABLE concurrency_probe (value INTEGER NOT NULL)"))
            session.execute(text("INSERT INTO concurrency_probe VALUES (1)"))

        def write():
            with db.transaction(write=True) as session:
                session.execute(text("UPDATE concurrency_probe SET value=2"))

        with ThreadPoolExecutor(max_workers=1) as worker, db.transaction() as reader:
            assert reader.scalar(text("SELECT value FROM concurrency_probe")) == 1
            worker.submit(write).result(timeout=2)
            # A consistent active read snapshot survives the concurrent commit.
            assert reader.scalar(text("SELECT value FROM concurrency_probe")) == 1
        with db.transaction() as reader:
            assert reader.scalar(text("SELECT value FROM concurrency_probe")) == 2
    finally:
        db.engine.dispose()
