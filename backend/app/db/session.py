from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool


class Database:
    def __init__(self, url: str):
        if not url.startswith("sqlite:///") or url.endswith(":memory:"):
            raise ValueError("Use a file-backed SQLite database")
        # Short desktop/API transactions must not wait for a bounded pool on an
        # async execution path. Connections still belong to one Session at a time.
        self.engine = create_engine(
            url, connect_args={"check_same_thread": False, "timeout": 10}, poolclass=NullPool
        )

        @event.listens_for(self.engine, "connect")
        def configure_sqlite(connection, _):
            connection.isolation_level = None
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=10000")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=FULL")
            cursor.close()

        @event.listens_for(self.engine, "begin")
        def begin(connection):
            mode = "IMMEDIATE" if connection.get_execution_options().get("write_transaction") else "DEFERRED"
            connection.exec_driver_sql(f"BEGIN {mode}")

        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    @contextmanager
    def transaction(self, *, write: bool = False) -> Iterator[Session]:
        with self.sessions() as session:
            if write:
                session.connection(execution_options={"write_transaction": True})
            with session.begin_nested() if write else session.begin():
                yield session
            if write:
                session.commit()
