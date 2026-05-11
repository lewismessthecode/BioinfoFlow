# rnaseq-quant-mini

**Engine:** Nextflow (DSL2) · **Image:** `ubuntu:22.04` (local) + `quay.io/biocontainers/fastqc:0.12.1--hdfd78af_0` (**remote pull**) · **Steps:** 5 processes

Purpose: exercise the Nextflow adapter's event mapping, channel joining, `publishDir`, and the backend image-pull path (the only remote-pull demo in this set).

Submission note: `samplesheet` is now a per-run document input. Upload one of the `data/samplesheet*.csv` files when you submit the run; the platform snapshots that CSV into the run before launch.

## Pipeline

```
FASTQC → TRIM → ALIGN(+genome) → QUANT → MULTIQC(collect fastqc + quant)
```

- `FASTQC` — per-sample; uses the remote `quay.io/biocontainers/fastqc` image. Emits both the reads tuple (for downstream) and a report file (for MULTIQC collect).
- `TRIM` — per-sample, mock trimmer output.
- `ALIGN` — per-sample × scalar `genome` param. Tests channel + value joining.
- `QUANT` — per-sample, emits `${sample}/quant.sf`.
- `MULTIQC` — gathers all fastqc reports and quant files (`.collect()`), writes a single `multiqc_report.html`. This is the fan-in / synchronization point.

All processes use `publishDir` to copy outputs into `${params.outdir}/<stage>/` under the run's results root.

## Input variants

### `happy.params.json` → expect **completed**

- 3 samples, `genome=GRCh38`.
- Outputs:
  - `results/rnaseq-quant-mini/fastqc/{sample1,2,3}.fastqc.html`
  - `results/rnaseq-quant-mini/trim/{sample1,2,3}.trimmed.fq.gz`
  - `results/rnaseq-quant-mini/align/{sample1,2,3}.bam`
  - `results/rnaseq-quant-mini/quant/{sample1,2,3}/quant.sf`
  - `results/rnaseq-quant-mini/multiqc/multiqc_report.html`
- **What to watch:** Was the fastqc image pulled? Is the pull visible in the images API? Does the DAG render all 5 processes with edge multiplicities (1→1 for the linear stages, 3→1 for MULTIQC)?

### `boundary.params.json` → expect **completed**

- 1 sample only.
- **What to watch:** does MULTIQC's `.collect()` still trigger with a single input? Any Nextflow weirdness with a size-1 channel into `collect`?

### `failure.params.json` → expect **failed at FASTQC channel init**

- `samplesheet` points to a missing path; `checkIfExists: true` on the channel means it should fail immediately.
- **What to watch:** does the error surface as a pre-process Nextflow exception? Is it routed to the platform's run-detail page, or lost in logs?

## Platform behaviors this demo exercises

- **Remote image pull** — the only demo that deliberately pulls. Confirms the backend image service + Docker daemon can resolve `quay.io/biocontainers` and reuse the image across this and future runs.
- **Nextflow channel semantics** — `fromPath → splitCsv → map → tuple`, `collect()` fan-in, value (`genome`) + queue channel joining.
- **`publishDir`** — tests whether outputs land in `params.outdir` relative to the per-run workspace (path contract).
- **Event mapping** — Nextflow emits process-level events; does the adapter correctly map them into the unified DAG?

## Notes

- The mock-reads files in `data/mock-reads/` are tiny gzipped fastqs (single read each). The processes don't actually consume their bytes — they just need the paths to exist so `file(row.fastq_1)` doesn't fail channel init.
- The example CSVs now use paths relative to the CSV file itself (`mock-reads/...`). The workflow resolves those relative paths against the uploaded manifest location, so the fixture stays portable after the manifest is snapshotted into the run.
- First run will pull the fastqc image (may take 30–60s). Subsequent runs use the cached image.
