# SPEC-001 — Delivery worker serves every workspace

Standard: ADR-0004 — TDD + SDD.

| Field | Value |
|---|---|
| Spec ID / version | SPEC-001 / 0.1 |
| Status | **draft**, waiting for owner approval |
| Repository / path | bookchaowalit-backend/platform-communication / `docs/SPEC-001-MULTI-WORKSPACE-WORKER.md` |
| Owner (maker) | Claude Code |
| Approver | Owner (bookchaowalit) |
| Requirement links | SaaS gap review 2026-11-11, item 2 (workers pinned to one workspace); platform-identity SPEC-006 (tenants now exist) |
| Main-only | no: branch → PR, merged locally |
| Created / approved | 2026-11-13 / — |

## 1. Problem and intent

- **Problem:** `python -m platform_communication worker` reads `COMMUNICATION_WORKSPACE_ID` and drains only
  that workspace. The runtime role sees one workspace at a time through RLS. Since SPEC-006, customers create
  their own workspaces. A message queued by a second customer is accepted (202) but never sent.
- **Outcome:** every cron run delivers due messages and applies retention for **every** workspace that has
  work, fairly, with no change to the API.

## 2. Scope

| In scope | Out of scope |
|---|---|
| Worker finds workspaces with due or redactable messages and drains each | Always-on polling (stays a cron job, Neon quota) |
| Fair share: at most `COMMUNICATION_PER_WORKSPACE_BATCH` (default 100) messages per workspace per pass, total cap 500 per run | Per-workspace quotas or billing |
| `COMMUNICATION_WORKSPACE_ID` becomes an optional filter (rollback) | Changing the API, adapters, or outbox schema |

## 3. Scenarios

- **AC-01 — All workspaces with due messages are served.** Given due messages in W1 and W2, when one
  `worker --until-empty` run executes, then both are delivered and the heartbeat counts both.
  Test: `runtime_tests/test_worker_workspaces.py::test_run_serves_every_workspace`.
- **AC-02 — Discovery reveals ids only.** A SECURITY DEFINER function `communication_due_workspaces(limit)`
  returns workspace ids that have a claimable message (queued and due, or leased with an expired lease) or
  redactable content. It returns nothing else and is executable only by the runtime role. The runtime role
  keeps RLS for every table read. Test: `::test_discovery_function_returns_ids_only_and_is_not_public`.
- **AC-03 — Fair share.** Given 300 due messages in W1 and 5 in W2, with a per-workspace batch of 100, W2's
  5 are sent in the first pass. Passes repeat until the 500-per-run cap, and W1 is not starved.
  Test: `::test_one_busy_workspace_does_not_starve_another`.
- **AC-04 — Retention per workspace.** Content past `COMMUNICATION_RETENTION_DAYS` is cleared in each
  workspace that has such content. Test: `::test_retention_runs_per_workspace`.
- **AC-05 — Optional filter (rollback).** With `COMMUNICATION_WORKSPACE_ID` set, only that workspace is
  served, as today. Test: `::test_env_filter_limits_to_one_workspace`.
- **AC-06 — One workspace failing does not stop the others.** An adapter error in W1 still lets W2 be
  served. The run exits non-zero only after all workspaces are tried, and the heartbeat reports failure.
  Test: `::test_failure_in_one_workspace_does_not_block_others`.

## 4. Interfaces and data

- New migration: `communication_due_workspaces(p_limit int) RETURNS SETOF uuid`. It is SECURITY DEFINER,
  `search_path = pg_catalog, pg_temp`, `REVOKE ALL FROM PUBLIC`, `GRANT EXECUTE` to `communication_runtime`.
  It is owned by a NOLOGIN NOBYPASSRLS owner role with a SELECT-only policy, the same pattern as
  platform-empire 0009.
- Env: `COMMUNICATION_WORKSPACE_ID` becomes optional; new `COMMUNICATION_PER_WORKSPACE_BATCH` (1..500,
  default 100).
- Backward compatible: deploying with the existing variable set behaves exactly as today. Removing the
  variable turns on all-workspace mode.

## 5. NFR

| NFR | Target |
|---|---|
| Neon cost | one discovery query per pass; no new always-on process |
| Privacy | logs carry counts only, no workspace ids, recipients or bodies (unchanged rule) |
| Reliability | heartbeat semantics unchanged; failure = any workspace failed |

## 6. Test plan

Runtime tests against a throwaway `postgres:17-alpine`, as the real runtime role, red first.

## 7. Open questions

| # | Question | Owner |
|---|---|---|
| 1 | Default per-workspace batch: 100 (proposed) | Owner |
| 2 | Remove `COMMUNICATION_WORKSPACE_ID` from Railway at deploy, or keep it until a second customer exists | Owner |
