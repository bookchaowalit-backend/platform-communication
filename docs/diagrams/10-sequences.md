# 10 — Sequences

## S1 — Queue a message (`POST /v1/messages`)

```mermaid
sequenceDiagram
  participant C as Caller
  participant B as core _Boundary
  participant A as app.create
  participant V as TokenVerifier
  participant S as OutboxStore
  participant DB as PostgreSQL
  C->>B: POST /v1/messages, Bearer JWT, Idempotency-Key
  B->>B: body <= 32768 bytes, 30 s timeout
  B->>A: request
  A->>V: verify(authorization)
  V-->>A: Principal(actor, workspace, scopes) or 401
  A->>A: scope messages:write else 403
  A->>A: adapter for channel configured? else 503
  A->>S: create(workspace, key, ...)
  S->>S: validate key, recipient, body, template, attempts, subject (422)
  S->>DB: BEGIN, set app.workspace_id, advisory lock message-capacity
  S->>DB: INSERT ... ON CONFLICT (workspace_id,event_key) DO NOTHING
  S->>DB: UPDATE status suppressed if opted out
  S->>DB: SELECT row and fingerprint
  alt fingerprint differs
    S-->>A: Conflict to 409
  else active rows > 10000
    S-->>A: QueueFull to 429
  else
    S-->>A: row
    A-->>C: 202 with id, status, attempts
  end
```

## S2 — Worker delivers one message

```mermaid
sequenceDiagram
  participant W as DeliveryWorker
  participant S as OutboxStore
  participant DB as PostgreSQL
  participant P as Provider
  W->>S: claim(workspace)
  S->>DB: expired sending to uncertain, opted-out queued to suppressed, expired lease at max to dead
  S->>DB: SKIP LOCKED pick, status leased, attempts + 1, lease 30 s
  S-->>W: message or None (sleep 0.5 s)
  W->>S: mark_sending(id, lease_token)
  S->>DB: opted out? to suppressed, attempts - 1
  S->>DB: leased to sending
  alt suppressed or lost lease
    S-->>W: False (skip)
  else
    W->>P: adapter.send (HTTPS, 5 s, no redirect)
    alt 2xx with provider id
      P-->>W: id
      W->>S: finish delivered
    else 429
      W->>S: finish retry to queued with backoff, or dead at max
    else 4xx
      W->>S: finish dead
    else 403 blocked by the user (Telegram)
      W->>S: record_opt_out provider.blocked
      W->>S: finish dead
    else 5xx, redirect, timeout, bad body
      W->>S: finish uncertain
    end
  end
```

## S3 — One-click unsubscribe

```mermaid
sequenceDiagram
  participant M as Mail client
  participant A as app.unsubscribe
  participant K as Keys
  participant S as OutboxStore
  participant DB as PostgreSQL
  M->>A: POST /v1/unsubscribe?t=token, body List-Unsubscribe=One-Click
  A->>A: body exact? else 400 page
  A->>S: unsubscribe(token)
  S->>K: read_unsubscribe_token
  K-->>S: (workspace, message_id) or None to 404 page
  S->>DB: get message in that workspace, must be email
  S->>DB: INSERT opt-out email.list_unsubscribe event unsubscribe:<id>
  A-->>M: 200 page You are unsubscribed (no-store, CSP)
```

## S4 — Readiness probe

```mermaid
sequenceDiagram
  participant U as Railway healthcheck / uptime worker
  participant A as core /readyz
  participant DB as PostgreSQL
  U->>A: GET /readyz
  A->>DB: SELECT 1
  A->>DB: outbox_schema: privileges, migration checksums, forced RLS, columns
  A->>A: delivery_adapters: any configured
  A-->>U: 200 ready or 503 unavailable
```

Sources: `src/platform_communication/app.py`, `store.py`, `worker.py`, `adapters.py`, `keys.py`, `__main__.py`, platform-backend-core `http.py`, `auth.py`, `db.py` at `21d5f44`, `.railway/railway.ts`, ops record: book-platforms-status (2026-11-03) (uptime worker hourly `/readyz`)
