# Session Infrastructure

The backend's own login session: the signed cookie that carries it, and the in-memory
registry of per-user context that hangs off it. For why the backend is a confidential
OAuth client, where accounts are stored, and the local-mode and account-lifecycle
decisions, see `README_auth.md` at the repository root.

## Package Structure

```
infrastructure/session/
├── README.md               # This file
├── __init__.py
├── session_cookie.py       # SessionSigner — signs and verifies the cookie value
├── session_manager.py      # SessionManager — live SessionContext per account
└── token_validator.py      # Dead code, see below
```

## Components

### `SessionSigner`

Issues and verifies the backend's own `dockb_session` cookie, a Fernet token over the
username (`src/dockb/infrastructure/session/session_cookie.py`).

- `sign(username: str) -> str` — returns a token carrying the username.
- `verify(token: str) -> str | None` — returns the username if the token is ours and
  unexpired, else `None`.
- `ttl_seconds` — the cookie's `max-age`, from `OAUTH_SESSION_TTL_HOURS` (default 48).

The token is self-contained: it embeds its own timestamp and an HMAC, so the backend
verifies the issuer and the expiry without any server-side session lookup. The signing
key is derived from `DOCKB_SECRET_KEY` via SHA-256; without that variable the backend
uses an ephemeral key, so cookies do not survive a restart.

The cookie is set `HttpOnly` and `samesite="lax"`, with `path="/"` — so it is sent to
every path on the host. Narrowing the path is deferred work; see `README_todo.md`.

### `SessionManager`

A long-lived singleton holding the live `SessionContext` for each signed-in account,
keyed by username (`src/dockb/infrastructure/session/session_manager.py`).

- `get(username) -> SessionContext | None` — lookup.
- `create(username) -> SessionContext` — create and store a new context.
- `remove(username)` — drop the context (logout / teardown).

State is in memory only, so a backend restart drops every context. A cookie issued
before the restart still verifies — `SessionSigner` is stateless — so `get_current_user`
resolves the username and API calls keep working. What is gone is the `SessionContext`:
`get_current_session_context` 401s with `session_expired_relogin` until the user signs
in again, because there is no live context to hand back. No shipped route depends on it
today; `app_state` is gated on `get_current_user` alone, and the only caller of
`get_current_session_context` is a route defined inside a test
(`tests/dockb/controllers/test_auth_flow.py`). See `README_auth.md` §10.

### `SessionContext`

Per-user state for the duration of the session, holding the `JobQueue` (semantic
reconstruction jobs), the `DocCache` (spaCy `Doc` objects with TTL eviction), and a
pending notification queue for async results such as sentence splits.

It lives in `services/session_context.py` rather than here, because it bundles
service-level constructs rather than owning storage or signing.

### `TokenValidator` (dead code)

`src/dockb/infrastructure/session/token_validator.py` is a stub left over from an
earlier design. Its `validate()` ignores its argument and always returns `None`, and
nothing in `src/` or `tests/` imports or calls it. It is superseded by the signed
cookie above, and should be deleted rather than documented further.

An earlier version of this file described a `user_store.py` persisting OAuth profiles
with TinyDB. No such module exists, TinyDB is not a dependency, and the profile store
is `infrastructure/accounts/` (SQLite via the stdlib `sqlite3` module) — see
`README_auth.md` §3.
