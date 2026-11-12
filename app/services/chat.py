"""A stand-in chat model: it streams a canned reply in small chunks.

:func:`stream_reply` is the seam. A real model client replaces its body
and keeps its shape — an async generator of text chunks — and the
endpoint does not change.
"""

import asyncio
from collections.abc import AsyncIterator

_CHUNK_DELAY_SECONDS = 0.05


async def stream_reply(message: str) -> AsyncIterator[str]:
    """Yield the reply to ``message`` piece by piece. Concatenating every
    chunk gives the full text."""
    reply = f"You said: {message}. This reply is canned; a real model goes here."
    for index, word in enumerate(reply.split(" ")):
        await asyncio.sleep(_CHUNK_DELAY_SECONDS)
        yield word if index == 0 else f" {word}"
