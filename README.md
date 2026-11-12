# boilerplate-backend

A FastAPI starting point: async SQLAlchemy + Alembic, one error envelope for every failure, JWT auth with revocation, a server-sent event stream, health probes, and ruff / mypy / pytest preconfigured.

## Quick start

```bash
uv sync
cp .env.example .env          # set db_uri and secret_key
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

Open `http://localhost:8000/docs`. In production, a reverse proxy serves the app under `root_path` (default `/api/v1`).

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `POST` | `/users` | — | Register |
| `POST` | `/auth/access-tokens` | — | Sign in |
| `GET` | `/users?page=&page_size=` | bearer | List accounts (pagination example) |
| `GET` / `PATCH` | `/me` | bearer | Read / update the caller |
| `PUT` | `/me/password` | bearer | Change password; revokes every existing token |
| `POST` | `/chat` | bearer | Demo chat reply, streamed (SSE) |
| `GET` | `/health/live`, `/health/ready` | — | Liveness / readiness probes |

## Errors

Every failure, from a typed domain error to an unhandled crash, answers the same way:

```json
{"error": {"type": "username_taken", "message": "Username 'alice' is already taken."}}
```

Validation failures add a per-field `details` list. Clients branch on `type`; `message` is a developer-facing fallback.

## Streaming (SSE)

`POST /chat` answers as a `text/event-stream`: one `delta` event per chunk of the reply, then `done`. The reply itself is canned (`app/services/chat.py`) — swap that generator for a real model client and the endpoint stays as it is.

```bash
curl -N localhost:8000/chat -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"message": "hello"}'
```

A failure before the stream starts is the usual error envelope; one after it arrives as an `error` event carrying the same `{type, message}`. The browser's `EventSource` can neither `POST` nor send an `Authorization` header, so clients read the stream with `fetch` (e.g. `@microsoft/fetch-event-source`).

## Checks

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
```

See `CLAUDE.md` for conventions and how to add a resource, and [`docs/code-quality.md`](docs/code-quality.md) for the review every commit goes through.
