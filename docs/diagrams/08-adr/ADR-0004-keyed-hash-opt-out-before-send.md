# ADR-0004 — Opt-out enforced before send, stored as keyed HMAC hashes; one-click unsubscribe

- Status: accepted (retro-documented). Policy accepted by the owner 2026-10-16 (BOO-150); implemented 2026-10-29 (`db278a3`, `b78809e`)
- Retro-documented: 2026-11-03

## Decision

- `message_opt_out` เก็บเพียง `recipient_hash` (HMAC-SHA256 ของ address ที่ normalize; email เป็นตัวเล็ก) ไม่เก็บ address
- key สองตัว derive จาก `COMMUNICATION_SECRET` (≥ 32 ตัวอักษร): `recipient-hash` และ `unsubscribe-token`; `serve`/`worker` ไม่ start ถ้าไม่มี secret
- ตรวจ opt-out ตอน `create`, `claim`, `mark_sending`; สถานะ `suppressed` เป็น terminal และไม่นับ attempt
- แหล่ง opt-out: `owner.global`, `email.list_unsubscribe` (RFC 8058 POST, event `unsubscribe:<id>`), `provider.blocked` (Telegram 403, event `provider:<id>`); prefix ทั้งสองสงวนไว้
- link unsubscribe ถือ token (workspace id + message id + HMAC tag 128 bit) ไม่ถือ address; หน้าใช้ `no-store`, `no-referrer`, CSP `default-src 'none'`

## Consequences

- เปลี่ยน secret = opt-out เดิมใช้ไม่ได้ (ต้องมีแผน rehash)
- `message_outbox.recipient` ยังเก็บ address ตรงๆ เพื่อส่ง (มีเพียง opt-out ที่เป็น hash)

## Evidence

`src/platform_communication/keys.py`, `store.py`, `adapters.py`, `app.py`, `migrations.py` (0002, 0003), `runtime_tests/test_opt_out.py`, `runtime_tests/test_unsubscribe.py`, `docs/gates/BOO-150-communication-delivery-gate.md`, `docs/runtime.md`
