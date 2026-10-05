# Session Infrastructure

## Executive Summary

This package holds the backend's own login session: the signed cookie that carries it, and the
in-memory registry of per-user context that hangs off it. Nothing here decides *how* a user signs
in or where accounts live — for the confidential-OAuth-client decision, the SQLite accounts
store, and the no-local-mode and account-lifecycle calls, see `README_auth.md` at the repository
root.

## Package Structure

```
infrastructure/session/
├── README.md               # This file
├── __init__.py
├── session_cookie.py       # SessionSigner — signs and verifies the cookie value
└── session_manager.py      # SessionManager — live SessionContext per account
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
key is derived from `DOCKB_SECRET_KEY` via SHA-256, which is **required**: there is no
ephemeral fallback, because the same secret also encrypts OAuth refresh tokens and peppers
password hashes, so a per-process key would invalidate all three on every restart.

The cookie is set `HttpOnly` and `samesite="strict"`, with `path="/api"`. The whole
manuscript API lives under `/api`, so the cookie reaches everything that
authenticates it while being withheld from the rest of the host — the `/callback`
page that sets it, the editor shell at `/editor/`, and the interactive docs at
`/docs` and `/openapi.json`.

`strict` withholds a cookie from *cross-site* requests, which is what a `file://` renderer
loading the app from disk produced — the reason OAuth mode was unreachable from the editor. The
fix was to remove the cross-site request, not to weaken this attribute to `none`:
`SameSite=None` would have required `Secure`, an https origin, and would have let the cookie
ride along on requests from any site. The editor is same-origin with the API because the backend
serves the renderer itself (`dockb/editor_shell.py`), and the OAuth callback is a top-level
navigation to a loopback URL on this same origin, so both still carry the cookie. `strict` is
strictly stronger than the `lax` this replaces, and password sign-in needs it: a cross-site form
post carries no `state` or PKCE to protect it. Nothing in the renderer sets
`credentials: "include"`, because a same-origin request carries the cookie by default. See
`README_auth.md` §4.

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

### Removed: `TokenValidator`

`token_validator.py` was a stub from an earlier design in which each request validated a
provider token and looked the account up in a `SessionManager`. Its `validate()` ignored
its argument and always returned `None`, and nothing in `src/` or `tests/` called it. The
signed cookie above replaced it and the file has been deleted.

That design also assumed a `user_store.py` persisting OAuth profiles with TinyDB. No such
module ever existed, TinyDB is not a dependency, and the profile store is
`infrastructure/accounts/` (SQLite via the stdlib `sqlite3` module) — see `README_auth.md`
§3.
