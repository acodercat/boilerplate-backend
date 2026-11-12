# Code quality

What clean code means in this repository, and the review every change goes through before it is committed. Project-specific conventions (error envelope, transactions, pagination, auth, streaming) live in `CLAUDE.md` and are not repeated here.

**Every commit is reviewed against the checklist at the end.** A change that fails an item is fixed before it lands, not after.

---

## 1. Principles

1. **Simple beats clever.** The right amount of code is the least that solves today's problem clearly. A reader should never have to ask why something is there.
2. **Fix causes, not symptoms.** A bug is fixed where it originates. Code that works around a defect elsewhere is a second defect.
3. **One way to do each thing.** When the codebase already has a pattern (error envelope, pagination, transactions, auth dependency), new code uses it. A second pattern needs a reason strong enough to migrate the first one.
4. **Code says what; comments say why.** If a comment restates the code, delete it. If the code needs a comment to explain what it does, rename or restructure it.
5. **What a tool can check, a tool checks.** A rule that ruff or mypy can enforce belongs in `pyproject.toml`, not in a reviewer's memory. This document covers what they cannot see.

---

## 2. No over-design

An abstraction must pay for itself today. It does that by having **at least two real callers**, or by **hiding complexity a caller would otherwise get wrong**. Neither "we might need it later" nor "it looks more structured" counts.

Signs of over-design:

- A base class, mixin, protocol or generic with one user. Two columns written out in a model are clearer than a mixin that only that model inherits.
- A wrapper type around a primitive that adds no rule (`UserId(int)` with no validation).
- A setting nobody will change, or a parameter every caller passes the same value for.
- A factory, registry or plugin hook for a set with one member.
- Layers that only forward: a service function that calls one query and returns it, a schema identical to another schema.
- Config-driven behaviour where a constant with a comment would do.
- A new dependency for something the standard library or a library already installed does.

When in doubt, inline it. Extracting later, when the second caller arrives, is cheap; un-extracting a wrong abstraction is not. The same holds for duplication: two similar blocks may stay; the third is the signal to extract.

---

## 3. No patches

A patch makes a symptom go away without removing its cause. They accumulate, interact, and make the code impossible to reason about.

Not allowed:

- **Special-casing a bug**: `if user.id == 0: ...`, an extra `if x is None` far from where `None` was produced.
- **Swallowing errors**: `except Exception: pass`, or a broad `except` that returns a default. Catch the narrowest exception you can name, at the layer that knows what to do about it. A catch-all belongs only at an outer boundary that logs the error and still reports a failure (the 500 middleware, the `error` event of a stream).
- **Silencing the tools**: `# type: ignore`, `# noqa`, `cast(...)`, `Any` to get a check passing. Allowed only with the specific code and a one-line reason, and only when the tool is wrong, not the code (as in `install_error_handlers`).
- **Masking our own ordering bugs** with `sleep`, retries or "refresh it again". Retrying is for things outside our control (a dependency still starting up), never for a race in our own code.
- **Copy-paste fixes**: fixing one copy of duplicated logic and leaving the other. Fix it once, in one place.
- **Compatibility shims** for code that has no other users: rename it and update the callers.
- **Commented-out code** and dead branches. Git keeps history; the file keeps only what runs.

If the root cause genuinely cannot be fixed in this change, say so in the commit message and leave a comment naming the cause, not a vague `TODO`.

---

## 4. Naming

Names are the main documentation. Spend time on them.

| Kind | Rule | Examples |
|---|---|---|
| Module | A resource is a singular noun; a collection of like things is plural | `user.py`, `chat.py` · `errors.py`, `dependencies.py` |
| Function | Verb phrase for what it does or returns | `create_access_token`, `paginate`, `stream_reply` |
| Boolean | Reads as a yes/no question | `is_user_active`, `has_expired` |
| Class | Noun; errors end in `Error` | `User`, `AccessToken`, `UsernameTakenError` |
| Constant | `UPPER_SNAKE`, module-private with `_` | `BCRYPT_MAX_BYTES`, `_CHUNK_DELAY_SECONDS` |
| `error_type` | `snake_case`, describes the refusal, stable forever | `username_taken`, `incorrect_password` |
| Private | Leading `_` for anything not used outside the module | `_resolve_user`, `_status_phrase` |

Also:

- **Name for meaning, not mechanism.** `SessionFactory`, not `AsyncSessionMakerInstance`; `revoke_tokens`, not `bump_token_version`.
- **One word per concept across the codebase.** If it is a `user`, it is never also an `account` or `member` in code.
- **No abbreviations** beyond universal ones (`id`, `db`, `url`, `jwt`). `usr`, `cfg`, `mgr`, `tmp` are not names.
- **No type in the name** (`user_dict`, `name_str`); the annotation already says it.
- **No vague words** — `data`, `info`, `manager`, `helper`, `utils`, `handle`, `process` — unless they are the framework's own term or nothing more precise exists.
- **No single-letter names**, anywhere: not for loop variables, comprehensions, lambdas, caught exceptions or type parameters. Write `for user in users`, `except ValueError as exc`, `PaginatedResponse[ItemT]` — never `for u in users`, `except ValueError as e`, `[T]`. The only exception is `_` for a value that is deliberately unused.

---

## 5. Architecture

Dependencies point one way:

```
api  →  services  →  auth / models  →  database / config
         (schemas and common are leaves anyone may import)
```

