"""Isolated test API: temporary SQLite, no user DB, keys, audio or telephone."""

import os
import tempfile
from pathlib import Path

import uvicorn

from app.core.config import Settings
from app.db.session import Database
from app.main import create_app
from app.migrate import upgrade
from app.providers.overpass import OverpassRestaurantProvider
from app.services.catalog import import_catalog

with tempfile.TemporaryDirectory(prefix="baria-frontend-") as directory:
    settings = Settings(
        _env_file=None,
        local_api_token="frontend-test-only-token-no-real-access",
        admin_api_token="frontend-admin-test-only-token-no-real-access",
        database_url=f"sqlite:///{Path(directory) / 'e2e.db'}",
        call_delay_seconds=0.8,
        call_timeout_seconds=5,
        ai_extraction_mode="deterministic",
        openai_api_key=None,
        real_telephony_enabled=False,
        voice_sandbox_enabled=False,
        langsmith_tracing_enabled=False,
    )
    upgrade(settings.database_url)
    if os.environ.get("E2E_CATALOG_SNAPSHOTS"):
        db = Database(settings.database_url)
        try:
            records = [
                record
                for region in ("Madrid", "Navarra")
                for record in OverpassRestaurantProvider(
                    region, Path(os.environ["E2E_CATALOG_SNAPSHOTS"])
                ).records(offline=True)
            ]
            import_catalog(db, records)
        finally:
            db.engine.dispose()
    uvicorn.run(create_app(settings), host="127.0.0.1", port=18001, access_log=False)
