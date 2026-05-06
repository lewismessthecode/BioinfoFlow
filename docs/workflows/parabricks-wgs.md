# Parabricks WGS Workflows

This repo includes NVIDIA Parabricks WGS FASTQ-to-VCF workflows pinned to Parabricks v4.7.0.

## Included Workflows

- Nextflow: `demo/parabricks-wgs-v470/nextflow/main.nf`
- WDL: `demo/parabricks-wgs-v470/wdl/wgs_fq_to_vcf.wdl`

Both use:

```text
nvcr.io/nvidia/clara/clara-parabricks:4.7.0-1
```

Input templates:

- `demo/parabricks-wgs-v470/nextflow/params.example.json`
- `demo/parabricks-wgs-v470/nextflow/samplesheet.example.csv`
- `demo/parabricks-wgs-v470/wdl/inputs.example.json`

## How To Use Them

1. Put FASTQ files somewhere visible under `BIOINFOFLOW_HOME`, usually `sources/deliveries/<batch-name>/`.
2. Put reusable references under `sources/reference/<genome-name>/`.
3. Replace the FASTQ/reference paths in the example templates with paths visible on your GPU server.
4. Register the Nextflow or WDL workflow in Bioinfoflow.
5. Submit a run from the UI or CLI.

These workflows are useful for checking workflow registration, image handling, scheduling, GPU execution, and result collection on a trusted workstation or lab GPU server.

## Operational Requirements

- NVIDIA GPU hardware supported by the Parabricks image.
- Docker daemon access from the backend container.
- The Parabricks container image must be pullable on the host.
