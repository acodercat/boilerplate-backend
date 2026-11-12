"""The HTTP stack every app in this project is built on.

:func:`create_app` owns everything that must not differ between ASGI
entrypoints — the error envelope, the middleware **order**, the health
probes. A second entrypoint (say, an internal admin API) is a second call
with different arguments, never a hand-assembled ``FastAPI()``: the
arguments are the complete list of what may differ.
"""

from collections.abc import Awaitable, Callable, Mapping

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.types import Lifespan

from app.database import engine
from app.exception_handlers import install_error_handlers

ReadinessProbe = Callable[[FastAPI], Awaitable[str | None]]
"""Checks one dependency: ``None`` when healthy, else a short reason.

Returning a reason rather than raising keeps each probe responsible for
naming the exceptions it expects, so the readiness route never has to
blanket-catch ``Exception`` and call an unrelated bug "not ready".
"""


async def probe_database(_: FastAPI) -> str | None:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError) as exc:
        return str(exc)
    return None


def create_app(
    *,
    title: str,
    version: str,
    root_path: str,
    cors_origins: list[str],
    lifespan: Lifespan[FastAPI],
    readiness_probes: Mapping[str, ReadinessProbe],
) -> FastAPI:
    """Build an app with the standard stack. Routers are added by the caller.

    Args:
        title: OpenAPI title.
        version: OpenAPI version.
        root_path: Path prefix the reverse proxy strips before us.
        cors_origins: Explicit allowlist, never ``["*"]``.
        lifespan: The app's own startup/shutdown context manager.
        readiness_probes: ``{name: probe}`` behind ``/health/ready``; the
            name prefixes the reason in the 503 body.
    """
    app = FastAPI(title=title, version=version, root_path=root_path, lifespan=lifespan)

    # First: it adds the middleware that answers an unexpected error, which
    # must sit innermost so CORS still wraps that 500.
    install_error_handlers(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _install_health_routes(app, readiness_probes)
    return app


def _install_health_routes(app: FastAPI, readiness_probes: Mapping[str, ReadinessProbe]) -> None:
    @app.get("/health/live", tags=["health"])
    async def health_live() -> dict[str, str]:
        """Liveness: the process is up. Always 200 while the loop runs."""
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    async def health_ready() -> dict[str, str]:
        """Readiness: every dependency is reachable.

        503 when one is down, so the orchestrator stops routing traffic
        without restarting a process that will recover on its own.
        """
        errors = [
            f"{name}: {reason}"
            for name, probe in readiness_probes.items()
            if (reason := await probe(app)) is not None
        ]
        if errors:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"status": "not ready", "errors": errors},
            )
        return {"status": "ok"}
