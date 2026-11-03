# 11 — State machines

## `message_outbox.status`

```mermaid
stateDiagram-v2
  [*] --> queued: create (POST /v1/messages)
  queued --> suppressed: create or claim, recipient opted out
  queued --> leased: claim, attempts + 1, lease 30 s
  leased --> sending: mark_sending, lease valid
  leased --> suppressed: mark_sending or claim, opted out (attempt given back)
  leased --> leased: claim after lease expired (presend recovery)
  leased --> dead: claim, lease expired and attempts >= max_attempts
  sending --> delivered: finish delivered
  sending --> queued: finish retry, attempts < max_attempts (backoff)
  sending --> dead: finish retry at max, or finish dead
  sending --> uncertain: finish uncertain, or lease expired while sending
  delivered --> [*]
  dead --> [*]
  suppressed --> [*]
  uncertain --> [*]: operator reconciles, no automatic resend
```

Sources: `src/platform_communication/store.py` (`create`, `claim`, `mark_sending`, `finish`), `src/platform_communication/worker.py`, `src/platform_communication/migrations.py` (status CHECK in 0001 and 0002), `docs/runtime.md`

- status ที่นับเป็น queue capacity: `queued`, `leased`, `sending`, `uncertain`
- worker ส่ง outcome `dead` ทันทีถ้า adapter ของ channel ไม่ configured (`worker.py`)

## Opt-out record (`message_opt_out`)

```mermaid
stateDiagram-v2
  [*] --> active: record_opt_out created (201)
  active --> active: same event_id or same address replayed (200 existing)
  active --> active: event_id reused for another address (409, nothing written)
```

ไม่มี route หรือคำสั่งลบ opt-out (ไม่มี DELETE grant ใน `store.ready`)

Sources: `src/platform_communication/store.py` (`record_opt_out`), `src/platform_communication/app.py`

## Open questions

- กระบวนการ reconcile `uncertain` ของ operator ยังไม่มี runbook ใน repo
- ต้องการทางยกเลิก opt-out (re-subscribe) หรือไม่
