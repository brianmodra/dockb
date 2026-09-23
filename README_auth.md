# Authentication and Accounts

## Executive Summary

This document explains how DockB users sign in and where their accounts live.
They authenticate with Google or GitHub; the backend (not the editor) exchanges
the code, mints its own session cookie, and stores accounts, tokens, and
per-user app state in a small SQLite database. Provider tokens never reach the
editor.

The routes, session gate, and app-state endpoints are implemented. On first run
the editor shows a Sign-in button, then restores the last document or asks the
user to pick one. Read this for the login flow, storage, and security choices.

## 1. Context and constraints

- The backend owns the knowledge graph (Neo4j), the markdown file tree, and git. Accounts and
  sessions are none of those: they are simple, transactional rows, so they get a **relational**
  database rather than the graph.
- The editor is a thin client. It never sees services, repositories, the filesystem, or — by this
  design — the provider's tokens. It authenticates to the backend and that is all.
- Mobile (iOS/Android) is a real future requirement, so an account model must exist now rather than
  being bolted on later; the flow below does not presume a browser shell and works for any client.
- OAuth login is implemented. The backend's own session is a **signed HttpOnly cookie**
  (`dockb_session`, issued by `SessionSigner`); the in-memory `SessionManager`
  (`src/dockb/infrastructure/session/session_manager.py`) keeps a live `SessionContext` per
  account while the process runs, so a backend restart invalidates login — the user signs in again.
  The earlier `TokenValidator` scaffolding is superseded by the signed cookie.

## 2. Decision: backend is the confidential OAuth client (decided)

The OAuth flow is **Authorization Code + PKCE** (RFC 8252, "OAuth 2.0 for Native Apps"):

1. The editor opens the system browser to the provider's consent page. It never handles the code.
2. The provider redirects to `http://localhost:<port>/callback` served by **FastAPI**.
3. The backend exchanges the code for tokens using the provider client secret, saves the refresh
   token (encrypted), resolves the account, and mints **its own session** (HttpOnly cookie) that the
   editor presents on every subsequent API call.
4. On each request the controllers receive the session context for that account and serve that
   user; they do not re-contact the provider.

The alternative — the editor holding a public-client token — loses: refresh tokens would sit in
the editor's storage (a worse thin client), and the backend could not control session expiry.
Rejected for exactly that reason.

Consequences:

- The provider's access/refresh tokens exist only inside the backend.
- FastAPI needs the loopback callback path; the editor only needs to open a URL.
- `SessionManager` keeps per-account `SessionContext`s in memory (as today), so token validation
  happens at login, not per request.

## 3. Decision: accounts and state live in SQLite (decided)

The relational store is **SQLite via the Python standard library `sqlite3`** (no ORM), its file
`dockb_app.db` **beside the backend's owned directory** (`DOCKB_CHAPTERS_DIR`) — the directory the
composed `AuthService` receives as its `base_dir`. This keeps all server-owned on-disk state in one
place, with zero-ops on a single machine. Foreign keys are enforced (`PRAGMA foreign_keys=ON`), so
deleting a user cascades to its OAuth links and app state.

Three tables (`src/dockb/infrastructure/accounts/store.py` owns the exact schema):
`users`, `oauth_accounts` (per provider account, holding the encrypted refresh `token` and its
`expires_at`), and `app_state` (per user, holding the editor state the UI record keeps open).

The refresh-token `token` column is encrypted with Fernet under a key derived from the server
secret (`DOCKB_SECRET_KEY`), so the store doubles as a credential store and is treated as one.
Moving to Postgres later means re-implementing the small `AccountStore` against a new driver; the
store interface and route-controller call sites do not change.

## 4. Security properties (decided)

- **OAuth `state` and PKCE.** The authorization request carries both; the callback verifies them,
  so logins cannot be CSRF'd or the code swapped.
- **Refresh tokens encrypted at rest.** The `token` column is encrypted with a key derived from a
  server secret (e.g. `cryptography` Fernet) — never plaintext. This is a credential store and is
  treated as one.
- **Episode secrets, not repo secrets.** Provider client id/secret come from environment
  variables/`.env` only, never committed.
- **HttpOnly session cookie.** The backend's own session is not readable by JS; the editor holds no
  provider credential that could leak.
- **Loopback callback scoped.** The OAuth client for the desktop app registers only the loopback
  redirect URI, so the code cannot be intercepted by a third origin.

## 5. Providers (decided initially)

Google and GitHub, configured by environment variables:

- `OAUTH_GOOGLE_CLIENT_ID`, `OAUTH_GOOGLE_CLIENT_SECRET`
- `OAUTH_GITHUB_CLIENT_ID`, `OAUTH_GITHUB_CLIENT_SECRET`
- `OAUTH_CALLBACK_PORT` (the loopback port for the login redirect)
- `DOCKB_SECRET_KEY` (server secret; derives the Fernet key that encrypts refresh tokens and the
  session-cookie signer key). Auth wiring only runs when this is set.
- `OAUTH_SESSION_TTL_HOURS` (session cookie lifetime, default 48)

Configuring a provider is adding its env pair; the flow code is provider-agnostic apart from the
consent URL and the token exchange profile.

## 6. Flow in full (reference)

1. User clicks "Sign in" in the editor. The editor asks the backend for a login URL
   (`GET /api/auth/login?provider=google`), which returns the provider consent URL with `state` and
   a PKCE `code_verifier` the backend remembers.
2. The editor opens that URL in the system browser; the user consents.
3. Provider redirects to `http://localhost:{OAUTH_CALLBACK_PORT}/callback?...&code=...`.
4. The backend verifies `state`, exchanges the code (with `code_verifier`), stores the encrypted
   refresh token, upserts the user, and sets its own HttpOnly session cookie.
5. The editor reads that session; every API call after carries it. `GET /api/app/state` and
   `PUT /api/app/state` are then per-user as the UI record requires; `GET /api/auth/me` returns the
   signed-in user's profile and doubles as a session check from the editor.

## 7. Open questions

1. Account merging — the same email under two providers. Currently each provider account is its own
   `users` row; decide whether to link by verified email.

## 8. Resolved questions

Settled while the design was implemented:

- **First-run UX** — no session opens the Sign-in gate; after a live session the editor restores
  the last document or shows the select-document modal (`README_markdown_editor_ui.md` §9).
- **Session lifetime** — the session cookie lives for `OAUTH_SESSION_TTL_HOURS` (default 48)
  hours; sessions do not survive a backend restart (the in-memory `SessionManager` does not), and
  a re-login on restart is accepted for the desktop app.
- **SQL storage** — the SQLite store uses the stdlib `sqlite3` module with sync handlers, not
  SQLAlchemy; the store is small, local, and single-process, and an ORM adds nothing there. A
  future Postgres migration re-implements `AccountStore` behind the same interface.
- **State/PKCE memory** — pending login states (with their PKCE verifiers) are valid for 10
  minutes and single-use; storing them alongside the code-swap protects logins against CSRF and
  code-swapping, matching the security goals in §4.
