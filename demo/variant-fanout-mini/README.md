# variant-fanout-mini

**Engine:** WDL (miniwdl) · **Image:** `ubuntu:22.04` · **Steps:** 7 task definitions / 7 pipeline stages; scatter fan-out = 4

Purpose: exercise real `File` flow between tasks (not string `FINISHED` markers), `scatter → gather` with `Array[File]`, and DAG rendering of a non-trivial graph. This is the most file-IO-heavy demo.

Submission note: `samples_tsv` is also treated as a per-run document input now. Upload one of the TSV fixtures from `data/` when creating the run.

## Pipeline

```
PREP → scatter [ ALIGN → CALL ] → MERGE → FILTER → ANNOTATE → REPORT
```

- `PREP` — strips the TSV header → emits `sample_table.tsv` for scatter to consume.
- `ALIGN` — writes a mock SAM-header-style "BAM" file per sample: `${sample_id}.bam`.
- `CALL` — consumes `ALIGN.bam` as `File` input (the platform must mount it into CALL's work dir), emits a mock VCF.
- `MERGE` — gathers `Array[File] vcfs` from the scatter, concatenates bodies under one header.
- `FILTER` — keeps `PASS` records only.
- `ANNOTATE` — flattens the VCF to a TSV with a mock annotation column.
- `REPORT` — wraps the annotated TSV in a tarball named `report.zip` (the declared output path).

## Input variants

### `happy.inputs.json` → expect **completed**

- 4 samples scatter.
- Output: `results/variant-fanout-mini/07.report/report.zip` exists; contains an annotated TSV with 8 data rows (2 per sample × 4 samples).
- DAG: 1 PREP + 8 scatter children (ALIGN×4, CALL×4) + 4 downstream nodes.

### `boundary.inputs.json` → expect **completed**

- Single-sample scatter.
- **What to watch:** does the DAG still render a scatter group for a 1-item array? Does `Array[File]` of length 1 serialize correctly into MERGE?

### `failure.inputs.json` → expect **failed at PREP** (or earlier input-resolution)

- Points `samples_tsv` at a path that does not exist.
- **What to watch:** does the failure surface at input materialization (before any task runs) or inside PREP's container? Either is acceptable, but the error message should clearly name the missing file.

## Platform behaviors this demo exercises

- Real `File` passing between tasks in the same scatter iteration (ALIGN.bam → CALL).
- `scatter → gather` with `Array[File]` input to MERGE (tests `BioinfoflowSwarmContainer.host_path` rw-mount allowlisting for the gathered paths).
- WDL `read_tsv` + scatter (same pattern as `Deaf_20.wdl`).
- Output at a literal path (`report.zip`) after a potentially-renaming command.
- DAG with 13 runtime nodes across 7 pipeline stages.

## Intentionally avoided

- No `glob()` — miniwdl's `glob()` is local-only and breaks on platform-mounted absolute paths (documented gotcha).
- No parens in `command` block comments — all commands use the `<<< >>>` heredoc form.
