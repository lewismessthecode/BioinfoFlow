# resource-stress-mini

**Engine:** WDL (miniwdl) · **Image:** `ubuntu:22.04` · **Steps:** 3 task definitions with a large scatter fanout

Purpose: stress engine fanout, SSE event volume, and DAG rendering of wide graphs. Bioinfoflow schedules whole runs; MiniWDL owns the scattered task execution inside each run.

## Pipeline

```
PREP → scatter × N [ BUSY ] → REDUCE
```

- `PREP` — generates `seeds.txt` with N lines.
- `BUSY` (scatter × N) — `sleep ${sleep_seconds}` then touches `${seed}.done`.
- `REDUCE` — counts gathered markers, writes `summary.txt`.

## Input variants

### `happy.inputs.json` → expect **completed**

- `fanout=30`, `sleep_seconds=5`.
- Observe how MiniWDL and the available host resources execute the 30 BUSY tasks.
- **What to watch:**
  - Scheduler `/scheduler/status` — the Bioinfoflow run remains observable while MiniWDL executes the scatter.
  - DAG — 30 BUSY nodes all visible; do they render without the UI stalling?
  - SSE — live state transitions continue to arrive during the fanout.

### `boundary.inputs.json` → expect **completed**

- `fanout=1`, `sleep_seconds=1`.
- Scatter degenerates to a single task.
- **What to watch:** does the DAG still show a scatter group with one child? Any UI weirdness for size-1 arrays?

### `failure.inputs.json` → long-running timeout fixture

- `fanout=2`, `sleep_seconds=900` (15m).
- The WDL `meta.timeout` value is descriptive metadata, not an enforced task runtime limit.
- To test Bioinfoflow timeout handling, submit a complete run spec with `options.timeout_seconds` set to a value such as `600`. That limit applies to the whole run.
- **What to watch:**
  - Does the run stop at the configured run-level timeout?
  - Does the error message contain "timeout"?
  - Is REDUCE marked skipped/not-run, not green?

## Platform behaviors this demo exercises

- Scheduler behavior when several copies of the demo are submitted as separate runs.
- SSE event throughput under simultaneous fanout.
- DAG node render performance with 30+ nodes.
- Run-level timeout handling when `options.timeout_seconds` is configured.
- Scatter → gather with `Array[File]` (REDUCE consumes `BUSY.marker`).

## Concurrency-test variant

To stress the scheduler further, submit the demo three times. From `backend/`, after registering the workflow and selecting a project:

```bash
for i in 1 2 3; do
  uv run bif run submit \
    --project <project-id> \
    --workflow <workflow-id> \
    --spec ../demo/resource-stress-mini/inputs/happy.inputs.json &
done
wait
```

Watch `/scheduler/status` and `/scheduler/resources`; queue depth should remain bounded and the runs should continue making progress. These are acceptance checks, not recorded verification results.
