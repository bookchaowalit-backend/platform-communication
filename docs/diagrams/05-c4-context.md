# 05 — C4 Context

```mermaid
C4Context
  title platform-communication - System Context
  Person(owner, "Owner / Operator", "Runs migrate, worker, Railway deploys")
  Person(recipient, "Recipient", "Receives messages, may click unsubscribe")
  System_Ext(caller, "Calling services and agents", "Book Platform cells, remote MCP hub client mcp-hub")
  System_Ext(gw, "Edge API gateway", "gateway.bookchaowalit.com, route platform-communication")
  System(comm, "platform-communication", "Durable outbox API, delivery worker, opt-out store, one-click unsubscribe")
  System_Ext(identity, "platform-identity", "RS256 issuer, JWKS, audience communication-api")
  System_Ext(neon, "Neon PostgreSQL", "Dedicated database per service")
  System_Ext(resend, "Resend", "api.resend.com/emails")
  System_Ext(twilio, "Twilio", "api.twilio.com Messages")
  System_Ext(fcm, "Firebase Cloud Messaging", "fcm.googleapis.com v1")
  System_Ext(tg, "Telegram Bot API", "api.telegram.org sendMessage")
  System_Ext(sentry, "Sentry", "Error events, no free text")
  System_Ext(uptime, "platform-uptime-worker", "Hourly /readyz probe")

  Rel(caller, gw, "HTTPS JSON, Bearer JWT")
  Rel(gw, comm, "Proxy, token passed through")
  Rel(caller, comm, "Direct HTTPS, still allowed")
  Rel(caller, identity, "Gets tokens")
  Rel(comm, identity, "Fetches JWKS")
  Rel(comm, neon, "psycopg pool, RLS per workspace")
  Rel(comm, resend, "HTTPS POST")
  Rel(comm, twilio, "HTTPS POST")
  Rel(comm, fcm, "HTTPS POST")
  Rel(comm, tg, "HTTPS POST")
  Rel(comm, sentry, "Error events when SENTRY_DSN set")
  Rel(uptime, comm, "GET /readyz")
  Rel(owner, comm, "CLI: migrate, worker")
  Rel(recipient, comm, "GET/POST /v1/unsubscribe")
```

Sources: `src/platform_communication/adapters.py` (provider URLs), `src/platform_communication/__main__.py`, `src/platform_communication/_sentry.py`, `src/platform_communication/app.py`, `docs/runtime.md`, ops record: book-platforms-status (2026-11-03) (identity issuer + JWKS, audience `<svc>-api`, own Neon project `platform-<svc>`, uptime worker hourly `/readyz`, MCP hub cell `platform-<svc>`), ops record: api-gateway-edge (2026-11-03), platform-api-gateway `routes.json` @ `4a31ff5`

## Open questions

- channel ไหน configured จริงใน production (ops record ระบุว่า `RESEND_FROM` ยังเป็น owner follow-up; `/readyz` 200 แปลว่ามีอย่างน้อยหนึ่ง adapter configured)
- ~~edge API gateway มี route ไปยัง communication หรือไม่~~ ตอบแล้ว 2026-11-04: route `platform-communication` → `https://communication-api-production.up.railway.app` ใน platform-api-gateway `routes.json` @ `4a31ff5`
- caller ตัวไหนเรียกผ่าน gateway จริง: ops record ระบุ MCP hub ใช้ gateway; cells อื่นไม่ระบุ
