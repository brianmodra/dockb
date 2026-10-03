# Authentication and Accounts

## Executive Summary

This document explains how DockB users sign in and where their accounts live.
They authenticate with Google or GitHub; the backend (not the editor) exchanges
the code, mints its own session cookie, and stores accounts, tokens, and
per-user app state in a small SQLite database. Provider tokens never reach the
editor. **Local mode** — no sign-in, with the identity being the OS username —
is opt-in via `DOCKB_LOCAL_MODE=true` (see §6); the code still infers it from
absent provider configuration, which §6 changes.

The routes, session gate, and app-state endpoints are implemented. On first run
the editor shows a Sign-in button, then restores the last document or asks the
user to pick one. Read this for the login flow, storage, and security choices.

**Part of this document is a specification, not a description.** §6 and §7 record decisions that
have *not* been implemented; the code still behaves as this document previously described. The
table below is the baseline, verified against the code, so a build can start from it.

| Decision | The code today | The target | Done when |
| --- | --- | --- | --- |
| §6 local mode is opt-in | `requires_login` is `bool(self._providers)` (`services/auth_service.py`), so local mode is inferred from the absence of provider credentials. `DOCKB_LOCAL_MODE` exists nowhere in `src/`. Because `get_current_user` falls through to the OS user in local mode, the gated routes are open to any caller today. | `DOCKB_LOCAL_MODE=true` turns local mode on; nothing infers it. Provider configuration no longer selects the mode. | With the variable unset and a provider configured, login is required. With it set to `true` and no provider, requests are served as the OS user. The inference path is gone. |
| §7 account lifecycle is admin-CLI only | No admin CLI exists: `src/dockb/cli/` holds only `import_document.py` and `reconstruct_chapter.py`. There is no password column on `users`. | A CLI that creates accounts and sets or resets a password. No HTTP registration or recovery route. | An account can be created with a password and then sign in. No route accepts a registration or reset request. |
| §7 password login (a later step) | Not implemented. No password-hashing library is installed — `pyproject.toml` has `cryptography` and stdlib `hashlib` only. | Argon2id, verified off the event loop, constant-time on the not-found path, rate limited. | A wrong password and an unknown username cost the same and both fail; a correct password mints a session cookie. |
| `/api/auth/config` response | Returns `{"login_required", "providers"}` (`controllers/auth.py`); the editor branches on `login_required` at `frontend/src/renderer/main.ts`. | Gains a `password_login` flag when the password step lands, so the FE can render a form rather than only provider buttons. | The endpoint distinguishes all four states (local, federated only, password only, both) and the editor gates correctly in each. |

As this work lands, this document should get smaller. The decisions and their rationale stay here;
the implementation detail moves down into the package that owns it — `infrastructure/accounts/`
(the user and token schema and the admin CLI), `infrastructure/session/`, and
`controllers/README_API.md`. See `README_todo.md`.

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
`dockb_app.db` **beside the backend's owned directory** — the chapters directory the composed
`AuthService` receives as its `base_dir`. The chapters directory is `DOCKB_CHAPTERS_DIR`, defaulting
to `cwd`/`dockb_chapters_dir` when unset, and is created (and git-initialized) when missing
(`resolve_document_base_dir` in `composition.py`). This keeps all server-owned on-disk state in one
place, with zero-ops on a single machine. Foreign keys are enforced (`PRAGMA foreign_keys=ON`), so
deleting a user cascades to its OAuth links and app state.

Three tables (`src/dockb/infrastructure/accounts/store.py` owns the exact schema):
`users`, `oauth_accounts` (per provider account, holding the encrypted refresh `token` and its
`expires_at`), and `app_state` (per user, holding the editor state the UI record keeps open).
User identity is the unique `users.username` column everywhere: sessions, cookies, and app state
carry the username — the OS user in local (non-OAuth) mode, the OAuth profile username otherwise.
`users` keeps an internal UUID `id` only for the `oauth_accounts` foreign key; `app_state` and the
public store accessors are keyed by `username`.

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
  provider credential that could leak. It is scoped to `/api`, so it is sent to the manuscript
  routes that authenticate it and to nothing else the server serves, including `/editor` and
  `/callback`.
