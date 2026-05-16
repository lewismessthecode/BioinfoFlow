# NVIDIA Parabricks WGS v4.7.0 Platform Test Workflows

This bundle contains two small, production-shaped workflows for testing BioInfoFlow registration, image discovery, GPU scheduling, container startup, and run artifact handling with NVIDIA Parabricks:

- `nextflow/main.nf`: Nextflow DSL2 FASTQ-to-VCF workflow.
- `wdl/wgs_fq_to_vcf.wdl`: WDL 1.0 FASTQ-to-VCF workflow.

Both workflows use the official Parabricks container:

```text
nvcr.io/nvidia/clara/clara-parabricks:4.7.0-1
```

NVIDIA also publishes official workflow repositories for broader production use:

- https://github.com/clara-parabricks-workflows/parabricks-nextflow
- https://github.com/clara-parabricks-workflows/Parabricks-WDL-Workflows

These local workflows are intentionally smaller than the upstream repositories. They are meant to exercise the platform path from registration to run completion while staying easy to inspect and edit.

## Required Test Data

Use absolute paths visible to the host and task containers. For path-contract testing, keep `BIOINFOFLOW_HOME` identity-mounted and avoid paths that only exist inside one side of the host/container boundary.

Required inputs:

- Paired WGS FASTQs: `fastq_r1`, `fastq_r2`
- Read group string, for example `@RG\tID:HG002\tLB:HG002\tPL:ILLUMINA\tSM:HG002\tPU:unit1`
- Reference FASTA
- Reference sidecar indexes, usually `.fai`, `.dict`, `.amb`, `.ann`, `.bwt`, `.pac`, `.sa`
- Known-sites VCF, usually bgzipped
- Known-sites index, usually `.tbi`

The sidecar index files are explicit inputs so WDL/Nextflow localization keeps them next to the reference and known-sites file inside the task work directory.

## Nextflow

Entrypoint:

```text
demo/parabricks-wgs-v470/nextflow/main.nf
```

Input templates:

- `nextflow/samplesheet.example.csv`
- `nextflow/params.example.json`

Replace the paths in both templates, then run:

```bash
cd demo/parabricks-wgs-v470/nextflow
nextflow run main.nf -params-file params.example.json
```

For Docker GPU testing, `nextflow.config` enables Docker and passes `--gpus all --ipc=host`. For Singularity/Apptainer, adjust `nextflow.config` on the GPU server and use `--nv`.

## WDL

Entrypoint:

```text
demo/parabricks-wgs-v470/wdl/wgs_fq_to_vcf.wdl
```

Input template:

```text
demo/parabricks-wgs-v470/wdl/inputs.example.json
```

Replace the paths in the JSON template, then run:

```bash
cd demo/parabricks-wgs-v470/wdl
miniwdl run wgs_fq_to_vcf.wdl -i inputs.example.json
```

If you run via Cromwell or another WDL engine, make sure its Docker runtime passes GPU access to the Parabricks container.
