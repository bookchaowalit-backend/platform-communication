# 21 — Incident response

repo ไม่มี RUNBOOK; flow นี้ประกอบจากช่องทาง alert ที่มีจริง และกฎ rollback/reconcile ใน `docs/runtime.md`

```mermaid
flowchart TD
  A1["Uptime worker: /readyz not 200"] --> T
  A2["Sentry issue in platform-communication"] --> T
  A3["Caller sees 5xx / 503 Delivery unavailable"] --> T
  A4["Messages stuck queued / uncertain (no automatic alert)"] --> T
  T["Triage by owner"] --> D{"Which layer"}
  D -->|"/readyz 503"| R1["Check Neon (quota, suspend), migration history, runtime grants, adapter env"]
  D -->|"401 on every call"| R2["Check JWT_ISSUER, JWT_AUDIENCE, identity JWKS"]
  D -->|"Provider errors"| R3["Check provider key and status; dead vs uncertain"]
  D -->|"Code regression"| R4["Fix on branch, PR, CI green, merge locally"]
  R1 --> F
  R2 --> F
  R3 --> REC["uncertain: reconcile with provider logs, operator decides any new send"]
  R4 --> F["railway up --ci from git archive main"]
  F --> V["Verify /readyz 200 and sentry enabled log"]
  REC --> V
  V --> RB{"Still broken?"}
  RB -->|"yes"| ROLL["Rollback: stop runtime, restore consumers to previous adapter; never downgrade SQL"]
  RB -->|"no"| PM["Postmortem: not defined in repo"]
  ROLL --> PM
```

Sources: `docs/runtime.md` ("Verification and release gate", "Outbox API and workers"), `.railway/railway.ts`, `src/platform_communication/store.py` (`ready`), `src/platform_communication/app.py`, ops record: book-platforms-status (2026-11-03) (uptime worker, Sentry project, deploy recipe, Neon resume behaviour)

## Open questions

- uptime worker และ Sentry แจ้งเตือนผ่านช่องทางใด (Telegram?) สำหรับ service นี้: ไม่อยู่ใน repo หรือ ops record
- template postmortem และที่เก็บ
- ขั้นตอน reconcile `uncertain` ต่อ provider
