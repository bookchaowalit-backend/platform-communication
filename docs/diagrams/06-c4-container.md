# 06 — C4 Container

image เดียว (`Dockerfile`) รันได้ 3 คำสั่ง: `serve`, `worker`, `migrate` (`src/platform_communication/__main__.py`)

```mermaid
C4Container
  title platform-communication - Containers
  System_Ext(caller, "Caller", "Bearer JWT")
  System_Ext(gw, "Edge API gateway", "gateway.bookchaowalit.com")
  Person(recipient, "Recipient")
  System_Ext(identity, "platform-identity JWKS", "/.well-known/jwks.json")
  System_Ext(providers, "Providers", "Resend, Twilio, FCM, Telegram")
  System_Ext(sentry, "Sentry")
  Container_Boundary(b, "platform-communication") {
    Container(api, "communication serve", "Python 3.12, FastAPI, uvicorn", "API on PORT 8080, limit_concurrency 100")
    Container(worker, "communication worker", "Python 3.12", "Railway cron */30: worker --until-empty drains COMMUNICATION_WORKSPACE_ID and exits")
    Container(migrate, "communication migrate", "Python 3.12 one-off", "MigrationRunner namespace communication, DDL role")
    ContainerDb(db, "PostgreSQL", "Neon, PG 16+", "message_outbox, message_opt_out, platform_schema_migrations")
  }
  Rel(caller, gw, "HTTPS /v1/platform-communication/...")
  Rel(gw, api, "Proxy")
  Rel(caller, api, "Direct HTTPS /v1/messages, /v1/opt-outs")
  Rel(recipient, api, "/v1/unsubscribe")
  Rel(api, identity, "JWKS fetch, 5 s timeout, no redirect")
  Rel(api, db, "Runtime role, pool max 8, statement timeout 10 s")
  Rel(worker, db, "Runtime role, claim with SKIP LOCKED")
  Rel(worker, providers, "HTTPS, 5 s, no redirect, max 64 KiB")
  Rel(migrate, db, "DDL role")
  Rel(api, sentry, "Errors")
```

Sources: `Dockerfile`, `.railway/railway.ts`, `src/platform_communication/__main__.py`, `src/platform_communication/app.py`, `src/platform_communication/worker.py`, `src/platform_communication/adapters.py`, `src/platform_communication/_sentry.py`, `docs/runtime.md`, platform-backend-core `src/platform_backend_core/db.py`, `auth.py`, `migrations.py` at `21d5f44`, platform-api-gateway `routes.json` @ `4a31ff5`

## Open questions

- ~~ไม่ยืนยันว่ามี Railway service สำหรับ `worker`~~ 2026-11-10: Railway cron `communication-worker` ทุก 30 นาที
- worker ไม่มีเส้นทางส่ง error ไป Sentry ที่หาเจอในโค้ด: `__main__.main` แปลงทุก exception เป็น `SystemExit` (Python ไม่เรียก excepthook สำหรับ `SystemExit`) และ `_sentry.capture()` ไม่ถูกเรียกที่ใด (ดู [20](20-observability.md))
- worker ไม่มี HTTP port: ตรวจด้วย uptime heartbeat `communication-worker` (2 ชม., `_heartbeat.py`) แทน healthcheck
