from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PRESERVED_WORKFLOW_DIRS = [
    "demo/rnaseq-quant-mini",
    "demo/variant-fanout-mini",
    "demo/flaky-retry-mini",
    "demo/resource-stress-mini",
    "demo/subworkflow-import-mini",
]
PRESERVED_WDL_FILES = [
    "demo/flaky-retry-mini/flaky_retry.wdl",
    "demo/resource-stress-mini/resource_stress.wdl",
    "demo/variant-fanout-mini/variant_fanout.wdl",
    "demo/subworkflow-import-mini/main.wdl",
    "demo/subworkflow-import-mini/subworkflows/qc_sub.wdl",
    "demo/subworkflow-import-mini/subworkflows/align_sub.wdl",
]


def test_bundled_workflow_directories_are_preserved_for_tests():
    missing = [
        relative_path
        for relative_path in PRESERVED_WORKFLOW_DIRS
        if not (REPO_ROOT / relative_path).is_dir()
    ]

    assert missing == []


def test_preserved_wdl_fixtures_use_bash_capable_images():
    offenders = []
    for relative_path in PRESERVED_WDL_FILES:
        text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        if 'docker: "alpine:' in text:
            offenders.append(relative_path)

    assert offenders == []


def test_rnaseq_quant_demo_preserves_unique_quant_outputs_for_multiqc():
    text = (REPO_ROOT / "demo/rnaseq-quant-mini/rnaseq_quant.nf").read_text(
        encoding="utf-8"
    )

    assert 'path("${sample}/quant.sf"), emit: quant' not in text
    assert 'path("${sample}"), emit: quant' in text
