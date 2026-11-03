# 18 — Git and release workflow

```mermaid
gitGraph
  commit id: "b87a0e9 scaffold 09-17"
  commit id: "dc3d2e0 BOO-149"
  branch boo-150-delivery-gate
  commit id: "gate fixtures"
  checkout main
  merge boo-150-delivery-gate id: "f6d3db9 PR 2"
  commit id: "adc7d68 PR 3"
  commit id: "ed7092c ci v1.1.1"
  branch codex-shared-infrastructure
  commit id: "runtime"
  checkout main
  merge codex-shared-infrastructure id: "db278a3 runtime (PR 1 merged locally)"
  commit id: "b78809e unsubscribe"
  commit id: "777ee3c core pin 21d5f44"
  commit id: "f4a0f3d sentry"
  branch fix-sentry
  commit id: "PR 5 to PR 17"
  checkout main
  merge fix-sentry id: "8b8f74b"
  commit id: "bea8412 PR 18 no free text"
  commit id: "3a35541 PR 19 uv lock"
```

```mermaid
flowchart LR
  A["Branch per change (fix/*, ci/*, boo-*)"] --> B["Push: check.yml + shared-runtime.yml"]
  B --> C["PR on GitHub, CI green"]
  C --> D["Merge locally into main, push (Merge PR #n)"]
  D --> E["CI on main"]
  E -.->|"manual"| F["git archive main + railway up --ci"]
  F --> G["Railway healthcheck /readyz"]
  G --> H["Owner checks /readyz 200 and Sentry enabled log"]
```

Sources: `git log --first-parent origin/main`, `gh pr list -R bookchaowalit-backend/platform-communication --state all` (#1 closed, #2–#3 and #5–#19 merged, #4 open), `.github/workflows/*.yml`, `railway.toml`, ops record: book-platforms-status (2026-11-03) (deploy recipe, "all CLI-deployed, /readyz 200, `sentry: enabled` logged")

- merge แบบ local แล้ว push (`Merge PR #n: ...`); PR #1 ถูก close บน GitHub หลัง merge local (`db278a3`)
- ไม่มี tag หรือ GitHub release; version ใน `pyproject.toml` ยังเป็น `0.1.0`
- PR #4 (`sentry-hardened-scrubber`) ยังเปิดค้าง ถูกแทนด้วย #5–#18

## Open questions

- มี branch protection / required checks บน `main` หรือไม่ (first-parent history มี commit ที่ไม่ใช่ merge เช่น `ed7092c`, `3a35541` (PR #19 แบบ fast-forward) จึงแยกไม่ได้จาก git ว่า push ตรงหรือผ่าน PR)
- ควรปิด PR #4 หรือไม่
