from __future__ import annotations

import glob
from pathlib import Path

from app.models.workflow import WorkflowEngine
from app.services.run_helpers import expand_brace_glob_patterns


class RunProfileService:
    """Resolve profile-driven run params from workspace contents."""

    def resolve_params(
        self,
        *,
        workflow_name: str,
        engine: str,
        workspace_path: Path,
        params: dict | None,
    ) -> dict:
        resolved = dict(params or {})
        resolved.setdefault("outdir", "results")

        if engine != WorkflowEngine.NEXTFLOW.value:
            return resolved

        workflow_name_lower = workflow_name.lower()
        if not self._should_infer_nextflow_inputs(workflow_name_lower):
            return resolved

        samplesheet_candidate = self._detect_samplesheet(workspace_path)
        self._fill_or_repair_path_param(
            resolved,
            key="samplesheet",
            candidate=samplesheet_candidate,
            workspace=workspace_path,
        )
        if "samplesheet" in resolved:
            self._fill_or_repair_path_param(
                resolved,
                key="input",
                candidate=resolved["samplesheet"],
                workspace=workspace_path,
            )

        reads_candidate = self._detect_reads_pattern(workspace_path)
        self._fill_or_repair_path_param(
            resolved, key="reads", candidate=reads_candidate, workspace=workspace_path
        )

        reference_candidate = self._detect_reference(workspace_path)
        self._fill_or_repair_path_param(
            resolved,
            key="reference",
            candidate=reference_candidate,
            workspace=workspace_path,
        )

        return resolved

    def _should_infer_nextflow_inputs(self, workflow_name: str) -> bool:
        keywords = ("viral", "genomics", "sars", "ecoli", "yeast", "demo")
        return any(keyword in workflow_name for keyword in keywords)

    def _fill_or_repair_path_param(
        self, params: dict, *, key: str, candidate: str | None, workspace: Path
    ) -> None:
        if not candidate:
            return
        current = params.get(key)
        if not isinstance(current, str) or not current.strip():
            params[key] = candidate
            return
        if not self._path_value_exists(current.strip(), workspace):
            params[key] = candidate

    def _path_value_exists(self, value: str, workspace: Path) -> bool:
        if any(char in value for char in "*?[]{}"):
            patterns = expand_brace_glob_patterns(value)
            return any(
                glob.glob(pattern, root_dir=str(workspace), recursive=True)
                for pattern in patterns
            )
        return (workspace / value).exists()

    def _detect_samplesheet(self, workspace: Path) -> str | None:
        direct = workspace / "samplesheet.csv"
        if direct.is_file():
            return "samplesheet.csv"
        candidates = sorted(workspace.rglob("samplesheet.csv"))
        if not candidates:
            return None
        return str(candidates[0].relative_to(workspace))

    def _detect_reference(self, workspace: Path) -> str | None:
        preferred_nested = workspace / "data" / "ref" / "reference.fasta"
        if preferred_nested.is_file():
            return "data/ref/reference.fasta"

        for root in ("data/ref", "ref", "data", "."):
            for ext in ("*.fasta", "*.fa", "*.fna"):
                matches = sorted((workspace / root).glob(ext))
                if matches:
                    return str(matches[0].relative_to(workspace))

        preferred = workspace / "ref" / "reference.fasta"
        if preferred.is_file():
            return "ref/reference.fasta"

        for pattern in (
            "ref/*.fasta",
            "ref/*.fa",
            "ref/*.fna",
            "*.fasta",
            "*.fa",
            "*.fna",
        ):
            matches = sorted(workspace.glob(pattern))
            if matches:
                return str(matches[0].relative_to(workspace))
        return None

    def _detect_reads_pattern(self, workspace: Path) -> str | None:
        for root in ("reads", "data/reads"):
            reads_dir = workspace / root
            if not reads_dir.is_dir():
                continue
            for ext in (".fastq.gz", ".fq.gz", ".fastq", ".fq"):
                r1_files = sorted(reads_dir.glob(f"*_R1{ext}"))
                r2_files = sorted(reads_dir.glob(f"*_R2{ext}"))
                if r1_files and r2_files:
                    return f"{root}/*_{{R1,R2}}{ext}"
        return None