| Layer | Owns | Must not |
|---|---|---|
| `app/api/` | HTTP: routes, dependencies, status codes, commit | Contain business rules; catch `AppError` |
| `app/services/` | Business rules; raises `AppError` | Import FastAPI; commit |
| `app/auth.py` | Password hashing, tokens | Know about HTTP |
| `app/models/` | Tables | Contain behaviour beyond column definitions |
| `app/schemas/` | Request/response shapes and their validation | Touch the database |
| `app/common/` | Helpers with no domain | Import from any layer above |

Rules:

- A plain read may stay inline in the endpoint. As soon as there is a rule (a check, a refusal, a side effect), it moves to `services/`.
- Configuration is read through `settings` only, never `os.environ`.
- No module-level variable is reassigned or mutated at runtime. State that changes belongs in the database or on an object the lifespan owns.
- A new ASGI app is another `create_app(...)` call, never a hand-built `FastAPI()`.
- A new concept gets its own module when it has its own vocabulary. It does not get one to make a file shorter.

---

## 6. Functions and modules

- **One job, one level of abstraction.** A function either orchestrates steps or performs one; mixing both is the cue to split.
- **Flat over nested.** Handle the refusals first and return early, so the main path is not indented.
- **Keyword-only arguments** (`*,`) once a function takes more than three, so call sites read without the signature.
- **No boolean flag parameters that switch behaviour.** Two behaviours are two functions.
- **No hidden side effects.** A function named like a query does not write; a function that writes says so in its name or docstring.
- **Pure where possible.** Push I/O to the edges so the logic can be tested without it.
- **Never block the event loop.** No synchronous I/O or CPU-heavy call inside `async def`; move it off the loop (`asyncio.to_thread`, as password hashing does).
- **No magic numbers.** A literal with meaning gets a named constant, and a comment when the value has a reason.

---

## 7. Types

- `mypy --strict` passes. New code adds no `Any` that escapes a function boundary.
- FastAPI parameters use `Annotated[..., Depends()/Query()]`; the response model is the return annotation.
- Prefer precise types: `Literal` for closed string sets, `StrEnum` for persisted ones, frozen `dataclass` for internal records, pydantic models only at the boundary.

---

## 8. Errors and logging

- Catch only what you can name and handle. Re-raise with `from exc` when translating.
- Log once, at the layer that decides the outcome. Never log and re-raise the same error.
- Logs never contain secrets: no passwords, tokens, hashes, or bound SQL parameters.
- Error messages shown to a client never include internals (exception text, SQL, stack frames), and refusals that could aid an attacker are uniform.

---

## 9. Comments and docstrings

- A module docstring says what the module is for, when that is not obvious from its name.
- A docstring's first line is a sentence about what the function does or returns. Further lines are for contracts and reasons, not a restatement of the signature.
- Comments explain *why*: a constraint, a trade-off, a non-obvious failure the code prevents. Each one should survive the question "would the code be wrong without this knowledge?".
- No commented-out code, no changelog comments ("added in v2"), no `TODO` without a concrete next step.

---

## 10. Tests

- Tests describe behaviour: the name says what must hold (`test_change_password_revokes_tokens`).
- The default suite is offline: no database, network or sleeps. Use small fakes for the one thing under test.
- One behaviour per test; `pytest.mark.parametrize` for variations of one rule.
- A bug fix comes with a test that fails without the fix.
- Test helpers live in `tests/factories.py` or `conftest.py`, never imported from another test module.

---

## 11. Documentation

- `README.md` and `CLAUDE.md` change in the same commit as the behaviour they describe. A stale doc is a bug.
- A new convention is written down in `CLAUDE.md` when it is introduced, with its reason.

---

## Pre-commit review

### 1. Run the checks

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
```

All four pass. A failure is fixed, not suppressed.

### 2. Read the whole diff as a reviewer

Read every changed line in `git diff` (and every new file), as if someone else wrote it. Then go through the checklist:

**Design**
- [ ] The change solves the stated problem and nothing else.
- [ ] Every new abstraction has two real callers or hides real complexity.
- [ ] No patch: each fix sits where the problem originates.
- [ ] It follows the conventions in `CLAUDE.md` instead of introducing a second way.
- [ ] Layering holds: no upward imports, no rules in endpoints, no FastAPI in services.

**Code**
- [ ] Every name says what the thing means, in the codebase's vocabulary; no single-letter names.
- [ ] No dead code, commented-out code, debug prints, or unused imports, parameters or settings.
- [ ] No new `type: ignore`, `noqa`, `cast` or `Any` without a specific reason beside it.
- [ ] No broad `except`; nothing swallowed; nothing secret logged.
- [ ] Comments explain why, and every one is still true.

**Behaviour**
- [ ] A model change has a migration that was read, not just generated.
- [ ] New behaviour and every bug fix have a test.

**Docs and hygiene**
- [ ] `README.md` / `CLAUDE.md` match the code.
- [ ] Nothing staged that should not be: secrets, `.env`, logs, scratch files.

### 3. Prefer deleting

Before committing, look for what the change can lose: a helper that is now used once, a parameter that is always the same, a comment that repeats the code. The best review outcome is a smaller diff.

### 4. Commit

One logical change per commit; an unrelated tidy-up is its own commit. The message is `type(scope): summary` in the imperative, with a body explaining *why* when the diff does not make it obvious:

```
fix(user): refuse an explicit null in PATCH /me

The column is NOT NULL, so a null reached the database and came back as
a generic 409 conflict instead of a 422 naming the field.
```

`type` is one of `feat`, `fix`, `refactor`, `test`, `docs`, `chore`.
