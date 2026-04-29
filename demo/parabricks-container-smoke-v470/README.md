# Parabricks Container Smoke v4.7.0

This demo keeps the existing `demo/parabricks-wgs-v470` workflow untouched and
adds a much smaller Parabricks smoke test.

The workflow uses the same Parabricks container image:

```text
nvcr.io/nvidia/clara/clara-parabricks:4.7.0-1
```

It does not require FASTQ, reference FASTA, reference indexes, known-sites VCF,
or known-sites indexes. It is meant to verify the BioInfoFlow execution path:

- workflow registration and WDL parsing
- Parabricks container pull/startup
- optional `nvidia-smi` visibility
- run output collection

It is not a biological analysis workflow. It writes a tiny synthetic VCF so the
platform has a normal file artifact to collect.

## WDL

Entrypoint:

```text
demo/parabricks-container-smoke-v470/wdl/parabricks_container_smoke.wdl
```

Input template:

```text
demo/parabricks-container-smoke-v470/wdl/inputs.example.json
```

Local test:

```bash
cd demo/parabricks-container-smoke-v470/wdl
miniwdl run parabricks_container_smoke.wdl -i inputs.example.json
```

The default `num_gpus` is `0`. Set `require_gpu` to `true` when you want the
task to request a GPU and fail unless `nvidia-smi` succeeds inside the
Parabricks container. Bioinfoflow's miniwdl Docker Swarm backend translates WDL
`runtime.gpu` into an NVIDIA generic resource reservation plus the
`NVIDIA_VISIBLE_DEVICES`/`NVIDIA_DRIVER_CAPABILITIES` task environment. The
Docker host still needs NVIDIA Container Toolkit/Swarm GPU resources configured.
