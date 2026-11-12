"""ASGI entrypoint — ``uv run uvicorn app.main:app --port 8000``."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.logging_config import setup_logging

# Before any other app import, so module-level loggers are captured.
setup_logging(log_dir=settings.log_dir, level=settings.log_level)

from app.api.router import api_router  # noqa: E402
from app.asgi import create_app, probe_database  # noqa: E402
from app.database import engine  # noqa: E402

logger = logging.getLogger(__name__)

API_VERSION = "1.0"


async def _wait_for_database(app: FastAPI) -> None:
    """Probe the database with bounded exponential backoff.

    Orchestrators start dependencies in parallel; failing on the first
    attempt would crash-loop the process over a few-second race. The
    attempts are capped so a real outage still fails startup.
    """
    delay = settings.startup_probe_base_delay_seconds
    for attempt in range(1, settings.startup_probe_attempts + 1):
        reason = await probe_database(app)
        if reason is None:
            return
        if attempt == settings.startup_probe_attempts:
            raise RuntimeError(f"Database not reachable after {attempt} attempts: {reason}")
        logger.warning(
            "Database not reachable (attempt %s/%s): %s — retrying in %.1fs",
            attempt,
            settings.startup_probe_attempts,
            reason,
            delay,
        )
        await asyncio.sleep(delay)
        delay = min(delay * 2, settings.startup_probe_max_delay_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await _wait_for_database(app)
    logger.info("API started")
    try:
        yield
    finally:
        await engine.dispose()
        logger.info("API stopped")


app = create_app(
    title=settings.app_name,
    version=API_VERSION,
    root_path=settings.root_path,
    cors_origins=settings.cors_origins,
    lifespan=lifespan,
    readiness_probes={"db": probe_database},
)
app.include_router(api_router)
