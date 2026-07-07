# Session Infrastructure

Manages per-user session lifecycle on the server side.

## Package Structure

```
infrastructure/session/
├── README.md               # This file
├── __init__.py
├── token_validator.py      # OAuth token validation → account ID
├── user_store.py           # Persistent OAuth user profile storage (TinyDB)
└── session_manager.py      # Create/get/remove SessionContexts
```

## Components

### `TokenValidator`

Validates OAuth tokens from supported providers (Google, GitHub, etc.) and
extracts the authenticated account ID. Called once per request by middleware.

- `validate(token: str) -> str | None` — returns account ID or `None` if
  the token is invalid/expired.

### `UserStore`

Persists OAuth user profile information using [TinyDB](https://tinydb.readthedocs.io/) —
a lightweight, pure-Python document database stored as a JSON file. Kept separate from
Neo4j because auth metadata does not belong in the document graph.

- `get(account_id) -> UserInfo | None` — lookup by account ID
- `upsert(account_id, UserInfo)` — create or update user profile
- `list_all() -> list[UserInfo]` — admin/prometheus endpoint support

Stored fields:

| Field           | Type  | Description                        |
|-----------------|-------|------------------------------------|
| `account_id`    | str   | Unique account ID (primary key)    |
| `provider`      | str   | OAuth provider (google, github…)   |
| `email`         | str   | Verified email from provider       |
| `display_name`  | str   | User-facing name                   |
| `avatar_url`    | str   | Profile photo URL                  |
| `created_at`    | float | First-login timestamp (Unix epoch) |
| `last_login_at` | float | Most-recent-login timestamp        |

The `account_id` is the same value returned by `TokenValidator.validate()`. On first
login a new doc is inserted; on subsequent logins `last_login_at` (and optionally
`display_name` / `avatar_url`) are updated.

TinyDB is configured with a JSON file path from settings (default:
`~/.dockb/users.json`). The JSON file is safe to inspect and back up.

### `SessionManager`

Long-lived singleton that owns all active `SessionContext` instances, keyed by
account ID.

- `get(account_id) -> SessionContext | None` — lookup
- `create(account_id) -> SessionContext` — create new context
- `remove(account_id)` — destroy context (logout / timeout)

### `SessionContext`

Per-user state bundle kept for the duration of the session. Lives in
`services/session_context.py` (not in the infrastructure layer) because it
orchestrates services-level constructs.

Contains:
- **JobQueue** — semantic processing queue (ReconstructJob, DeleteJob)
- **DocCache** — spaCy Doc objects with TTL eviction
- **Notification queue** — pending async notifications (e.g. sentence split
  results) delivered to the client piggy-back on the next response or via
  `GET /api/notifications` poll.

## Lifecycle

```
Request → TokenValidator.validate(token)
           ↓ account_id
         SessionManager.get(account_id)
           ↓ create if missing
         SessionContext ← JobQueue, DocCache, Notification queue
```

Session is torn down on logout or expiry via `SessionManager.remove()`.
