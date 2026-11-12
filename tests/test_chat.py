"""The streaming chat endpoint — offline, as a generator and over HTTP."""

from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import chat as chat_api
from app.api.dependencies import get_streaming_user
from app.asgi import create_app
from app.errors import AppError
from app.schemas.chat import ChatRequest
from app.services import chat as chat_service
from tests.factories import make_user


@pytest.fixture(autouse=True)
def _no_delay(monkeypatch):
    monkeypatch.setattr(chat_service, "_CHUNK_DELAY_SECONDS", 0)


async def _events(message: str = "hello"):
    request = ChatRequest(message=message)
    return [event async for event in chat_api.chat(await make_user(), request)]


def _failing_after_one_chunk(error: Exception):
    async def stream_reply(_message: str):
        yield "partial"
        raise error

    return stream_reply


async def test_stream_is_deltas_then_done():
    *deltas, last = await _events()
    assert {event.event for event in deltas} == {"delta"}
    assert last.event == "done"
    reply = "".join(event.data["content"] for event in deltas)
    assert reply == "You said: hello. This reply is canned; a real model goes here."


async def test_typed_error_mid_stream_keeps_its_type(monkeypatch):
    class _QuotaError(AppError):
        error_type = "quota_exceeded"

    monkeypatch.setattr(
        chat_service, "stream_reply", _failing_after_one_chunk(_QuotaError("No quota left."))
    )
    events = await _events()
    assert [event.event for event in events] == ["delta", "error"]
    assert events[-1].data == {"type": "quota_exceeded", "message": "No quota left."}


async def test_unexpected_error_mid_stream_is_generic(monkeypatch):
    monkeypatch.setattr(
        chat_service, "stream_reply", _failing_after_one_chunk(RuntimeError("model went away"))
    )
    events = await _events()
    assert [event.event for event in events] == ["delta", "error"]
    assert events[-1].data["type"] == "internal_server_error"
    assert "model went away" not in events[-1].data["message"]


@asynccontextmanager
async def _noop_lifespan(_: FastAPI):
    yield


@pytest.fixture
def app() -> FastAPI:
    app = create_app(
        title="Chat Under Test",
        version="0",
        root_path="",
        cors_origins=[],
        lifespan=_noop_lifespan,
        readiness_probes={},
    )
    app.include_router(chat_api.router)
    return app


async def test_chat_over_http_is_an_event_stream(app):
    user = await make_user()
    app.dependency_overrides[get_streaming_user] = lambda: user
    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "hi"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = response.text.replace("\r\n", "\n").strip().split("\n\n")
    assert frames[0] == 'event: delta\ndata: {"content": "You"}'
    assert frames[-1] == "event: done\ndata: {}"


def test_chat_without_a_token_is_the_ordinary_401(app):
    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "hi"})
    assert response.status_code == 401
    assert response.json()["error"]["type"] == "unauthenticated"
