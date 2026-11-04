# 16 — Deployment

```mermaid
flowchart LR
  subgraph DEV["Owner machine"]
    GA["git archive main"] --> RU["railway up --ci"]
  end
  subgraph RW["Railway, region asia-southeast1-eqsg3a, sleep on"]
    SVC["communication-api-production: Dockerfile, CMD serve, PORT 8080, UID 65532"]
    HC["healthcheckPath /readyz, timeout 30 s, restart ON_FAILURE x3"]
    WRK["worker service: not confirmed"]
  end
  subgraph NEON["Neon (own project per service)"]
    DB[("communication database")]
  end
  subgraph SEC["Infisical /platform-communication"]
    ENV["DATABASE_URL, COMMUNICATION_SECRET, JWT_ISSUER, JWT_AUDIENCE, JWT_JWKS_URL, SENTRY_DSN, provider keys"]
  end
  RU --> SVC
  SVC --- HC
  SVC --> DB
  WRK -.-> DB
  ENV -.-> SVC
  SVC --> IDP["identity-api-production-fad1 JWKS"]
  SVC --> SEN["Sentry project platform-communication"]
  UP["platform-uptime-worker hourly /readyz"] --> SVC
```

Sources: `railway.toml`, `Dockerfile`, `src/platform_communication/__main__.py`, `docs/runtime.md` (Staging plan), ops record: book-platforms-status (2026-11-03) (service name `communication-api-production`, region, sleep, `/readyz` 200 ~0.4 s warm, Neon `platform-<svc>`, Infisical `/platform-<svc>`, Sentry `platform-<svc>`, identity issuer `https://identity-api-production-fad1.up.railway.app`, uptime worker, CLI deploy of `bea8412`)

| Endpoint | Purpose |
|---|---|
| `/healthz` | liveness, no DB |
| `/readyz` | Railway healthcheck + uptime worker; DB, schema, RLS, privileges, at least one adapter |

## Open questions

- ~~public domain เต็มของ service~~ ตอบแล้ว 2026-11-04: `https://communication-api-production.up.railway.app` (platform-api-gateway `routes.json` @ `4a31ff5`, route `platform-communication`)
- `main` ปัจจุบันคือ `3a35541` (CI only) แต่ ops record ระบุ CLI deploy ล่าสุดที่ `bea8412`: commit ที่รันอยู่จริงคืออะไร
- Railway service สำหรับ `worker` และ `COMMUNICATION_WORKSPACE_ID` มีหรือยัง; migrate รันด้วย role ใด
- Railway sleep ทำให้ worker loop (poll 0.5 s) หลับด้วยหรือไม่ ถ้า deploy เป็น serverless
