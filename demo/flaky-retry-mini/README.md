# flaky-retry-mini

**Engine:** WDL (miniwdl) · **Image:** `alpine:3.19` · **Steps:** 4

Purpose: exercise the platform's retry, failure-propagation, and downstream-skip behavior. Scripts are mocks — no real bio tools.

## Pipeline

```
PREP → FLAKY (maxRetries: 3) → FATAL → CLEANUP
```

- `PREP` — initializes a per-run attempt counter at `${outdir}/01.prep/flaky_attempts.txt`.
- `FLAKY` — appends one line to the counter each invocation, `exit 1` until attempts ≥ `flaky_count`.
- `FATAL` — always `exit 1` when `fatal_enabled=true`; otherwise no-op.
- `CLEANUP` — reads the counter + fatal state, writes `summary.txt`.

## Input variants

### `happy.inputs.json` → expect **completed**

- `flaky_count=2`, `fatal_enabled=false`
- FLAKY fails on attempt 1, succeeds on attempt 2.
- Final: run completed; DAG all green; `summary.txt` contains `flaky_attempts=2`, `fatal_state=skipped`.

### `boundary.inputs.json` → expect **failed**

- `flaky_count=4` (exceeds `maxRetries: 3` ceiling).
- FLAKY fails on attempts 1..3, scheduler gives up.
- Final: run failed at FLAKY; FATAL and CLEANUP never run.
- **What to watch:** does the DAG show FLAKY with 3 attempts? Are logs from attempts 1 and 2 preserved, or only the last one?

### `failure.inputs.json` → expect **failed at FATAL**

- `flaky_count=1` (succeeds immediately), `fatal_enabled=true`.
- FLAKY passes on attempt 1, FATAL always fails.
- Final: run failed at FATAL; CLEANUP never runs.
- **What to watch:** is the DAG showing PREP and FLAKY green, FATAL red, CLEANUP grey/skipped? Does the run-detail page surface the `FATAL fatal_enabled=true, exiting 1` message?

## Platform behaviors this demo exercises

- `maxRetries` semantics — same-container retry vs fresh container (our counter persists via outdir mount, so it works either way).
- Log capture across retry attempts (both success and boundary variants).
- Downstream task skipping on upstream failure (failure variant).
- State transitions in the scheduler: `running → failed → retrying → running → completed` for FLAKY in the happy path.
