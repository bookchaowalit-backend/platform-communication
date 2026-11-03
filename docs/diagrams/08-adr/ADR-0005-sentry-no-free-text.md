# ADR-0005 — Sentry errors only, with no free text

- Status: accepted (retro-documented). Shipped `9c69f81` / merge `bea8412` (PR #18, 2026-11-03)
- Retro-documented: 2026-11-03

## Context

PR #5–#17 (2026-11-02 → 2026-11-03) พยายาม scrub ด้วย pattern แต่ review รอบต่อๆ ไปหาทาง bypass ได้เสมอ (`_sentry.py` docstring);
service นี้ถือ email, เบอร์โทร, chat id

## Decision

- `SENTRY_DSN` ว่าง = ไม่ส่งอะไร; มี DSN = errors only (`traces_sample_rate=None`, `trace_propagation_targets=[]`, `send_default_pii=False`, `include_local_variables=False`, `max_request_body_size="never"`)
- `before_send` ลบ exception value, message, logentry, breadcrumbs, extra, user, dynamic sampling context; request เหลือแค่ method
- `LoggingIntegration(level=None, event_level=None)`: log ไม่กลายเป็น event
- `CaptureErrors` เป็น middleware ชั้นในสุด เพราะ core `_Boundary` กลืน exception เป็น 500 ก่อนถึง integration ชั้นนอก

## Consequences

- event มีแค่ type, stack, route, tags, release: debug ต้องอาศัย stack
- owner revert ได้ถ้าต้องการข้อความ (ops record: book-platforms-status (2026-11-03))

## Evidence

`src/platform_communication/_sentry.py`, `src/platform_communication/__init__.py`, `src/platform_communication/app.py`, `tests/test_sentry.py`, `runtime_tests/test_sentry_boundary.py`, `gh pr list` (#5–#18)
