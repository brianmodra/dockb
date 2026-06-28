# Session Infrastructure

Manages per-user session lifecycle on the server side.

## Package Structure

```
infrastructure/session/
├── README.md               # This file
├── __init__.py
├── token_validator.py      # OAuth token validation → account ID
└── session_manager.py      # Create/get/remove SessionContexts
```

## Components

### `TokenValidator`

Validates OAuth tokens from supported providers (Google, GitHub, etc.) and
extracts the authenticated account ID. Called once per request by middleware.

- `validate(token: str) -> str | None` — returns account ID or `None` if
  the token is invalid/expired.

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
