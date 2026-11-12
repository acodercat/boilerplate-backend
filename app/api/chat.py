"""Chat — the reference streaming (SSE) endpoint.

``POST /chat`` answers as ``text/event-stream``:

- ``delta`` — ``{"content": "<next chunk>"}``, repeated.
- ``done``  — the reply is complete.
- ``error`` — ``{"type", "message"}``; the stream ends without ``done``.

The framework adds the keep-alive pings and the no-buffering headers. A
client that disconnects cancels the generator, so nothing keeps running
for a reader that left.
"""

import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.sse import EventSourceResponse, ServerSentEvent

from app.api.dependencies import StreamingUser
from app.errors import AppError
from app.schemas.chat import ChatRequest
from app.services import chat as chat_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


@router.post("/chat", response_class=EventSourceResponse)
async def chat(_: StreamingUser, body: ChatRequest) -> AsyncIterator[ServerSentEvent]:
    """Stream the reply to one message.

    ``StreamingUser`` rather than ``CurrentUser``: see
    :func:`app.api.dependencies.get_streaming_user`.

    Authentication and validation fail before the first byte, as the
    ordinary error envelope. After that the 200 is already on the wire, so
    a failure can only be reported in-band — hence the ``error`` event,
    which carries what the envelope would have: a typed refusal keeps its
    ``error_type``, anything else is logged and answered generically.
    """
    try:
        async for chunk in chat_service.stream_reply(body.message):
            yield ServerSentEvent(event="delta", data={"content": chunk})
    except AppError as exc:
        yield _error_event(exc.error_type, exc.message)
        return
    except Exception:
        logger.exception("Chat stream failed")
        yield _error_event("internal_server_error", "An unexpected error occurred.")
        return
    yield ServerSentEvent(event="done", data={})


def _error_event(type_: str, message: str) -> ServerSentEvent:
    return ServerSentEvent(event="error", data={"type": type_, "message": message})
