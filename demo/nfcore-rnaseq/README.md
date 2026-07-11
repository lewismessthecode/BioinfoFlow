# nf-core/rnaseq Canonical Demo

This is the public onboarding demo for Bioinfoflow. It runs the real upstream
`nf-core/rnaseq` pipeline with the official nf-core test profile, so a new user
can verify the platform without downloading or committing large FASTQ fixtures.

## What This Proves

- Docker and Nextflow can run a real nf-core pipeline on the machine.
- Bioinfoflow can register and launch a production-shaped Nextflow workflow.
- The run page can show live logs, DAG state, and published outputs for a
  pipeline users already recognize.

## Requirements

- Docker Engine or Docker Desktop
- Nextflow on `PATH`
- Internet access for the first run, because Nextflow fetches the pipeline and
  Docker pulls the nf-core test containers

## Direct Nextflow Smoke Test

From the repo root:

```bash
demo/nfcore-rnaseq/run-direct.sh
```

The core command shape is:

```bash
nextflow run nf-core/rnaseq -r 3.24.0 -profile test,docker
```

The script also supplies its generated config, work directory, local samplesheet,
reference/index paths, and output directory; inspect `run-direct.sh` for the
complete invocation.

Before launching Nextflow, the script downloads the official nf-core test
samplesheet, FASTQs, and reference fixtures into
`runs/direct-test-docker/testdata/` with curl retries. It then points
`nf-core/rnaseq` at those local files. This keeps the demo faithful to the
upstream `test` profile while avoiding fragile Java/Nextflow TLS reads from
`raw.githubusercontent.com` during validation.

Outputs are written under:

```text
demo/nfcore-rnaseq/runs/direct-test-docker/results/
```

Acceptance criteria (not yet established by a fresh successful external-machine
run in `VERIFIED.md`):

- Nextflow exits with code `0`.
- `multiqc/` and `pipeline_info/` exist under the output directory.
- The command completes in under 30 minutes on a normal fresh Mac or Linux
  workstation with Docker already installed.

## Bioinfoflow Path

1. Start the app from the repo root:

   ```bash
   docker compose up -d --build
   ```

2. Open <http://localhost:3000> and sign in with the owner credentials from
   `.env`.

3. Register a Nextflow workflow:

   - Source: `nf-core`
   - Name: `rnaseq`
   - Version/ref: `3.24.0`

4. Submit a run with the same profile used by the direct smoke test:

   - Profile: `test,docker`
   - Outdir: choose a managed run output directory
   - Extra params: use `params.test-docker.json` as the reference shape

5. Watch the run detail page until it completes. Confirm logs, DAG, and outputs
   are visible.

## Why There Is No FASTQ Data Here

This demo intentionally relies on nf-core's official `test` profile. The test
profile carries the small public test inputs needed to validate setup, while
Docker supplies reproducible tool environments. Keeping the data upstream avoids
large binary fixtures in this repo and keeps the demo aligned with the pinned
pipeline version.

## Expected First-Run Cost

The first run may spend most of its time downloading the pipeline and pulling
Docker images. Subsequent runs should be faster because Nextflow and Docker
cache those artifacts locally.

## Troubleshooting

If the run prints `Unable to find image 'community.wave.seqera.io/...' locally`
and then appears to hang, Docker is likely blocked while authenticating to or
pulling from the container registry. On Docker Desktop, check whether
`docker-credential-desktop get` is stuck:

```bash
ps -ef | grep docker-credential
```

Then try:

```bash
docker pull community.wave.seqera.io/library/coreutils_grep_gzip_lbzip2_pruned:838ba80435a629f8
docker system df
docker compose logs backend frontend
```

Registry/proxy/offline troubleshooting is tracked in the launch issue seed
`.github/ISSUES/launch-06-docker-pull-troubleshooting.md`.

## Verification Record

Fill in `VERIFIED.md` after running this demo on a clean machine. Treat this
file as release evidence: include OS, CPU architecture, Docker version,
Nextflow version, command, elapsed time, and result.
