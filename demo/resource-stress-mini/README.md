# resource-stress-mini

**Engine:** WDL (miniwdl) · **Image:** `alpine:3.19` · **Steps:** 3 tasks, but large scatter fanout

Purpose: stress the scheduler's concurrency limits, SSE event volume, DAG rendering of wide graphs, and `timeout` enforcement.

## Pipeline

```
PREP → scatter × N [ BUSY ] → REDUCE
```

- `PREP` — generates `seeds.txt` with N lines.
- `BUSY` (scatter × N) — `sleep ${sleep_seconds}` then touches `${seed}.done`. Task `timeout: "10m"`.
- `REDUCE` — counts gathered markers, writes `summary.txt`.

## Input variants

### `happy.inputs.json` → expect **completed**

- `fanout=30`, `sleep_seconds=5`.
- With scheduler default of 4 concurrent task slots, the 30 BUSY tasks queue and drain in ~40s.
- **What to watch:**
  - Scheduler `/scheduler/status` — queue depth climbs to ~26 then drains.
  - DAG — 30 BUSY nodes all visible; do they render without the UI stalling?
  - SSE — live state transitions arrive promptly (no >5s stale).

### `boundary.inputs.json` → expect **completed**

- `fanout=1`, `sleep_seconds=1`.
- Scatter degenerates to a single task.
- **What to watch:** does the DAG still show a scatter group with one child? Any UI weirdness for size-1 arrays?

### `failure.inputs.json` → expect **failed (timeout)**

- `fanout=2`, `sleep_seconds=900` (15m) against `timeout: "10m"`.
- Each BUSY task should be killed by the runtime at ~10m.
- **What to watch:**
  - Do tasks actually get killed at the 10m mark, or does the run hang until the request timeout?
  - Does the error message contain "timeout"?
  - Is REDUCE marked skipped/not-run, not green?

## Platform behaviors this demo exercises

- Scheduler backpressure (queue depth under `scheduler_max_queue_depth`, concurrent slots under `scheduler_max_concurrency`).
- SSE event throughput under simultaneous fanout.
- DAG node render performance with 30+ nodes.
- Task `timeout` cut-off path (failure variant).
- Scatter → gather with `Array[File]` (REDUCE consumes `BUSY.marker`).

## Concurrency-test variant

To stress the scheduler further, launch 3 concurrent runs of this demo simultaneously:

```bash
for i in 1 2 3; do
  uv run bif run create --demo resource-stress-mini &
done
wait
```

Watch `/scheduler/status` and `/scheduler/resources` — the queue depth should stay bounded, no run should deadlock.
