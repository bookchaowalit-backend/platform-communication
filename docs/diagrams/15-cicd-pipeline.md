# 15 — CI/CD pipeline

```mermaid
flowchart TD
  EV["push (any branch), pull_request, workflow_dispatch"] --> CHK["check.yml: Check"]
  EV --> SR["shared-runtime.yml: Shared runtime"]
  subgraph CHK_JOBS["Check jobs (parallel, no needs)"]
    C1["contract: matrix Python 3.11, 3.12"]
    C2["python: ci-python.yml @87dc5e1c v1.1.1"]
    C3["security: security.yml @87dc5e1c v1.1.1"]
  end
  CHK --> C1
  CHK --> C2
  CHK --> C3
  C1 --> C1a["checkout + checkout platform-notifications-api @57dd097"]
  C1a --> C1b["check_schema_pin.py"]
  C1b --> C1c["scripts/check.sh with REQUIRE_SERVER_PARITY=1"]
  C2 --> C2a["uv sync --frozen --all-extras"]
  C2a --> C2b["Start PostgreSQL"]
  C2b --> C2c["Ruff lint"]
  C2c --> C2d["mypy"]
  C2d --> C2e["pytest --cov with PLATFORM_TEST_DSN, then uv build --wheel"]
  C2e --> C2f["Coverage gate 90 percent"]
  C3 --> C3a["gitleaks"]
  C3 --> C3b["semgrep"]
  C3 --> C3c["osv-scanner"]
  C3 --> C3d["trivy-fs"]
  SR --> I1["image: docker build --pull (no push)"]
  I1 --> I2["import check + non-root check"]
  C2f -.->|"no deploy job"| DEP["Manual: railway up --ci from git archive main"]
  I2 -.-> DEP
```

Sources: `.github/workflows/check.yml`, `.github/workflows/shared-runtime.yml`, `bookchaowalit/platform-ci-workflows` `.github/workflows/ci-python.yml` and `security.yml` at `87dc5e1c`, ops record: book-platforms-status (2026-11-03) (deploy recipe)

- concurrency: `check-${{ github.ref }}` และ `shared-runtime-${{ github.ref }}` cancel-in-progress
- runner: GitHub-hosted (`ubuntu-latest` / shared default `ubuntu-24.04`) เพราะเป็น public repo
- `format-check: false` (follow-up: ruff format)

## Open questions

- ต้องการ deploy job (หรือ Railway GitHub source) แทน CLI หรือไม่
