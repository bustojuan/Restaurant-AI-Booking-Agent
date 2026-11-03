import asyncio
import json
import logging
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from filelock import FileLock, Timeout
from sqlalchemy.exc import OperationalError
from starlette.exceptions import HTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.ai.api import router as ai_router
from app.ai.runtime import AIRuntime
from app.api.routes import router, ws_router
from app.bootstrap import bootstrap
from app.core.config import Settings, get_settings
from app.core.errors import DomainError
from app.db.session import Database
from app.migrate import migration_config
from app.observability import center as _center  # noqa: F401 -- registers administrative projections
from app.observability.api import router as observation_router
from app.observability.api import ws_router as observation_ws_router
from app.providers.calls import MockCallProvider
from app.providers.images import NoImageProvider, VerifiedCatalogImageProvider
from app.schemas import ErrorResponse
from app.services.execution import BookingExecutionService
from app.voice.api import router as telephony_router
from app.voice.sandbox import router as voice_router


class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps(
            {
                "level": record.levelname,
                "message": record.getMessage(),
                "booking_id": getattr(record, "booking_id", None),
                "error_type": getattr(record, "error_type", None),
            }
        )


def error_response(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    db = Database(settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        lock = FileLock(str(Path(db.engine.url.database).resolve()) + ".executor.lock")
        try:
            lock.acquire(timeout=0)
        except Timeout:
            raise RuntimeError(
                "Another executor is using this SQLite file. Run a single Uvicorn worker."
            ) from None
        supervisor = None
        try:
            with db.engine.connect() as connection:
                if (
                    MigrationContext.configure(connection).get_current_revision()
                    != ScriptDirectory.from_config(migration_config()).get_current_head()
                ):
                    raise RuntimeError("Run python -m app.migrate before starting the server")
            image_provider = (
                VerifiedCatalogImageProvider.from_file(settings.image_catalog_path)
                if settings.image_catalog_path
                else NoImageProvider()
            )
            bootstrap(db, image_provider, settings.seed_mock_data)
            executor = BookingExecutionService(
                db, MockCallProvider(settings.call_delay_seconds), settings.call_timeout_seconds
            )
            executor.recover()
            app.state.executor = executor
            async with AIRuntime.open(db, executor, settings) as runtime:
                executor.ai = runtime
                app.state.ai = runtime
                supervisor = asyncio.create_task(executor.supervise())
                try:
                    yield
                finally:
                    supervisor.cancel()
                    with suppress(asyncio.CancelledError):
                        await supervisor
                    supervisor = None
        finally:
            if supervisor:
                supervisor.cancel()
                with suppress(asyncio.CancelledError):
                    await supervisor
            lock.release()
            db.engine.dispose()

    app = FastAPI(
        title="AI Restaurant Booking Agent",
        version="0.1.0",
        lifespan=lifespan,
        description="Local booking API. Simulation by default; paid voice and telephony require explicit configuration and authorization. See docs/frontend-api.md.",
        responses={code: {"model": ErrorResponse} for code in [401, 404, 409, 422, 428, 503]},
    )
    app.state.settings, app.state.db = settings, db
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "If-Match"],
        expose_headers=["ETag"],
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError):
        return error_response(exc.code, exc.message, exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return error_response("validation_error", "Invalid request parameters or body", 422)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return error_response("http_error", str(exc.detail), exc.status_code)

    @app.exception_handler(OperationalError)
    async def database_error(request: Request, exc: OperationalError):
        return error_response(
            "database_unavailable", "Database temporarily unavailable; retry after reloading", 503
        )

    @app.get("/api/health", tags=["Health"])
    def health() -> dict[str, str]:
        return {"status": "ok", "mode": "simulation"}

    app.include_router(router)
    app.include_router(ws_router)
    app.include_router(ai_router)
    app.include_router(voice_router)
    app.include_router(telephony_router)
    app.include_router(observation_router)
    app.include_router(observation_ws_router)
    return app


def main() -> None:
    import uvicorn

    settings = get_settings()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, access_log=False)


if __name__ == "__main__":
    main()
