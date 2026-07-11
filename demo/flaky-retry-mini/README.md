# flaky-retry-mini

**Engine:** WDL (miniwdl) · **Image:** `ubuntu:22.04` · **Steps:** 4

Purpose: exercise MiniWDL task retries plus workflow failure propagation and downstream skipping inside one Bioinfoflow run. Scripts are mocks — no real bio tools.

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

### `boundary.inputs.json` → retry-boundary probe

- `flaky_count=4` probes the exact `maxRetries: 3` boundary.
- `maxRetries` is enforced by MiniWDL, not the Bioinfoflow run scheduler. Verify the installed MiniWDL semantics before treating this fixture as a deterministic failure case; implementations may count retries in addition to the initial attempt.
- **What to watch:** how many FLAKY attempts run, whether the fixture completes or fails, and which retry logs remain available.

### `failure.inputs.json` → expect **failed at FATAL**

- `flaky_count=1` (succeeds immediately), `fatal_enabled=true`.
- FLAKY passes on attempt 1, FATAL always fails.
- Final: run failed at FATAL; CLEANUP never runs.
- **What to watch:** is the DAG showing PREP and FLAKY green, FATAL red, CLEANUP grey/skipped? Does the run-detail page surface the `FATAL fatal_enabled=true, exiting 1` message?

## Platform behaviors this demo exercises

- `maxRetries` semantics — same-container retry vs fresh container (our counter persists via outdir mount, so it works either way).
- Log capture across retry attempts (both success and boundary variants).
- Downstream task skipping on upstream failure (failure variant).
- MiniWDL retry behavior inside a Bioinfoflow run. Bioinfoflow's persisted run states do not include a task-level `retrying` state.
