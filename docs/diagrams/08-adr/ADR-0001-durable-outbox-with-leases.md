# ADR-0001 — Durable PostgreSQL outbox with leases; ambiguous sends are never retried

- Status: accepted (retro-documented)
- Date of decision: 2026-10-29 (runtime merged to `main` in `db278a3`, PR #1 branch `codex/shared-infrastructure-20261015`)
- Retro-documented: 2026-11-03

## Context

caller ต้องการ "ส่งแล้วไม่หาย" และไม่ส่งซ้ำโดยไม่ตั้งใจ แต่ provider ส่วนใหญ่ (Telegram, Twilio, FCM) ไม่มี idempotency key ฝั่ง provider
(BOO-150 gate: "Retries can duplicate on non-idempotent providers")

## Decision

- `POST /v1/messages` เขียน row ลง `message_outbox` ใน transaction แล้วตอบ 202; idempotency ด้วย `UNIQUE(workspace_id, event_key)` + fingerprint (409 เมื่อ payload ต่าง)
- worker `claim` ด้วย `FOR UPDATE SKIP LOCKED` + lease token 30 s; บันทึก `sending` ก่อน provider I/O; `finish` ต้องมี lease token ที่ยังไม่หมดอายุ
- `sending` ที่ lease หมดอายุกลายเป็น `uncertain` และไม่ถูกส่งซ้ำอัตโนมัติ; 5xx, redirect, timeout, response เสีย = `uncertain`; 429 = retry; 4xx อื่น = dead
- retry backoff `least(3600, 2^attempts)` วินาที; `max_attempts` default 3 (1..10)
- Resend ได้ `Idempotency-Key: message/<uuid>` ทุก attempt

## Consequences

- ไม่มี exactly-once; operator ต้อง reconcile `uncertain` กับ provider log
- ไม่มี manual retry API (ตั้งใจ เพื่อไม่ให้ส่งซ้ำเงียบๆ)
- queue cap 10,000 active rows ต่อ workspace ป้องกัน table โตไม่จำกัด

## Evidence

`src/platform_communication/store.py` (`create`, `claim`, `mark_sending`, `finish`), `src/platform_communication/adapters.py` (`HTTPAdapter.request`, `ResendAdapter.send`), `src/platform_communication/migrations.py` (0001), `runtime_tests/test_runtime.py`, `docs/runtime.md` "Outbox API and workers", `git log` `db278a3`
