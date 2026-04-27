"""Nextflow workflow validation using regex parsing.

Handles parsing Nextflow files, extracting processes, parameters,
and dependencies via pipe operators and .out references.
"""

from __future__ import annotations

import re

from app.services.validators.types import (
    ValidationError,
    ValidationResult,
    WorkflowDependency,
    WorkflowParameter,
    WorkflowTask,
    find_matching_brace,
    find_matching_paren,
    infer_is_internal,
    infer_source_hint,
    infer_value_kind,
)


class NextflowValidator:
    """Validates Nextflow workflow files."""

    def validate(self, content: str, file_name: str | None) -> ValidationResult:
        """Validate Nextflow using regex parsing."""
        result = ValidationResult(valid=True)
        errors = []

        has_process = bool(re.search(r"\bprocess\s+\w+\s*\{", content))
        has_workflow = bool(
            re.search(r"\bworkflow\s*\{|\bworkflow\s+\w+\s*\{", content)
        )

        if not (has_process or has_workflow):
            errors.append(
                ValidationError(None, None, "No process or workflow block found")
            )
            result.valid = False
            result.errors = errors
            return result

        if content.count("{") != content.count("}"):
            errors.append(
                ValidationError(
                    None,
                    None,
                    f"Unmatched braces: {content.count('{')} opening vs {content.count('}')} closing",
                )
            )
            result.valid = False

        main_wf = re.search(r"\bworkflow\s+(\w+)\s*\{", content)
        result.workflow_name = (
            main_wf.group(1)
            if main_wf
            else (file_name.replace(".nf", "") if file_name else "main")
        )

        for match in re.finditer(r"process\s+(\w+)\s*\{", content):
            process_name = match.group(1)
            start = match.end() - 1
            end = find_matching_brace(content, start)
            if end > start:
                body = content[start : end + 1]
                container_match = re.search(r'container\s+["\']([^"\']+)["\']', body)
                result.tasks.append(
                    WorkflowTask(
                        name=process_name,
                        container=(
                            container_match.group(1) if container_match else None
                        ),
                    )
                )

        seen_params: set[str] = set()

        for match in re.finditer(r"params\.(\w+)\s*=\s*([^\n]+)", content):
            name = match.group(1)
            seen_params.add(name)
            default = match.group(2).strip()
            value_kind = infer_value_kind("Any", name=name, default=default)
            result.inputs.append(
                WorkflowParameter(
                    name=name,
                    type="Any",
                    default=default,
                    optional=True,
                    value_kind=value_kind,
                    source_hint=infer_source_hint(name=name, value_kind=value_kind),
                    is_internal=infer_is_internal(name),
                )
            )

        for match in re.finditer(r"params\.(\w+)\b", content):
            name = match.group(1)
            if name in seen_params:
                continue
            seen_params.add(name)
            value_kind = infer_value_kind("Any", name=name, default=None)
            result.inputs.append(
                WorkflowParameter(
                    name=name,
                    type="Any",
                    default=None,
                    optional=False,
                    value_kind=value_kind,
                    source_hint=infer_source_hint(name=name, value_kind=value_kind),
                    is_internal=infer_is_internal(name),
                )
            )

        for pipe in re.finditer(r"(\w+)\s*\|\s*(\w+)", content):
            result.dependencies.append(
                WorkflowDependency(source=pipe.group(1), target=pipe.group(2))
            )

        self._extract_dependencies(content, result.tasks, result.dependencies)

        result.errors = errors
        return result

    def _extract_dependencies(
        self,
        content: str,
        tasks: list[WorkflowTask],
        dependencies: list[WorkflowDependency],
    ) -> None:
        """Extract dependencies from process invocations in Nextflow workflow blocks.

        Matches patterns like:
        - PROCESS(OTHER.out)
        - PROCESS(OTHER.out.channel)
        - PROCESS(OTHER.out.stats.collect(), ANOTHER.out.data)
        - PROCESS(\n    OTHER.out.foo,\n    ANOTHER.out.bar\n  )
        """
        process_names = {t.name for t in tasks}

        for wf_match in re.finditer(r"\bworkflow\s*(?:\w+\s*)?\{", content):
            wf_start = wf_match.end() - 1
            wf_end = find_matching_brace(content, wf_start)
            if wf_end <= wf_start:
                continue
            wf_body = content[wf_start : wf_end + 1]

            for invocation in re.finditer(r"(\b[A-Z][A-Z0-9_]*)\s*\(", wf_body):
                target_process = invocation.group(1)

                if target_process not in process_names:
                    continue

                paren_start = invocation.end() - 1
                paren_end = find_matching_paren(wf_body, paren_start)
                if paren_end <= paren_start:
                    continue

                args_block = wf_body[paren_start + 1 : paren_end]

                for out_ref in re.finditer(r"\b([A-Z][A-Z0-9_]*)\.out\b", args_block):
                    source_process = out_ref.group(1)
                    if source_process in process_names:
                        dep = WorkflowDependency(
                            source=source_process, target=target_process
                        )
                        if not any(
                            d.source == dep.source and d.target == dep.target
                            for d in dependencies
                        ):
                            dependencies.append(dep)
