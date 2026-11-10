# Core 22 SDLC diagram pack — platform-communication

ชุดภาพ Core 22 ตาม SDLC Diagram Catalog v2 วาดจากโค้ดและ config ใน repo นี้ (ณ `origin/main` `3a35541`, 2026-11-03)
repo นี้คือ central platform service `communication`: durable outbox API (`/v1/messages`), opt-out store, one-click unsubscribe และ delivery worker
ไปยัง Resend / Twilio / FCM / Telegram; Python 3.12 + shared core `platform-backend-core` `21d5f44` + PostgreSQL (Neon)

ทุกไฟล์มี `Sources:` ใต้ภาพ และ "Open questions" สำหรับสิ่งที่ยืนยันจากโค้ดไม่ได้; ข้อเท็จจริง hosting ที่ไม่อยู่ใน repo อ้าง `ops record: book-platforms-status (2026-11-03)`

สรุปสถาปัตยกรรมระดับระบบ (style, quality attributes, integrations, fitness functions): [`DOCPACK/02-architecture.md`](../../DOCPACK/02-architecture.md)

| # | Item | Status | File | Sources read |
|---|---|---|---|---|
| 01 | Business process As-Is / To-Be | done | [01-business-process.md](01-business-process.md) | `app.py`, `store.py`, `worker.py`, `PRODUCT.md`, `docs/runtime.md`, BOO-150 gate |
| 02 | Use cases | done | [02-use-cases.md](02-use-cases.md) | `app.py`, `__main__.py`, core `http.py` / `auth.py`, ops record |
| 03 | User flows (API call flows) | done | [03-user-flows.md](03-user-flows.md) | `app.py`, `store.py`, `keys.py`, `adapters.py`, `docs/runtime.md` |
| 04 | Traceability (RTM) | done | [04-traceability.md](04-traceability.md) | BOO-150 gate, consumer contract, `docs/runtime.md`, `tests/`, `runtime_tests/`, workflows |
| 05 | C4 Context | done | [05-c4-context.md](05-c4-context.md) | `adapters.py`, `_sentry.py`, `__main__.py`, ops record |
| 06 | C4 Container | done | [06-c4-container.md](06-c4-container.md) | `Dockerfile`, `.railway/railway.ts`, `__main__.py`, core `db.py` |
| 07 | C4 Component | done | [07-c4-component.md](07-c4-component.md) | `src/platform_communication/*.py`, core `http.py`, `auth.py`, `db.py` |
| 08 | ADRs | done (5) | [08-adr/](08-adr/) | git log, `store.py`, `migrations.py`, `keys.py`, `_sentry.py`, `.railway/railway.ts`, ops record |
| 09 | ERD | done | [09-erd.md](09-erd.md) | `migrations.py`, `store.py`, core `migrations.py` |
| 10 | Sequences | done (4) | [10-sequences.md](10-sequences.md) | `app.py`, `store.py`, `worker.py`, `keys.py`, core `http.py` |
| 11 | State machines | done | [11-state-machines.md](11-state-machines.md) | `store.py`, `worker.py`, `migrations.py` |
| 12 | API & integrations | done | [12-api-integration.md](12-api-integration.md) | `app.py`, `store.py`, `adapters.py`, core `http.py` |
| 13 | Threat model | done | [13-threat-model.md](13-threat-model.md) | `src/`, core, `.railway/railway.ts`, `Dockerfile`, workflows |
| 14 | Backup & DR | done (backup not found) | [14-backup-dr.md](14-backup-dr.md) | `docs/runtime.md`, `keys.py`, workflows, ops record |
| 15 | CI/CD pipeline | done | [15-cicd-pipeline.md](15-cicd-pipeline.md) | `.github/workflows/*.yml`, platform-ci-workflows `ci-python.yml` / `security.yml` @ `87dc5e1c` |
| 16 | Deployment | done | [16-deployment.md](16-deployment.md) | `.railway/railway.ts`, `Dockerfile`, `docs/runtime.md`, ops record |
| 17 | Test coverage matrix | done | [17-test-coverage-matrix.md](17-test-coverage-matrix.md) | `tests/`, `runtime_tests/`, `pyproject.toml`, `check.yml` |
| 18 | Git & release workflow | done | [18-git-release-workflow.md](18-git-release-workflow.md) | `git log --first-parent`, `gh pr list` |
| 19 | Service dependency map | done | [19-service-dependency-map.md](19-service-dependency-map.md) | `src/`, `pyproject.toml`, `uv.lock`, `contract.json` |
| 20 | Observability | done | [20-observability.md](20-observability.md) | `_sentry.py`, `__main__.py`, core `http.py`, `.railway/railway.ts`, ops record |
| 21 | Incident response | done | [21-incident-response.md](21-incident-response.md) | `docs/runtime.md`, `.railway/railway.ts`, ops record |
| 22 | DORA | done (proxies; production deploys not computable) | [22-dora.md](22-dora.md) | `git log`, `gh run list`, `gh pr list`, ops record |

