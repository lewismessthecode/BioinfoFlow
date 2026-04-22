from __future__ import annotations

from pathlib import Path

from app.services.run_profile_service import RunProfileService


def _touch(path: Path, content: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_resolve_params_detects_reads_reference_and_samplesheet(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _touch(workspace / "reads" / "sample1_R1.fastq.gz")
    _touch(workspace / "reads" / "sample1_R2.fastq.gz")
    _touch(workspace / "ref" / "NC_045512.2.fasta", ">chr\nACGT")
    _touch(workspace / "samplesheet.csv", "sample,fastq_1,fastq_2\n")

    service = RunProfileService()
    resolved = service.resolve_params(
        workflow_name="viral-mini-nf",
        engine="nextflow",
        workspace_path=workspace,
        params={},
    )

    assert resolved["outdir"] == "results"
    assert resolved["reads"] == "reads/*_{R1,R2}.fastq.gz"
    assert resolved["reference"] == "ref/NC_045512.2.fasta"
    assert resolved["samplesheet"] == "samplesheet.csv"
    assert resolved["input"] == "samplesheet.csv"


def test_resolve_params_preserves_valid_explicit_values(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _touch(workspace / "reads" / "sample1_R1.fastq.gz")
    _touch(workspace / "reads" / "sample1_R2.fastq.gz")
    _touch(workspace / "ref" / "reference.fasta", ">chr\nACGT")

    service = RunProfileService()
    resolved = service.resolve_params(
        workflow_name="genomics-pipeline-nf",
        engine="nextflow",
        workspace_path=workspace,
        params={
            "reference": "ref/reference.fasta",
            "reads": "reads/*_{R1,R2}.fastq.gz",
            "outdir": "custom-results",
        },
    )

    assert resolved["outdir"] == "custom-results"
    assert resolved["reference"] == "ref/reference.fasta"
    assert resolved["reads"] == "reads/*_{R1,R2}.fastq.gz"
