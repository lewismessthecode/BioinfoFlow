from __future__ import annotations

import gzip
import re
from pathlib import Path
from typing import Any


SCENARIOS: list[dict[str, Any]] = [
    {
        "id": "rna_seq_differential_expression",
        "category": "bulk-rna-seq",
        "prompt": "Analyze RNA-seq data at data/counts.csv vs data/meta.csv, treatment vs control. Run the analysis yourself, save outputs, and summarize the differential expression results.",
        "expectations": [
            "Reads both counts and metadata tables",
            "Executes code instead of handing back a script",
            "Produces a persisted result artifact or output path",
        ],
    },
    {
        "id": "pubmed_crispr_base_editing",
        "category": "literature",
        "prompt": "Search PubMed for recent papers on CRISPR base editing, summarize the top 10, and include links.",
        "expectations": [
            "Searches recent literature rather than giving generic background only",
            "Returns citations or URLs",
            "Produces a concise ranked summary",
        ],
    },
    {
        "id": "clinical_survival_analysis",
        "category": "clinical",
        "prompt": "Run survival analysis on data/clinical.csv with time=OS_months and event=OS_status. Execute the analysis, save Kaplan-Meier outputs, and summarize the findings.",
        "expectations": [
            "Parses time/event columns correctly",
            "Runs code locally",
            "Reports where outputs were saved",
        ],
    },
    {
        "id": "single_cell_10x_analysis",
        "category": "single-cell",
        "prompt": "Perform single-cell RNA-seq analysis on the 10X data in data/10x/. Run the workflow or code yourself, then summarize QC, clustering, and marker results.",
        "expectations": [
            "Recognizes 10X input structure",
            "Executes analysis steps instead of describing them only",
            "Returns concrete QC and clustering outputs",
        ],
    },
    {
        "id": "virtual_screen_egfr_chembl",
        "category": "cheminformatics",
        "prompt": "Virtual screen EGFR inhibitors from ChEMBL with IC50 < 50 nM, run the retrieval/analysis yourself, and generate an SAR report.",
        "expectations": [
            "Queries ChEMBL data",
            "Executes the retrieval or analysis code directly",
            "Produces a structured SAR-oriented summary",
        ],
    },
    {
        "id": "workflow_recommendation_from_fastqs",
        "category": "workflow-orchestration",
        "prompt": "Inspect the local workspace for paired FASTQ files, recommend the best workflow, and prepare the exact next command or run submission plan.",
        "expectations": [
            "Scans the workspace instead of guessing",
            "Finds concrete files or reports none found",
            "Proposes a workflow using discovered paths",
        ],
    },
    {
        "id": "failed_run_diagnosis",
        "category": "operations",
        "prompt": "Diagnose the latest failed workflow run for this project using available logs and status information, then tell me the likeliest root cause and next action.",
        "expectations": [
            "Inspects real run/log state",
            "Explains a concrete root cause hypothesis",
            "Recommends retry, resume, or fix path with evidence",
        ],
    },
    {
        "id": "gene_list_enrichment_report",
        "category": "functional-analysis",
        "prompt": "Read a gene list from data/genes.txt, run enrichment analysis if possible, and produce a concise biological interpretation report.",
        "expectations": [
            "Reads the provided gene list",
            "Attempts analysis rather than generic prose only",
            "Returns a biologically meaningful summary",
        ],
    },
    {
        "id": "omics_script_execution",
        "category": "coding-agent",
        "prompt": "Write and execute a Python script that loads the omics tables in data/, performs a basic exploratory analysis, and saves plots into outputs/agent-report/.",
        "expectations": [
            "Writes and runs code directly",
            "Creates concrete output files",
            "Summarizes the executed workflow and outputs",
        ],
    },
    {
        "id": "cohort_comparison_report",
        "category": "reporting",
        "prompt": "Compare results from data/cohort_a_results.csv and data/cohort_b_results.csv, run the comparison yourself, and save a markdown report with the key differences.",
        "expectations": [
            "Loads both cohort result files",
            "Executes comparison code",
            "Persists a markdown summary artifact",
        ],
    },
]

