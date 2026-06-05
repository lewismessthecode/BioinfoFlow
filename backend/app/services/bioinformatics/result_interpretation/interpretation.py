from __future__ import annotations


class ResultInterpretationService:
    def summarize(self, *, metrics: dict, role: str = "bioinformatician") -> dict:
        findings = _technical_findings(metrics)
        return {
            "role": role,
            "summary": _role_summary(findings, role),
            "findings": findings,
            "ready_for_review": not any(item["severity"] == "error" for item in findings),
        }


def _technical_findings(metrics: dict) -> list[dict]:
    findings: list[dict] = []
    duplication_rate = _float(metrics.get("duplication_rate"))
    if duplication_rate is not None and duplication_rate > 0.5:
        findings.append(
            {
                "code": "HIGH_DUPLICATION",
                "severity": "warning",
                "message": "Duplication rate is high.",
                "value": duplication_rate,
            }
        )
    mapping_rate = _float(metrics.get("mapping_rate"))
    if mapping_rate is not None and mapping_rate < 0.7:
        findings.append(
            {
                "code": "LOW_MAPPING_RATE",
                "severity": "error",
                "message": "Mapping rate is below expected threshold.",
                "value": mapping_rate,
            }
        )
    mean_coverage = _float(metrics.get("mean_coverage"))
    if mean_coverage is not None and mean_coverage < 20:
        findings.append(
            {
                "code": "LOW_COVERAGE",
                "severity": "warning",
                "message": "Mean coverage is low for many variant workflows.",
                "value": mean_coverage,
            }
        )
    if not findings:
        findings.append(
            {
                "code": "NO_MAJOR_QC_FLAGS",
                "severity": "info",
                "message": "No major QC flags were detected from provided metrics.",
                "value": None,
            }
        )
    return findings


def _role_summary(findings: list[dict], role: str) -> str:
    errors = [item for item in findings if item["severity"] == "error"]
    warnings = [item for item in findings if item["severity"] == "warning"]
    if role == "wet_lab":
        if errors:
            return "Some samples may not be suitable for downstream analysis."
        if warnings:
            return "Samples are usable but should be reviewed for QC warnings."
        return "Samples look acceptable based on the provided QC metrics."
    if role == "project_manager":
        return f"Batch has {len(errors)} blocking issue(s) and {len(warnings)} warning(s)."
    if role == "report_writer":
        if errors:
            return "Do not proceed to report interpretation until QC issues are resolved."
        return "Results can proceed to report-oriented review with noted caveats."
    if errors:
        return "Technical QC failed for at least one critical metric."
    if warnings:
        return "Technical QC passed with warnings."
    return "Technical QC passed for provided metrics."


def _float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