- **Same-origin editor.** The renderer is served by the backend rather than loaded from `file://`,
  so no cross-site cookie is needed and no CORS grant is issued. This is what keeps the `null`
  origin — which every `file://` page sends — from reading the API.
- **Loopback callback scoped.** The OAuth client for the desktop app registers only the loopback
  redirect URI, so the code cannot be intercepted by a third origin.

## 5. Providers (decided initially)

Google and GitHub, configured by environment variables:

- `OAUTH_GOOGLE_CLIENT_ID`, `OAUTH_GOOGLE_CLIENT_SECRET`
- `OAUTH_GITHUB_CLIENT_ID`, `OAUTH_GITHUB_CLIENT_SECRET`
- `OAUTH_CALLBACK_PORT` (the loopback port for the login redirect)
- `DOCKB_SECRET_KEY` (server secret; derives the Fernet key that encrypts refresh tokens and the
  session-cookie signer key). Without it the backend uses an ephemeral key in memory (see §6).
- `DOCKB_LOCAL_MODE` (opt in to local mode with `true`; see §6)
- `OAUTH_SESSION_TTL_HOURS` (session cookie lifetime, default 48)

Configuring a provider is adding its env pair; the flow code is provider-agnostic apart from the
consent URL and the token exchange profile.

## 6. Local (non-OAuth) mode is opt-in (decided)

Local mode is enabled explicitly, with `DOCKB_LOCAL_MODE=true`. It is **not** inferred from the
absence of a configured provider. This inverts the earlier behaviour, which ran in local mode
whenever no provider was configured, for a security reason: inference means a deployment that
forgets one environment variable silently serves every request as the local OS user, with no
error anywhere. That is an authentication bypass by misconfiguration, and it is only harmless
while a single person uses the machine. Once real accounts exist, local mode has to be a decision
rather than a default.

When local mode is on, OAuth is off, no login step exists, and the identity is the OS username
(`$USER`, falling back to `getpass.getuser()`). A provider client id without its secret still
does not count as configured, since a provider is only configured when its id *and* secret are
both present — but with the mode explicit, provider configuration no longer selects it.

The set of enabled sign-in methods is therefore a matrix rather than a single boolean: local
mode, federated providers only, password only, or federated and password together. The one
combination that skips the login gate is deliberate local mode, which is now something an
operator asks for by name.

- The session cookie is not required; `get_current_user` falls back to the local username and
  `ensure_local_user` creates the minimal `users` row lazily (display name = username, empty
  email/avatar).
- `/api/auth/me` answers with that local profile. `GET /api/auth/config` reports
  `{"login_required": false, "providers": []}`, and the editor opens its Sign-in gate **only**
  when that response says login is required — so in local mode the gate never appears and the
  menubar simply shows the OS username.
- The built Electron shell loads the renderer from the **backend**, at `/editor/`, so the editor
  is same-origin with `/api`. That is what lets the `SameSite=lax` session cookie reach the gated
  routes: a `file://` renderer talking to `http://localhost:8000` is a cross-site request, and
  browsers withhold a `lax` cookie on those. It also means the app needs **no CORS middleware**,
  which is the stronger half of the win — a grant for the `null` origin a `file://` page sends,
  with credentials, let any local file read the API as the signed-in user. The Vite dev server
  needs none either, because its `/api` proxy is same-origin to the browser. See
  `src/dockb/controllers/README_API.md` § The editor shell and `editor_shell.py`.
- Auth wiring runs whenever there is an accounts directory, which is always: the chapters directory,
  resolved by `resolve_document_base_dir` (`DOCKB_CHAPTERS_DIR`, defaulting to `cwd`/`dockb_chapters_dir`
  and provisioned when missing). `DOCKB_SECRET_KEY` is not required: without it the backend uses an
  ephemeral signer/encryption key in memory (nothing is signed or encrypted in local mode, and the
  accounts DB may be recreated on restart), and OAuth providers are ignored even if their id/secret
  pairs are set — a provider is only enabled when a secret is present.
- Per-user app state is keyed by the local username, so two OS users on the same machine get
  separate state.