## ADR list

- [ADR-0001](08-adr/ADR-0001-durable-outbox-with-leases.md) Durable PostgreSQL outbox with leases; ambiguous sends never retried
- [ADR-0002](08-adr/ADR-0002-own-database-forced-rls-workspace-jwt.md) Own database, forced RLS, workspace from JWT `ws`
- [ADR-0003](08-adr/ADR-0003-railway-serverless-docker-cli-deploy.md) Railway serverless (Singapore), Dockerfile, CLI deploy
- [ADR-0004](08-adr/ADR-0004-keyed-hash-opt-out-before-send.md) Opt-out before send, keyed HMAC hashes, one-click unsubscribe
- [ADR-0005](08-adr/ADR-0005-sentry-no-free-text.md) Sentry errors only, no free text

## Existing docs reused (linked, not copied)

- [`docs/runtime.md`](../runtime.md) — runtime, staging plan, verification records
- [`docs/CONTRACT-SURFACE.md`](../CONTRACT-SURFACE.md), [`docs/UPGRADE-PLAN.md`](../UPGRADE-PLAN.md), [`docs/gates/BOO-150-communication-delivery-gate.md`](../gates/BOO-150-communication-delivery-gate.md)
- Central: [C4-DIAGRAMS.md](https://github.com/bookchaowalit/architecture-docs/blob/main/docs/architecture/C4-DIAGRAMS.md), [ERD-DIAGRAMS.md](https://github.com/bookchaowalit/architecture-docs/blob/main/docs/architecture/ERD-DIAGRAMS.md), [ATTACK-PATH-DIAGRAMS.md](https://github.com/bookchaowalit/architecture-docs/blob/main/docs/architecture/ATTACK-PATH-DIAGRAMS.md) (ไม่มี service นี้โดยตรง)

## Findings worth the owner's attention

- เอกสารใน repo (`README.md`, `PRODUCT.md`, `contract.json` status `scaffolded`, "Sentry does not apply", "not deployed") ขัดกับ ops record ที่ระบุว่า `communication-api-production` live และมี Sentry (ดู 01, 16)
- consumer contract ที่ owner accept (BOO-150) อธิบาย `POST /v1/notifications` + `dedupe_key` + `recipient_ref` แต่ runtime ให้ `POST /v1/messages` + `Idempotency-Key` + raw `recipient`; ไม่มี compatibility adapter (ดู 04)
- worker / startup errors ไม่ถึง Sentry: `__main__` แปลงทุก exception เป็น `SystemExit` และ `capture()` ไม่ถูกเรียก (ดู 20)
- ยังไม่ยืนยันว่ามี Railway service `worker`: ถ้าไม่มี ทุกข้อความค้าง `queued` (ดู 06, 16)
- ไม่พบ backup / restore drill ของ Neon project นี้; RTO/RPO not defined (ดู 14)
- `/metrics`, `/docs`, `/openapi.json` เปิดไม่ต้อง auth (ดู 12, 13)
- `contract.json` `depends_on` `workflow`, `observability` ไม่มีการเรียกในโค้ด (ดู 19)

Validate: `node ~/work/core22/tools/validate.mjs docs/diagrams/*.md docs/diagrams/08-adr/*.md`
