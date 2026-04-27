# Parabricks WGS v4.7.0 Test Workflows Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add two platform-test workflows that run NVIDIA Parabricks WGS FASTQ-to-VCF with the official v4.7.0 container: one Nextflow workflow and one WDL workflow.

**Architecture:** Keep the workflows as local demo assets under `demo/parabricks-wgs-v470/` so they can be registered independently in BioInfoFlow. Both workflows use the same two-stage shape: `fq2bam` produces a BAM and recalibration artifacts, then `haplotypecaller` produces the germline VCF. Inputs are explicit absolute paths so the remote GPU server can swap FASTQ/reference paths without changing workflow code.

**Tech Stack:** Nextflow DSL2, WDL 1.0, NVIDIA Parabricks container `nvcr.io/nvidia/clara/clara-parabricks:4.7.0-1`, Docker/Singularity GPU runtime options.

### Task 1: Add workflow bundle documentation

**Files:**
- Create: `demo/parabricks-wgs-v470/README.md`

**Steps:**
1. Document that NVIDIA publishes official Parabricks workflow repositories, but this bundle is a small platform-test fixture pinned to v4.7.0.
2. Document registration entrypoints for Nextflow and WDL.
3. Document required inputs: paired FASTQs, read group, reference FASTA plus sidecar indexes, known-sites VCF plus index, GPU count, output directory.
4. Document example run commands for local Nextflow and miniwdl.

### Task 2: Add Nextflow workflow

**Files:**
- Create: `demo/parabricks-wgs-v470/nextflow/main.nf`
- Create: `demo/parabricks-wgs-v470/nextflow/nextflow.config`
- Create: `demo/parabricks-wgs-v470/nextflow/samplesheet.example.csv`
- Create: `demo/parabricks-wgs-v470/nextflow/params.example.json`

**Steps:**
1. Implement DSL2 process `FQ2BAM` using `pbrun fq2bam`.
2. Implement DSL2 process `HAPLOTYPECALLER` using `pbrun haplotypecaller`.
3. Use literal Parabricks v4.7.0 container directives so the platform can extract task images.
4. Provide a CSV samplesheet and JSON params file where users only replace absolute paths.

### Task 3: Add WDL workflow

**Files:**
- Create: `demo/parabricks-wgs-v470/wdl/wgs_fq_to_vcf.wdl`
- Create: `demo/parabricks-wgs-v470/wdl/inputs.example.json`

**Steps:**
1. Implement workflow `parabricks_wgs_fq_to_vcf`.
2. Implement task `fq2bam` with Parabricks v4.7.0 Docker runtime and GPU runtime hint.
3. Implement task `haplotypecaller` with the same container and resource hints.
4. Provide a miniwdl/Cromwell-compatible JSON template with replaceable absolute paths.

### Task 4: Verify registration-facing syntax

**Files:**
- Test: `backend/app/services/workflow_validator.py`

**Steps:**
1. Run the local validator against the new Nextflow and WDL files.
2. Run `miniwdl check` if the local backend environment provides miniwdl.
3. Run `nextflow run ... -stub-run` if the local environment provides nextflow.
4. Record any skipped checks caused by missing local binaries.