**This is a security prerequisite, not only a usability one.** Until it lands, `get_current_user`
does not reject an unauthenticated caller in local mode: it falls through to the OS username and
serves the request (`src/dockb/controllers/auth.py:116-121`). Since local mode is currently
*inferred* from the absence of provider credentials, and `.env.example` configures none, every
gated route answers anyone who can reach the port. `README_mcp_auth.md` §5 depends on this
changing before it opens a public listener, so it is sequenced before that work rather than
alongside it.

## 7. Decision: account lifecycle is admin-CLI only (decided)

Accounts are created, and passwords reset, by an admin-only command-line tool. There is no
self-registration and no recovery flow over HTTP. That removes, as a class:

- No `POST /api/auth/register` endpoint, and so no registration policy to decide or enforce.
- No email verification step.
- No password-reset token flow, no expiry on such a token, and no email delivery.
- No account-takeover surface reachable from a recovery path.

This is a deliberate fit for the current stage: DockB is a writing tool with a small, known set of
users, and a CLI is the right weight for administering it. Opening DockB to untrusted users would
require a hosted registration and recovery flow, and this decision would be revisited then.

### Password login, when it is added

Password sign-in is a later step, and is not implemented today. When it lands:

- Passwords are stored as **Argon2id** hashes (`argon2-cffi`), not salted SHA-256. The
  parameters come from OWASP's Password Storage Cheat Sheet. One dependency is worth it: the
  endpoint is eventually public, and PBKDF2 is CPU-cost-only, so a GPU cracks it far faster.
- The verification runs off the event loop. Argon2id is deliberately slow and memory-hard, and
  asyncio is cooperative and single-threaded: a blocking call in an `async def` route stalls
  every concurrent request for its full duration, whether or not it releases the GIL. The login
  route is therefore `async def` and offloads verification with
  `fastapi.concurrency.run_in_threadpool`, leaving the rest of `AuthService` synchronous as it is
  today.
- The not-found path verifies against a precomputed dummy hash, so that a request for a
  non-existent username costs the same as a wrong password. Skipping it is a reliable username
  oracle.
- Login is rate limited per username and per IP, with lockout or backoff. The federated flow never
  needed this — Google and GitHub did the throttling — and a password endpoint has to do it.
- The session cookie is tightened to `SameSite=Strict` for the password path. `state` and PKCE
  protect the federated flow from CSRF, but a password form has no equivalent, and the Electron
  shell loads the renderer from `file://`, a `null` origin that the CORS middleware admits
  (see §6).

## 8. Flow in full (reference)

1. The editor asks `GET /api/auth/config` and only shows the Sign-in gate when `login_required`
   is true. User clicks "Sign in"; the editor asks the backend for a login URL
   (`GET /api/auth/login?provider=google`), which returns the provider consent URL with `state` and
   a PKCE `code_verifier` the backend remembers.
2. The editor opens that URL in the system browser; the user consents.
3. Provider redirects to `http://localhost:{OAUTH_CALLBACK_PORT}/callback?...&code=...`.
4. The backend verifies `state`, exchanges the code (with `code_verifier`), stores the encrypted
   refresh token, upserts the user, and sets its own HttpOnly session cookie.
5. The editor reads that session; every API call after carries it. `GET /api/app/state` and
   `PUT /api/app/state` are then per-user as the UI record requires; `GET /api/auth/me` returns the
   signed-in user's profile and doubles as a session check from the editor.

## 9. Open questions

None at present.

## 10. Resolved questions

Settled while the design was implemented, or decided since:

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
- **Explicit local mode** — local mode is `DOCKB_LOCAL_MODE=true`, never inferred from absent
  provider configuration (§6).
- **Account linking** — not supported. Every provider account, and every password account, is its
  own `users` row, and accounts are never merged by email. Linking on a verified email is an
  account-takeover vector: an attacker registers the victim's address first, and when the victim
  later signs in with a federated provider under that same address, a naive merge hands them the
  attacker's account. Doing no linking means the vector does not exist; the cost is that one person
  using two providers has two accounts.
- **Machine-to-machine credentials are separate from user accounts** — the MCP server's service
  credential is not a user account and never appears in `users`. It is a per-prompt bearer token
  held in memory, and is documented in `README_mcp_auth.md`.
