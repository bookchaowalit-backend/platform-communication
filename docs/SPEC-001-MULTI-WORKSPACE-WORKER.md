# SPEC-001 — Delivery worker serves every workspace

Standard: ADR-0004 — TDD + SDD.

| Field | Value |
|---|---|
| Spec ID / version | SPEC-001 / 0.3 |
| Status | **in review**: checker R1 revise → 0.2; R2 revise (2 P1) → 0.3; **R3 pass**; waiting for owner approval |
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

## 6a. Design decisions (0.2, checker R1)

- **D1 — owner role provisioned out of band.** `communication_discovery` (NOLOGIN, NOSUPERUSER, NOBYPASSRLS,
  NOINHERIT) is created by the role provisioning step, the same way `communication_runtime` is today
  (`docs/runtime.md` checklist gets the step). The migration does not `CREATE ROLE`. It checks that the role
  exists and stops with a clear error otherwise. Then it creates the function, sets ACLs (`REVOKE ALL FROM
  PUBLIC`, `GRANT EXECUTE TO communication_runtime`), and runs `ALTER FUNCTION … OWNER TO
  communication_discovery`, in that order, because a revoke by a non-owner is a no-op.
- **D2 — narrow read path.** The migration adds a stored generated column `has_content boolean GENERATED ALWAYS AS
  (body <> '' OR subject IS NOT NULL) STORED`, so retention can be found without reading content. The owner role
  gets `SELECT (workspace_id, status, run_at, lease_until, attempts, max_attempts, created_at, has_content)` on
  `message_outbox` only. It gets no access to recipient,
  subject or body, and no INSERT/UPDATE/DELETE. It also gets one policy `FOR SELECT TO communication_discovery
  USING (true)`. It gets nothing on `message_opt_out`: a due row that is opted out is still work, because `claim()` marks it
  `suppressed`, so discovery does not need the opt-out table (R2 #3, decided: no).
- **D3 — the predicate mirrors `claim()`.** A workspace is due when it has a row with `attempts < max_attempts`
  and either `status='queued' AND run_at <= now()`, or `status IN ('leased','sending') AND lease_until <= now()`
  (recovery of a crashed run). A workspace is also due when it has a row with `status IN ('delivered','dead','suppressed')`,
  `created_at < now() - retention` and `has_content`. Retention days are passed in by the worker, clamped to
  7..3650. `p_limit` is clamped to 1..200 inside the function. Order is by oldest due work (`min(run_at)`),
  never by id, so no workspace is pinned out.
- **D4 — result contract.** `scheduled_run_all` returns `(handled, failed_workspaces)`. Each workspace runs in
  its own try/except. A failure logs only the exception class and a counter, never a workspace id or a DB
  message. The heartbeat is `send(ok=failed_workspaces == 0, handled)`, and the process exits non-zero when
  `failed_workspaces > 0` after every workspace was tried. SIGTERM stops after the current message and starts no new
  workspace. Workspaces not reached count as `skipped`, and the heartbeat is `ok=False` when `skipped > 0`, so a
  cut-short run is visible (R2 #4).
- **D5 — rollback.** With `COMMUNICATION_WORKSPACE_ID` set, discovery is not called; a malformed UUID still
  fails at start-up as today. The function stays in place and is harmless when unused.

### Added scenarios

- **AC-07 — No workspaces.** Discovery returns nothing: exit 0, heartbeat ok with 0, no adapter call.
- **AC-08 — Lease recovery.** A `leased` row whose lease expired in W2 is discovered and delivered by the next run.
- **AC-09 — Exhausted rows are not rediscovered.** A workspace whose only rows have `attempts = max_attempts`
  is not returned.
- **AC-10 — Concurrent runs.** Two overlapping runs deliver each message once (`FOR UPDATE SKIP LOCKED`), and
  neither fails.
- **AC-11 — Rotation.** With more due workspaces than `p_limit`, the oldest-due ones go first, and the rest are
  served by the next run.
- **AC-12 — Discovery role cannot write or read content.** As `communication_discovery`, INSERT, UPDATE and
  SELECT body all fail. `communication_runtime` still cannot read another workspace's rows directly.
- **AC-14 — `has_content` tracks content.** True for a body-only row and for a subject-only row. False after
  `redact_terminal`, so a retention-only workspace is not rediscovered.
- **AC-13 — Logs carry no ids.** A captured log of a run with a failing workspace contains no UUID.

Deploy note (R3): `ADD COLUMN … GENERATED … STORED` rewrites `message_outbox` under an ACCESS EXCLUSIVE lock. That
is brief at today's size. Run the migration before merging (deploys do not migrate). A SIGTERM-cut run alerts by
design (D4); accept the rare deploy-time alert.

## 7. Open questions

| # | Question | Owner |
|---|---|---|
| 1 | Default per-workspace batch: 100 (proposed) | Owner |
| 2 | Remove `COMMUNICATION_WORKSPACE_ID` from Railway at deploy, or keep it until a second customer exists | Owner |
| 3 | Run time: about 500 messages × provider latency per run, against the `*/30 * * * *` schedule in `docs/runtime.md`. Railway does not start a cron run while one is still running, and AC-10 covers overlap anyway | — |
