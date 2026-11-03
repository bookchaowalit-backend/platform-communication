# 09 — ERD

schema มาจาก migration `0001`–`0003` ใน `src/platform_communication/migrations.py` (namespace `communication`) และตาราง history ของ core
ไม่มี foreign key ระหว่างตาราง: `message_opt_out` ผูกกับ `message_outbox` ด้วย `(workspace_id, recipient_hash)` และ channel (`channel IN (m.channel, '*')`) ใน SQL `OPTED_OUT`

```mermaid
erDiagram
  message_outbox {
    uuid workspace_id PK "RLS key"
    uuid id PK
    text event_key "UNIQUE with workspace_id = Idempotency-Key"
    text fingerprint "sha256 of canonical payload"
    text channel "email sms push telegram"
    text recipient "raw address, needed to send"
    text recipient_hash "HMAC, NOT NULL (0003)"
    text subject "nullable, 1..200, email only (0002)"
    text body
    text template "plain or html"
    text status "queued leased sending delivered dead uncertain suppressed"
    int attempts
    int max_attempts "1..10"
    timestamptz run_at
    uuid lease_token
    timestamptz lease_until
    text provider_id
    timestamptz created_at
  }
  message_opt_out {
    uuid workspace_id PK "RLS key"
    text channel PK "* email sms push telegram"
    text recipient_hash PK "HMAC only, no address"
    text source "owner.global email.list_unsubscribe provider.blocked"
    text event_id "UNIQUE with workspace_id"
    timestamptz created_at
  }
  platform_schema_migrations {
    text namespace PK
    text version PK
    text checksum
    timestamptz applied_at
  }
  message_outbox }o--o{ message_opt_out : "suppressed when hash and channel match"
```

Sources: `src/platform_communication/migrations.py`, `src/platform_communication/store.py` (`OPTED_OUT`, `PUBLIC`, `ready`), platform-backend-core `src/platform_backend_core/migrations.py` at `21d5f44`

## Indexes, RLS and runtime role

| Table | Index | RLS | Runtime grants (`store.ready`) |
|---|---|---|---|
| `message_outbox` | `(workspace_id,status,run_at,id)`, `(workspace_id,created_at,id)` | ENABLE + FORCE, policy `workspace` USING + WITH CHECK | SELECT, INSERT, UPDATE |
| `message_opt_out` | `(workspace_id,recipient_hash)` | ENABLE + FORCE, policy `workspace` | SELECT, INSERT |
| `platform_schema_migrations` | PK | none (shared history) | SELECT |

- runtime role ต้องเป็น NOSUPERUSER NOBYPASSRLS (core `Database._configure`); schema `public` USAGE
- API ไม่คืน `recipient_hash`, `fingerprint`, `lease_token`, `provider_id`, `event_key` (`PUBLIC` column list) แต่คืน `recipient` และ `body`
- ไม่มี DELETE grant และไม่มี purge job: ข้อมูลอยู่ถาวรจนกว่า operator จัดการ (`docs/runtime.md`)

ภาพ ERD กลางของ architecture-docs ([ERD-DIAGRAMS.md](https://github.com/bookchaowalit/architecture-docs/blob/main/docs/architecture/ERD-DIAGRAMS.md)) ไม่มีตารางของ service นี้

## Open questions

- retention ของ `message_outbox.body` / `recipient` หลัง terminal: `docs/runtime.md` บอกให้ตั้งก่อน production แต่ยังไม่มีค่า
