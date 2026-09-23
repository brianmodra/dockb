# Authentication and Accounts

## Executive Summary

This document records the design for user authentication and account storage in DockB's backend:
OAuth 2.0 Authorization Code with PKCE, the backend acting as a confidential OAuth client, and a
relational database beside the backend's owned file tree. Users sign in through an identity
provider (Google and GitHub initially, configured via environment variables), the backend exchanges
the authorization code itself and mints its own session, and provider tokens never reach the
editor. Accounts, refresh tokens, and per-user app state live in a small SQLite database managed by
SQLAlchemy, so the store is transactional and a future Postgres migration is a connection-string
change.

Read this to learn how a user session starts, where tokens and state are stored, and what security
properties the design holds — and the choices the editor and backend each make in the flow. It
relates to `README_markdown_redesign.md` (the editor is a thin client) and
`README_markdown_editor_ui.md` (per-user app state).

## 1. Context and constraints

- The backend owns the knowledge graph (Neo4j), the markdown file tree, and git. Accounts and
  sessions are none of those: they are simple, transactional rows, so they get a **relational**
  database rather than the graph.
- The editor is a thin client. It never sees services, repositories, the filesystem, or — by this
  design — the provider's tokens. It authenticates to the backend and that is all.
- Mobile (iOS/Android) is a real future requirement, so an account model must exist now rather than
  being bolted on later; the flow below does not presume a browser shell and works for any client.
- OAuth login is not implemented yet. The existing `TokenValidator`
  (`src/dockb/infrastructure/session/token_validator.py`) and `SessionManager`
  (`.../session_manager.py`) are unwired scaffolding for token validation and per-account session
  contexts; this document is the design that wires them.

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

The relational store is **SQLite via SQLAlchemy**, its file **beside the backend's owned
directory** (`DOCKB_CHAPTERS_DIR`; see `src/dockb/infrastructure/document_store/README.md`). This
keeps all server-owned on-disk state in one place, with zero-ops on a single machine.

Three tables:

- **users** — `id`, `email`, `display_name`, `avatar_url`, `created_at`.
- **oauth_accounts** — `user_id`, `provider` (google/github), `provider_account_id`,
  `provider_id` unique per provider, `token` (encrypted refresh token), `expires_at`.
- **app_state** — `user_id` (primary key), `last_document_id`, `panel_widths`, `edit_mode`,
  `updated_at` (the per-user state the editor UI record keeps open).

SQLAlchemy's abstraction leaves the migration to Postgres as a connection-string change when the
backend becomes a shared service; no feature work trails it.

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
   `PUT /api/app/state` are then per-user as the UI record requires.

## 7. Open questions before trust

1. Account merging — the same email under two providers. Decide whether to link
   `oauth_accounts` rows to one `users` row by verified email or keep them separate.
2. Session lifetime — cookie expiry and whether sessions survive a backend restart (the in-memory
   `SessionManager` does not). A re-login on restart is acceptable for a desktop app; confirm.
3. First-run UX — the editor opens with no session; the login button route and "select a document"
   modal must coexist in the start-up flow.
4. Postgres readiness — confirm SQLAlchemy sync vs async keeps the current controller wiring simple
   (async SQLAlchemy is the likely choice given the async FastAPI stack).