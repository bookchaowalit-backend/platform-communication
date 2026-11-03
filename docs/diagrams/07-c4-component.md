# 07 — C4 Component

```mermaid
C4Component
  title platform-communication serve and worker - Components
  Container_Boundary(api, "serve / worker process") {
    Component(boundary, "core _Boundary", "platform_backend_core.http", "Body limit 32768 bytes, 30 s timeout, x-request-id, redacted 500, route metrics")
    Component(capture, "CaptureErrors", "_sentry.py", "Innermost ASGI layer, reports then re-raises")
    Component(routes, "Routes", "app.py", "messages, opt-outs, unsubscribe, exception handlers 409/422/429")
    Component(scope, "require_scope", "platform_backend_core.http", "TokenVerifier.verify, 401 / 403")
    Component(verifier, "TokenVerifier", "platform_backend_core.auth", "RS256, issuer, audience, sub ws jti")
    Component(store, "OutboxStore", "store.py", "create, list, get, claim, mark_sending, finish, record_opt_out, unsubscribe, ready")
    Component(keys, "Keys", "keys.py", "HMAC recipient hash and unsubscribe token from COMMUNICATION_SECRET")
    Component(adapters, "Adapters", "adapters.py", "ResendAdapter, TwilioAdapter, FCMAdapter, TelegramAdapter")
    Component(worker, "DeliveryWorker", "worker.py", "run_one(workspace)")
    Component(dbc, "Database", "platform_backend_core.db", "Pool, set_config app.workspace_id per transaction")
  }
  ContainerDb(pg, "PostgreSQL")
  System_Ext(prov, "Providers")
  Rel(boundary, capture, "wraps")
  Rel(capture, routes, "wraps")
  Rel(routes, scope, "Depends")
  Rel(scope, verifier, "verify")
  Rel(routes, store, "calls")
  Rel(store, keys, "recipient_hash, read_unsubscribe_token")
  Rel(worker, store, "claim, mark_sending, finish")
  Rel(worker, adapters, "send")
  Rel(adapters, keys, "unsubscribe_token")
  Rel(adapters, prov, "HTTPS")
  Rel(store, dbc, "transaction(workspace)")
  Rel(dbc, pg, "SQL")
```

Sources: `src/platform_communication/app.py`, `store.py`, `keys.py`, `adapters.py`, `worker.py`, `_sentry.py`, `errors.py`, platform-backend-core `http.py`, `auth.py`, `db.py` at `21d5f44`
