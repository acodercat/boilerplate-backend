"""``create_app`` — the error envelope, middleware order and health probes.

Tested once here through a throwaway app, since every entrypoint gets the
same stack from the factory.
"""

from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError

from app.asgi import create_app
from app.errors import AppError, UnauthenticatedError

ORIGIN = "http://localhost:9999"


class _ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    error_type = "forbidden_test"


class _Body(BaseModel):
    count: int = Field(ge=1)
    code: str

    @field_validator("code")
    @classmethod
    def _upper(cls, value: str) -> str:
        if not value.isupper():
            raise ValueError("must be upper case")
        return value


_probe_reason: list[str | None] = [None]


async def _fake_probe(_: FastAPI) -> str | None:
    return _probe_reason[0]


@asynccontextmanager
async def _noop_lifespan(_: FastAPI):
    yield


def _build_app() -> FastAPI:
    app = create_app(
        title="Factory Under Test",
        version="0",
        root_path="",
        cors_origins=[ORIGIN],
        lifespan=_noop_lifespan,
        readiness_probes={"db": _fake_probe},
    )

    @app.get("/app-error")
    async def app_error():
        raise _ForbiddenError("not allowed", details={"limit": 3})

    @app.get("/unauthenticated")
    async def unauthenticated():
        raise UnauthenticatedError("who are you")

    @app.get("/http-error")
    async def http_error():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="gone")

    @app.get("/integrity-error")
    async def integrity_error():
        raise IntegrityError("INSERT", {}, Exception("duplicate key"))

    @app.get("/unexpected")
    async def unexpected():
        raise RuntimeError("boom")

    @app.post("/validated")
    async def validated(body: _Body):
        return body

    return app


@pytest.fixture
def client():
    _probe_reason[0] = None
    with TestClient(_build_app()) as client:
        yield client


def test_app_error_uses_envelope_with_details(client):
    response = client.get("/app-error")
    assert response.status_code == 403
    assert response.json() == {
        "error": {"type": "forbidden_test", "message": "not allowed", "details": {"limit": 3}}
    }


def test_401_carries_bearer_challenge(client):
    response = client.get("/unauthenticated")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json()["error"]["type"] == "unauthenticated"
    assert "details" not in response.json()["error"]


def test_http_exception_type_derived_from_status(client):
    response = client.get("/http-error")
    assert response.status_code == 404
    assert response.json() == {"error": {"type": "not_found", "message": "gone"}}


def test_unknown_route_uses_envelope(client):
    response = client.get("/no-such-route")
    assert response.status_code == 404
    assert response.json()["error"]["type"] == "not_found"


def test_integrity_error_is_conflict(client):
    response = client.get("/integrity-error")
    assert response.status_code == 409
    assert response.json()["error"]["type"] == "conflict"


def test_validation_error_lists_fields(client):
    response = client.post("/validated", json={"count": 0, "code": "lower"})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["type"] == "validation_error"
    locations = {tuple(item["location"]) for item in error["details"]}
    assert locations == {("body", "count"), ("body", "code")}


def test_validator_value_error_context_is_serializable(client):
    response = client.post("/validated", json={"count": 1, "code": "lower"})
    assert response.status_code == 422
    [detail] = response.json()["error"]["details"]
    assert detail["context"] == {"error": "must be upper case"}


def test_unexpected_error_is_500_with_cors_headers(client):
    response = client.get("/unexpected", headers={"Origin": ORIGIN})
    assert response.status_code == 500
    assert response.json()["error"]["type"] == "internal_server_error"
    assert response.headers["access-control-allow-origin"] == ORIGIN


def test_health_live(client):
    assert client.get("/health/live").json() == {"status": "ok"}


def test_health_ready_ok(client):
    assert client.get("/health/ready").status_code == 200


def test_health_ready_reports_failing_probe(client):
    _probe_reason[0] = "connection refused"
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["error"]["details"] == {
        "status": "not ready",
        "errors": ["db: connection refused"],
    }
