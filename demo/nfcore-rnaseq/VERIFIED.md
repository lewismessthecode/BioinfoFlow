# nf-core/rnaseq Demo Verification

Status: not yet verified on a fresh external machine.

Use this file as release evidence for the canonical demo. Add one entry per
clean-machine run.

## Verification Template

- Date:
- Commit:
- Machine:
- OS:
- CPU architecture:
- Docker version:
- Nextflow version:
- Command:

  ```bash
  demo/nfcore-rnaseq/run-direct.sh
  ```

- Started:
- Finished:
- Elapsed:
- Result:
- Notes:

## Acceptance Criteria

- `docker compose up -d --build` starts the platform from a fresh clone.
- `demo/nfcore-rnaseq/run-direct.sh` exits `0`.
- The direct run completes in under 30 minutes after Docker is installed.
- Bioinfoflow can launch the same pinned `nf-core/rnaseq` demo.
- The Bioinfoflow run page shows logs, DAG progress, and outputs.

## Local Attempt Log

### 2026-05-06 - local development machine

- Machine: local macOS development workspace
- Docker: 27.3.1 linux/arm64
- Nextflow: 25.10.2
- Command:

  ```bash
  demo/nfcore-rnaseq/run-direct.sh
  ```

- Result: failed before task submission while reading the remote nf-core test
  samplesheet.
- Error: `javax.net.ssl.SSLHandshakeException: Remote host terminated the handshake`
- Notes: `curl` to the same `raw.githubusercontent.com` host also intermittently
  failed with `LibreSSL SSL_connect: SSL_ERROR_SYSCALL`. The script now retries
  and caches the official test samplesheet locally before invoking Nextflow.

### 2026-05-06 - local development machine, cached test data iteration

- Machine: local macOS development workspace
- Docker: 27.3.1 linux/arm64
- Nextflow: 25.10.2
- Command:

  ```bash
  demo/nfcore-rnaseq/run-direct.sh
  ```

- Result: failed during parameter validation because script progress logs were
  written into the generated local samplesheet.
- Fix applied: `fetch()` progress now writes to stderr so stdout can safely
  generate `samplesheet_test.local.csv`.

### 2026-05-06 - local development machine, Docker pull stage

- Machine: local macOS development workspace
- Docker: 27.3.1 linux/arm64
- Nextflow: 25.10.2
- Command:

  ```bash
  demo/nfcore-rnaseq/run-direct.sh
  ```

- Result: manually stopped after the run exceeded the launch-demo time target
  while pulling or starting the first Wave container image.
- Evidence:
  - Nextflow passed parameter validation.
  - Nextflow submitted `GUNZIP_GTF` and `GUNZIP_ADDITIONAL_FASTA`.
  - Both tasks reported `Unable to find image 'community.wave.seqera.io/library/coreutils_grep_gzip_lbzip2_pruned:838ba80435a629f8' locally`.
  - `docker-credential-desktop get` processes remained running while no
    containers appeared in `docker ps`.
- Follow-up: verify the demo on a clean Docker environment via issues #6 and
  #7, and document registry/credential troubleshooting via issue #9.
