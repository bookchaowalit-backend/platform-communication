# ADR-0003 — Railway serverless (Singapore) from the Dockerfile, deployed by CLI

- Status: accepted (retro-documented)
- Date of decision: 2026-10-29 (owner approved serverless for all new services; ops record: book-platforms-status (2026-11-03))
- Retro-documented: 2026-11-03

## Context

repo ไม่มี deploy workflow; CI สร้าง image เพื่อพิสูจน์ว่า build ได้เท่านั้น ("never pushes or deploys": `.github/workflows/shared-runtime.yml`)

## Decision

- `.railway/railway.ts`: builder `DOCKERFILE`, `healthcheckPath = "/readyz"`, timeout 30 s, restart `ON_FAILURE` max 3
- Dockerfile สองชั้น, runtime เป็น UID/GID 65532, `CMD python -m platform_communication serve`, `PORT=8080`
- service `communication-api-production` อยู่บน Railway region `asia-southeast1-eqsg3a` โดยเปิด sleep (serverless); deploy ด้วย `railway up --ci` จาก `git archive main` (ops record: book-platforms-status (2026-11-03), "Deploy recipe")
- Neon free project แยกต่อ service; core pool รอ resume ได้ (pool wait 20 s, connect timeout 15 s)

## Consequences

- push to `main` ไม่ deploy เอง; ประวัติ deploy ไม่อยู่ใน git/gh (ดู [22-dora](../22-dora.md))
- cold start หลัง sleep + Neon resume ~6–9 s (ops record, "Core fixes found in production")

## Evidence

`.railway/railway.ts`, `Dockerfile`, `.github/workflows/shared-runtime.yml`, `tests/test_build_hygiene.py`, `docs/runtime.md` "Container image", platform-backend-core `db.py` at `21d5f44`, ops record: book-platforms-status (2026-11-03)
