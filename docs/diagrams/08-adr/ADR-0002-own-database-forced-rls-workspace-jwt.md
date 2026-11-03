# ADR-0002 — Own PostgreSQL database per service, forced RLS, workspace from JWT `ws`

- Status: accepted (retro-documented)
- Date of decision: 2026-10-15 (correlation `SHARED-INFRA-2026-10-15`), shipped in `db278a3` (2026-10-29)
- Retro-documented: 2026-11-03

## Context

service นี้ถือ recipient (email, เบอร์โทร, chat id) ของหลาย workspace; README กำหนดว่า consumer ห้าม import database หรือ module ของ platform อื่น

## Decision

- ใช้ shared core `platform-backend-core` ที่ pin commit `21d5f44` (Dockerfile, `pyproject.toml` `[tool.uv.sources]`, CI ต้องตรงกัน: `tests/test_build_hygiene.py`)
- ทุก table มี `workspace_id` + `ENABLE` และ `FORCE ROW LEVEL SECURITY` + policy `workspace_id = current_setting('app.workspace_id')`
- `Database.transaction(workspace)` ตั้ง `app.workspace_id` จาก principal ที่ verify แล้วเท่านั้น; body/header ไม่เลือก tenant
- runtime role ต้องเป็น NOSUPERUSER NOBYPASSRLS (core `_configure` ปฏิเสธ connection ถ้าไม่ใช่); migration แยกเป็นคำสั่ง `migrate` ด้วย DDL role
- `/readyz` ตรวจ privilege ทีละตัว, migration checksum และ RLS
- database แยกต่อ service: ops record: book-platforms-status (2026-11-03) "Each service has its own free Neon project `platform-<svc>`"

## Consequences

- worker ต้องระบุ `COMMUNICATION_WORKSPACE_ID` ต่อ process: ไม่มี reader ข้าม tenant; หลาย workspace = หลาย worker
- การ grant runtime role เป็นงาน operator นอก repo

## Evidence

`src/platform_communication/migrations.py`, `src/platform_communication/store.py` (`ready`), `src/platform_communication/__main__.py`, platform-backend-core `db.py`, `auth.py` at `21d5f44`, `docs/runtime.md`, `runtime_tests/test_http.py`, `runtime_tests/test_runtime.py::test_outbox_force_rls_rejects_foreign_write_and_stale_finish`
