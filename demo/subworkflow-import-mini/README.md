# subworkflow-import-mini

**Engine:** WDL (miniwdl) · **Image:** `ubuntu:22.04` · **Steps:** 7 tasks across main + 2 imported subworkflows

Purpose: exercise WDL `import` resolution, nested DAG rendering, and event attribution across workflow boundaries.

## Pipeline

```
main.wdl
├── qc.qc_pipeline (imported from subworkflows/qc_sub.wdl)
│   └── FASTQC → TRIM → POST_QC
├── align.align_pipeline (imported from subworkflows/align_sub.wdl)
│   └── INDEX_REF → BWA_MEM → SORT_BAM
└── REPORT (local task in main.wdl)
```

Files flow across subworkflow boundaries: `qc_run.trimmed_reads` → `align.align_pipeline.trimmed_reads`, and `qc_run.qc_summary` + `align_run.sorted_bam` → `REPORT`.

## Input variants

### `happy.inputs.json` → expect **completed**

- `sample_id=sampleA`.
- Output at `results/subworkflow-import-mini/99.report/sampleA.final_report.txt`.
- DAG: 7 task nodes total, ideally grouped into 3 clusters (qc, align, main).

### `boundary.inputs.json` → expect **completed**

- `sample_id=X` (single-character sample id — tests string escaping in `${sample_id}.report.txt` filenames).

### `failure.inputs.json` → expect **failed at FASTQC** (or input validation)

- `sample_id=""` (empty string).
- FASTQC's output path becomes `${outdir}/qc/01.fastqc/.report.txt` — a dotfile. Platform may fail to materialize it as a declared `File` output.
- **What to watch:** does the error message clearly identify that the output file is missing? Does the platform choke on empty-string inputs at the materialization layer, or only when the task fails to produce the file?

## Platform behaviors this demo exercises

- **WDL `import` path resolution** — paths are relative to the main WDL. Does the platform correctly stage `subworkflows/` into the miniwdl run dir?
- **DAG nesting** — the UI should ideally group the 3 qc tasks + 3 align tasks under collapsible cluster nodes, not flatten all 7 to a single row.
- **Event attribution** — when `qc.qc_pipeline.FASTQC` emits a task event, it should be routed to the correct DAG node (namespaced, not confused with a top-level `FASTQC`).
- **File flow across subworkflow boundaries** — `qc_run.trimmed_reads` is a subworkflow output consumed by another subworkflow as input.

## Files in this demo

- `main.wdl` — imports + REPORT task.
- `subworkflows/qc_sub.wdl` — `qc_pipeline` (FASTQC → TRIM → POST_QC).
- `subworkflows/align_sub.wdl` — `align_pipeline` (INDEX_REF → BWA_MEM → SORT_BAM).
