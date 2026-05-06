"""Launch-readiness checks for public onboarding artifacts."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
DEMO_ROOT = REPO_ROOT / "demo" / "nfcore-rnaseq"
ISSUE_SEEDS_ROOT = REPO_ROOT / ".github" / "ISSUES"


def test_nfcore_rnaseq_demo_entrypoint_files_exist() -> None:
    expected = [
        DEMO_ROOT / "README.md",
        DEMO_ROOT / "run-direct.sh",
        DEMO_ROOT / "params.test-docker.json",
        DEMO_ROOT / "nextflow.test-docker.config",
        DEMO_ROOT / "VERIFIED.md",
    ]

    missing = [path.relative_to(REPO_ROOT).as_posix() for path in expected if not path.exists()]

    assert missing == []


def test_nfcore_rnaseq_direct_script_uses_real_pinned_pipeline() -> None:
    script = (DEMO_ROOT / "run-direct.sh").read_text(encoding="utf-8")

    assert "nf-core/rnaseq" in script
    assert 'PIPELINE_VERSION="3.24.0"' in script
    assert 'PROFILE="test,docker"' in script
    assert '-r "${PIPELINE_VERSION}"' in script
    assert '-profile "${PROFILE}"' in script
    assert "raw.githubusercontent.com/nf-core/test-datasets" in script
    assert '--input "${SAMPLESHEET_FILE}"' in script
    assert '--fasta "${REFERENCE_DIR}/genome.fasta"' in script
    assert '--gff "${REFERENCE_DIR}/genes.gff.gz"' in script
    assert "--retry 5" in script
    assert "--outdir" in script


def test_readme_links_launch_demo_and_canonical_architecture_doc() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert "demo/nfcore-rnaseq/README.md" in readme
    assert "docs/architecture.md" in readme


def test_github_issue_templates_and_launch_issue_seeds_exist() -> None:
    expected = [
        REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "config.yml",
        REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml",
        REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "feature_request.yml",
    ]
    seed_files = sorted(ISSUE_SEEDS_ROOT.glob("launch-*.md"))

    missing = [path.relative_to(REPO_ROOT).as_posix() for path in expected if not path.exists()]

    assert missing == []
    assert len(seed_files) >= 5
    assert all("## Acceptance Criteria" in path.read_text(encoding="utf-8") for path in seed_files)