_SCENARIOS_BY_ID = {scenario["id"]: scenario for scenario in SCENARIOS}
_URL_RE = re.compile(r"https?://\S+")
_CODE_TOOLS = {"execute_code", "shell"}
_PATH_RE = re.compile(
    r"(?P<path>(?:[\w.-]+/)*[\w.-]+\.(?:csv|tsv|json|md|txt|png|jpg|jpeg|svg|pdf|html|log))"
)
_INFRA_ERROR_PATTERNS = (
    "service unavailable",
    "midstreamfallbackerror",
    "apiconnectionerror",
    "vertex_ai_betaexception",
    "stream timed out",
    "request timed out",
    "high demand",
)


def get_scenario(scenario_id: str) -> dict[str, Any]:
    try:
        return _SCENARIOS_BY_ID[scenario_id]
    except KeyError as exc:
        available = ", ".join(sorted(_SCENARIOS_BY_ID))
        raise KeyError(f"Unknown scenario '{scenario_id}'. Available: {available}") from exc


def _write_text(path: Path, content: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return str(path)


def _write_gzip_text(path: Path, content: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write(content)
    return str(path)


def provision_workspace(workspace_root: Path, scenario: dict[str, Any]) -> list[str]:
    workspace_root.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    scenario_id = scenario["id"]

    def write(relative_path: str, content: str) -> None:
        created.append(
            str(Path(_write_text(workspace_root / relative_path, content)).relative_to(workspace_root))
        )

    def write_gz(relative_path: str, content: str) -> None:
        created.append(
            str(Path(_write_gzip_text(workspace_root / relative_path, content)).relative_to(workspace_root))
        )

    if scenario_id == "rna_seq_differential_expression":
        write(
            "data/counts.csv",
            "gene_id,ctrl_1,ctrl_2,trt_1,trt_2\n"
            "TP53,120,118,260,255\n"
            "EGFR,80,79,160,158\n"
            "GAPDH,900,890,905,910\n",
        )
        write(
            "data/meta.csv",
            "sample_id,condition\nctrl_1,control\nctrl_2,control\ntrt_1,treatment\ntrt_2,treatment\n",
        )
    elif scenario_id == "clinical_survival_analysis":
        write(
            "data/clinical.csv",
            "patient_id,OS_months,OS_status,arm\n"
            "P1,14,1,control\nP2,18,0,control\nP3,22,1,treatment\nP4,30,0,treatment\n",
        )
    elif scenario_id == "single_cell_10x_analysis":
        write_gz("data/10x/barcodes.tsv.gz", "cell-1\ncell-2\ncell-3\n")
        write_gz(
            "data/10x/features.tsv.gz",
            "ENSG000001,MS4A1,Gene Expression\nENSG000002,CD3D,Gene Expression\n",
        )
        write_gz(
            "data/10x/matrix.mtx.gz",
            "%%MatrixMarket matrix coordinate integer general\n%\n2 3 4\n1 1 4\n1 2 1\n2 2 6\n2 3 7\n",
        )
    elif scenario_id == "workflow_recommendation_from_fastqs":
        write_gz(
            "data/reads/sample_A_R1.fastq.gz",
            "@SEQ1\nACGTACGT\n+\nFFFFFFFF\n",
        )
        write_gz(
            "data/reads/sample_A_R2.fastq.gz",
            "@SEQ1\nTGCATGCA\n+\nFFFFFFFF\n",
        )
    elif scenario_id == "failed_run_diagnosis":
        write(
            "run_diagnostics/latest_failed_run.json",
            '{"run_id":"run-001","status":"failed","workflow":"rnaseq","failed_step":"align","exit_code":137}\n',
        )
        write(
            "run_diagnostics/latest_failed_run.log",
            "ERROR align: process exited with code 137 after memory spike on sample_A\n",
        )
    elif scenario_id == "gene_list_enrichment_report":
        write("data/genes.txt", "TP53\nEGFR\nBRCA1\nMTOR\nSTAT3\n")
    elif scenario_id == "omics_script_execution":
        write(
            "data/transcriptomics.csv",
            "sample,condition,TP53,EGFR,STAT3\nS1,control,11,7,8\nS2,treatment,24,13,15\n",
        )
        write(
            "data/proteomics.csv",
            "sample,condition,AKT1,MTOR\nS1,control,1.2,1.8\nS2,treatment,2.1,2.7\n",
        )
    elif scenario_id == "cohort_comparison_report":
        write(
            "data/cohort_a_results.csv",
            "feature,logFC,p_value\nTP53,1.8,0.001\nEGFR,1.2,0.01\n",
        )
        write(
            "data/cohort_b_results.csv",
            "feature,logFC,p_value\nTP53,0.8,0.05\nEGFR,2.0,0.002\n",
        )
    else:
        # Scenarios like PubMed and ChEMBL rely primarily on tool/web access, but
        # still benefit from an outputs directory the agent can write into.
        pass

    (workspace_root / "outputs").mkdir(parents=True, exist_ok=True)
    return created


def _final_agent_text(result: dict[str, Any]) -> str:
    history = result.get("history", {}).get("messages", [])
    for message in reversed(history):
        if message.get("role") == "agent" and message.get("type") == "text":
            return str(message.get("content") or "")
    return ""


def _tool_names(result: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for event in result.get("events", []):
        if event.get("event") not in {"agent.tool_call_start", "agent.tool_call_end"}:
            continue
        metadata = event.get("data", {}).get("metadata", {})
        name = metadata.get("name")
        if isinstance(name, str) and name:
            names.add(name)
    return names


def _event_names(result: dict[str, Any]) -> set[str]:
    return {str(event.get("event")) for event in result.get("events", []) if event.get("event")}


def _artifact_matches(workspace_root: Path, patterns: list[str]) -> list[str]:
    matches: list[str] = []
    for pattern in patterns:
        for path in workspace_root.glob(pattern):
            if path.is_file():
                matches.append(str(path.relative_to(workspace_root)))
    return sorted(set(matches))


def _paths_mentioned_in_text(workspace_root: Path, text: str) -> list[str]:
    matches: list[str] = []
    for matched in _PATH_RE.findall(text):
        candidate = (workspace_root / matched).resolve()
        try:
            if candidate.is_relative_to(workspace_root) and candidate.is_file():
                matches.append(str(candidate.relative_to(workspace_root)))
        except Exception:
            continue
    return sorted(set(matches))


def _build_checks(
    scenario_id: str,
    *,
    result: dict[str, Any],
    workspace_root: Path,
) -> list[dict[str, Any]]:
    final_text = _final_agent_text(result)
    tool_names = _tool_names(result)
    outputs = _artifact_matches(
        workspace_root,
        [
            "outputs/**/*",
            "outputs/agent-report/**/*",
            "data/**/*",
            "*.csv",
            "*.tsv",
            "*.json",
            "*.md",
            "reports/**/*",
        ],
    )
    text_artifacts = _paths_mentioned_in_text(workspace_root, final_text)
    outputs = sorted(set(outputs + text_artifacts))

    checks: list[dict[str, Any]] = [
        {
            "id": "conversation_completed",
            "description": "Agent finished the turn and is no longer running",
            "passed": not bool(result.get("status", {}).get("is_running")),
            "details": result.get("status", {}),
        },
        {
            "id": "assistant_reply_present",
            "description": "Assistant produced a final text reply",
            "passed": bool(final_text.strip()),
            "details": final_text[:200],
        },
    ]

    if scenario_id == "pubmed_crispr_base_editing":
        checks.extend(
            [
                {
                    "id": "recent_search_tool_used",
                    "description": "Agent used a search-capable tool",
                    "passed": bool({"web_search", "shell"} & tool_names),
                    "details": sorted(tool_names),
                },
                {
                    "id": "citations_or_links_present",
                    "description": "Final answer includes source links",
                    "passed": bool(_URL_RE.search(final_text)),
                    "details": final_text[:300],
                },
            ]
        )
        return checks

    if scenario_id == "workflow_recommendation_from_fastqs":
        checks.extend(
            [
                {
                    "id": "workspace_scan_tool_used",
                    "description": "Agent scanned the workspace to discover files",
                    "passed": bool({"glob", "file_read", "grep", "shell"} & tool_names),
                    "details": sorted(tool_names),
                },
                {
                    "id": "fastq_context_in_reply",
                    "description": "Final reply references discovered FASTQ inputs or workflow recommendation",
                    "passed": "fastq" in final_text.lower() or "workflow" in final_text.lower(),
                    "details": final_text[:300],
                },
            ]
        )
        return checks

    if scenario_id == "failed_run_diagnosis":
        checks.extend(
            [
                {
                    "id": "diagnostics_inspected",
                    "description": "Agent inspected logs or diagnostic files",
                    "passed": bool({"file_read", "glob", "shell"} & tool_names),
                    "details": sorted(tool_names),
                },
                {
                    "id": "root_cause_and_next_step",
                    "description": "Final reply includes a root cause hypothesis and next action",
                    "passed": any(keyword in final_text.lower() for keyword in ("root cause", "likely", "next", "retry", "resume")),
                    "details": final_text[:300],
                },
            ]
        )
        return checks

    artifact_required = scenario_id in {
        "rna_seq_differential_expression",
        "clinical_survival_analysis",
        "single_cell_10x_analysis",
        "omics_script_execution",
        "cohort_comparison_report",
    }

    code_required = scenario_id in {
        "rna_seq_differential_expression",
        "clinical_survival_analysis",
        "single_cell_10x_analysis",
        "virtual_screen_egfr_chembl",
        "gene_list_enrichment_report",
        "omics_script_execution",
        "cohort_comparison_report",
    }

    if code_required:
        checks.append(
            {
                "id": "code_execution_tool_used",
                "description": "Agent used execute_code or shell to do the work directly",
                "passed": bool(_CODE_TOOLS & tool_names),
                "details": sorted(tool_names),
            }
        )

    if artifact_required:
        checks.append(
            {
                "id": "artifacts_written",
                "description": "Workspace contains output artifacts after the run",
                "passed": bool(outputs),
                "details": outputs[:20],
            }
        )

    if scenario_id == "cohort_comparison_report":
        checks.append(
            {
                "id": "markdown_report_written",
                "description": "A markdown comparison report was generated",
                "passed": bool(_artifact_matches(workspace_root, ["outputs/**/*.md", "**/*.md"])),
                "details": _artifact_matches(workspace_root, ["outputs/**/*.md", "**/*.md"])[:20],
            }
        )

    if scenario_id == "virtual_screen_egfr_chembl":
        checks.append(
            {
                "id": "egfr_context_present",
                "description": "Final reply stays grounded in EGFR / SAR context",
                "passed": "egfr" in final_text.lower() and "sar" in final_text.lower(),
                "details": final_text[:300],
            }
        )

    return checks


def score_scenario_result(
    scenario: dict[str, Any],
    *,
    result: dict[str, Any],
    workspace_root: Path,
) -> dict[str, Any]:
    checks = _build_checks(scenario["id"], result=result, workspace_root=workspace_root)
    passed_checks = sum(1 for check in checks if check["passed"])
    total_checks = len(checks)
    final_reply_preview = _final_agent_text(result)[:500]
    final_reply_lower = final_reply_preview.lower()
    classification = "pass" if passed_checks == total_checks else "agent_fail"
    if classification != "pass" and any(pattern in final_reply_lower for pattern in _INFRA_ERROR_PATTERNS):
        classification = "infra_fail"
    return {
        "passed": passed_checks == total_checks,
        "passed_checks": passed_checks,
        "failed_checks": total_checks - passed_checks,
        "total_checks": total_checks,
        "checks": checks,
        "classification": classification,
        "tool_names": sorted(_tool_names(result)),
        "event_names": sorted(_event_names(result)),
        "final_reply_preview": final_reply_preview,
    }
