"""WDL workflow validation using miniwdl and regex fallback.

Handles parsing WDL files, extracting parameters, tasks, and dependencies
via both the miniwdl AST and basic regex patterns.
"""

from __future__ import annotations

import asyncio
import inspect
import os
import re
import tempfile

from app.services.validators.types import (
    ValidationError,
    ValidationResult,
    WorkflowDependency,
    WorkflowParameter,
    WorkflowTask,
    find_matching_brace,
    infer_is_internal,
    infer_source_hint,
    infer_value_kind,
)


class WdlValidator:
    """Validates WDL workflow files."""

    def validate(self, content: str, file_name: str | None) -> ValidationResult:
        """Validate WDL using miniwdl library."""
        try:
            import WDL
        except ImportError:
            return self._validate_basic(content, file_name)

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            return self._validate_basic(content, file_name)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".wdl", delete=False) as f:
            f.write(content)
            temp_path = f.name

        try:
            doc = WDL.load(temp_path)
            if inspect.isawaitable(doc):
                if hasattr(doc, "close"):
                    doc.close()
                return self._validate_basic(content, file_name)
            result = ValidationResult(valid=True)

            if doc.workflow:
                wf = doc.workflow
                result.workflow_name = wf.name
                result.version = doc.wdl_version
                result.description = wf.meta.get("description") if wf.meta else None

                for inp in wf.available_inputs:
                    inp_type = getattr(inp, "type", None)
                    inferred_type = str(inp_type) if inp_type else "Unknown"
                    value_kind = infer_value_kind(inferred_type, name=inp.name)
                    result.inputs.append(
                        WorkflowParameter(
                            name=inp.name,
                            type=inferred_type,
                            optional=inp_type.optional if inp_type else False,
                            default=(
                                str(inp.expr) if getattr(inp, "expr", None) else None
                            ),
                            value_kind=value_kind,
                            source_hint=infer_source_hint(
                                name=inp.name,
                                value_kind=value_kind,
                            ),
                            is_internal=infer_is_internal(inp.name),
                        )
                    )

                for out in wf.effective_outputs:
                    out_type = getattr(out, "type", None)
                    inferred_type = str(out_type) if out_type else "Unknown"
                    value_kind = infer_value_kind(inferred_type, name=out.name)
                    result.outputs.append(
                        WorkflowParameter(
                            name=out.name,
                            type=inferred_type,
                            optional=out_type.optional if out_type else False,
                            value_kind=value_kind,
                            source_hint=infer_source_hint(
                                name=out.name,
                                value_kind=value_kind,
                            ),
                        )
                    )

            for task in doc.tasks:
                container = None
                if task.runtime:
                    docker_expr = task.runtime.get("docker")
                    if docker_expr:
                        container = str(docker_expr)
                    else:
                        image_expr = task.runtime.get("image")
                        if image_expr:
                            container = str(image_expr)

                result.tasks.append(
                    WorkflowTask(
                        name=task.name,
                        inputs=[inp.name for inp in task.inputs],
                        outputs=[out.name for out in task.outputs],
                        container=container,
                    )
                )

            if doc.workflow:
                self._extract_dependencies(doc.workflow, result.dependencies)

            return result

        except Exception:
            return self._validate_basic(content, file_name)
        finally:
            os.unlink(temp_path)

    def _validate_basic(
        self, content: str, file_name: str | None
    ) -> ValidationResult:
        """Basic WDL validation without miniwdl library."""
        result = ValidationResult(valid=True)
        errors = []

        has_workflow = bool(re.search(r"\bworkflow\s+\w+\s*\{", content))
        has_task = bool(re.search(r"\btask\s+\w+\s*\{", content))

        if not (has_workflow or has_task):
            errors.append(
                ValidationError(None, None, "No workflow or task block found")
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

        version_match = re.search(r"version\s+([\d.]+)", content)
        result.version = version_match.group(1) if version_match else None

        wf_match = re.search(r"\bworkflow\s+(\w+)\s*\{", content)
        result.workflow_name = (
            wf_match.group(1)
            if wf_match
            else (file_name.replace(".wdl", "") if file_name else "main")
        )
        wf_body = None
        if wf_match:
            wf_start = wf_match.end() - 1
            wf_end = find_matching_brace(content, wf_start)
            if wf_end > wf_start:
                wf_body = content[wf_start : wf_end + 1]

        if wf_body:
            result.inputs = self._extract_parameters_from_block(
                wf_body,
                block_name="input",
                include_internal=True,
            )
            result.outputs = self._extract_parameters_from_block(
                wf_body,
                block_name="output",
                include_internal=False,
            )

        for match in re.finditer(r"\btask\s+(\w+)\s*\{", content):
            task_name = match.group(1)
            start = match.end() - 1
            end = find_matching_brace(content, start)
            if end > start:
                body = content[start : end + 1]
                container_match = re.search(
                    r'(?:docker|image):\s*["\']([^"\']+)["\']', body
                )
                result.tasks.append(
                    WorkflowTask(
                        name=task_name,
                        container=(
                            container_match.group(1) if container_match else None
                        ),
                    )
                )

        self._extract_dependencies_basic(content, result.tasks, result.dependencies)

        result.errors = errors
        return result

    def _extract_parameters_from_block(
        self,
        content: str,
        *,
        block_name: str,
        include_internal: bool,
    ) -> list[WorkflowParameter]:
        block_match = re.search(rf"\b{block_name}\s*\{{", content)
        if not block_match:
            return []

        start = block_match.end() - 1
        end = find_matching_brace(content, start)
        if end <= start:
            return []

        block = content[start + 1 : end]
        parameters: list[WorkflowParameter] = []
        for raw_line in block.splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if not line:
                continue
            match = re.match(
                r"^(?P<type>[A-Za-z][A-Za-z0-9_]*(?:\[[^\]]+\])?\??)\s+"
                r"(?P<name>[A-Za-z_][A-Za-z0-9_.]*)"
                r"(?:\s*=\s*(?P<default>.+))?$",
                line,
            )
            if not match:
                continue

            inferred_type = match.group("type")
            name = match.group("name")
            default = match.group("default")
            value_kind = infer_value_kind(
                inferred_type,
                name=name,
                default=default,
            )
            parameters.append(
                WorkflowParameter(
                    name=name,
                    type=inferred_type,
                    optional=inferred_type.endswith("?"),
                    default=default.strip() if isinstance(default, str) else None,
                    value_kind=value_kind,
                    source_hint=infer_source_hint(
                        name=name,
                        value_kind=value_kind,
                    ),
                    is_internal=infer_is_internal(name) if include_internal else False,
                )
            )
        return parameters

    def _extract_dependencies(
        self, workflow, dependencies: list[WorkflowDependency]
    ) -> None:
        """Extract call dependencies from WDL workflow body (miniwdl AST).

        Uses a 3-pass approach matching ``_extract_workflow_dependencies``
        in the WDL adapter: variable declarations, scatter expressions,
        and direct call-input references.
        """
        try:
            import WDL

            seen: set[tuple[str, str]] = set()

            def _add(source: str, target: str) -> None:
                pair = (source, target)
                if source != target and pair not in seen:
                    seen.add(pair)
                    dependencies.append(
                        WorkflowDependency(source=source, target=target)
                    )

            task_names: set[str] = set()
            for task in getattr(
                getattr(workflow, "doc", None) or workflow, "tasks", []
            ):
                task_names.add(task.name)
            for element in getattr(workflow, "body", []):
                self._collect_call_names_ast(element, task_names, WDL)

            def _refs_from_expr(expr_str: str) -> set[str]:
                return {
                    ref
                    for ref in self._find_call_refs(expr_str)
                    if ref in task_names
                }

            var_sources: dict[str, set[str]] = {}

            def process_element(element) -> None:
                if isinstance(element, WDL.Tree.Decl):
                    expr_str = str(getattr(element, "expr", ""))
                    refs = _refs_from_expr(expr_str)
                    if refs:
                        var_name = getattr(element, "name", None)
                        if var_name:
                            var_sources[var_name] = refs

                elif isinstance(element, WDL.Tree.Scatter):
                    scatter_expr = str(getattr(element, "expr", ""))
                    scatter_refs = _refs_from_expr(scatter_expr)
                    for var_name, src_tasks in var_sources.items():
                        if var_name in scatter_expr:
                            scatter_refs |= src_tasks
                    if scatter_refs:
                        for call_name in self._collect_calls_in_body_ast(
                            element, WDL
                        ):
                            for src in scatter_refs:
                                _add(src, call_name)
                    for child in getattr(element, "body", []):
                        process_element(child)

                elif isinstance(element, WDL.Tree.Call):
                    task_name = (
                        element.callee.name
                        if hasattr(element.callee, "name")
                        else str(element.callee)
                    )
                    for inp_expr in element.inputs.values():
                        expr_str = str(inp_expr)
                        for ref in _refs_from_expr(expr_str):
                            _add(ref, task_name)
                        for var_name, src_tasks in var_sources.items():
                            if var_name in expr_str:
                                for src in src_tasks:
                                    _add(src, task_name)
                else:
                    body = getattr(element, "body", None)
                    if body:
                        for child in body:
                            process_element(child)

            for element in workflow.body:
                process_element(element)
        except ImportError:
            pass

    @staticmethod
    def _collect_call_names_ast(element, task_names: set[str], WDL) -> None:
        """Recursively collect call target names from miniwdl AST."""
        if isinstance(element, WDL.Tree.Call):
            callee_name = (
                element.callee.name
                if hasattr(element.callee, "name")
                else str(element.callee)
            )
            task_names.add(callee_name)
        body = getattr(element, "body", None)
        if body:
            for child in body:
                WdlValidator._collect_call_names_ast(child, task_names, WDL)

    @staticmethod
    def _collect_calls_in_body_ast(element, WDL) -> list[str]:
        """Collect all call target names nested inside an element's body."""
        result: list[str] = []
        for child in getattr(element, "body", []):
            if isinstance(child, WDL.Tree.Call):
                callee_name = (
                    child.callee.name
                    if hasattr(child.callee, "name")
                    else str(child.callee)
                )
                result.append(callee_name)
            result.extend(
                WdlValidator._collect_calls_in_body_ast(child, WDL)
            )
        return result

    def _extract_dependencies_basic(
        self,
        content: str,
        tasks: list[WorkflowTask],
        dependencies: list[WorkflowDependency],
    ) -> None:
        """Extract dependencies from WDL workflow using regex.

        Handles three patterns:
        1. Direct call-input refs: ``call B { input: x = A.out }``
        2. Workflow-scope variable declarations that reference task outputs:
           ``Array[...] var = read_tsv(TASK.output)`` or ``var = TASK.output``
        3. Scatter expressions over variables derived from task outputs,
           creating edges from the source task to every call inside the scatter.
        """
        task_names = {t.name for t in tasks}

        wf_match = re.search(r"\bworkflow\s+\w+\s*\{", content)
        if not wf_match:
            return

        wf_start = wf_match.end() - 1
        wf_end = find_matching_brace(content, wf_start)
        if wf_end <= wf_start:
            return

        wf_body = content[wf_start : wf_end + 1]
        seen: set[tuple[str, str]] = set()

        def _add_dep(source: str, target: str) -> None:
            pair = (source, target)
            if pair not in seen and source != target:
                seen.add(pair)
                dependencies.append(WorkflowDependency(source=source, target=target))

        # --- Pass 1: direct task refs inside call blocks ---
        for call_match in re.finditer(r"\bcall\s+(\w+)\s*(\{)?", wf_body):
            target_task = call_match.group(1)
            has_block = call_match.group(2) is not None

            if target_task not in task_names:
                continue

            if has_block:
                block_start = call_match.end() - 1
                block_end = find_matching_brace(wf_body, block_start)
                if block_end > block_start:
                    call_block = wf_body[block_start + 1 : block_end]
                    for ref_match in re.finditer(r"\b(\w+)\.(\w+)\b", call_block):
                        source_task = ref_match.group(1)
                        if source_task in task_names:
                            _add_dep(source_task, target_task)

        # --- Pass 2: workflow-scope variable declarations ---
        var_sources: dict[str, set[str]] = {}
        var_decl_pattern = re.compile(
            r"(?:^|\n)\s*"
            r"(?:Array\[.*?\]\s+|String\s+|File\s+|Int\s+|Float\s+|Boolean\s+)?"
            r"(\w+)\s*=\s*([^\n]+)",
        )
        for decl_match in var_decl_pattern.finditer(wf_body):
            var_name = decl_match.group(1)
            rhs = decl_match.group(2)
            if self._is_inside_call_block(wf_body, decl_match.start()):
                continue
            refs = set()
            for ref_match in re.finditer(r"\b(\w+)\.\w+", rhs):
                ref_task = ref_match.group(1)
                if ref_task in task_names:
                    refs.add(ref_task)
            if refs:
                var_sources[var_name] = refs

        # --- Pass 3: scatter blocks + call inputs referencing scope variables ---
        for scatter_match in re.finditer(
            r"\bscatter\s*\(\s*\w+\s+in\s+(.+?)\s*\)", wf_body
        ):
            scatter_expr = scatter_match.group(1)
            source_tasks: set[str] = set()
            if scatter_expr in var_sources:
                source_tasks = var_sources[scatter_expr]
            for ref_match in re.finditer(r"\b(\w+)\.\w+", scatter_expr):
                ref_task = ref_match.group(1)
                if ref_task in task_names:
                    source_tasks.add(ref_task)
            if not source_tasks:
                continue
            brace_pos = wf_body.find("{", scatter_match.end())
            if brace_pos < 0:
                continue
            brace_end = find_matching_brace(wf_body, brace_pos)
            if brace_end <= brace_pos:
                continue
            scatter_body = wf_body[brace_pos : brace_end + 1]
            for call_in_scatter in re.finditer(r"\bcall\s+(\w+)", scatter_body):
                target_task = call_in_scatter.group(1)
                if target_task in task_names:
                    for src in source_tasks:
                        _add_dep(src, target_task)

        # For call inputs that reference workflow-scope variables
        for call_match in re.finditer(r"\bcall\s+(\w+)\s*\{", wf_body):
            target_task = call_match.group(1)
            if target_task not in task_names:
                continue
            block_start = call_match.end() - 1
            block_end = find_matching_brace(wf_body, block_start)
            if block_end <= block_start:
                continue
            call_block = wf_body[block_start + 1 : block_end]
            for var_name, src_tasks in var_sources.items():
                if re.search(r"\b" + re.escape(var_name) + r"\b", call_block):
                    for src in src_tasks:
                        _add_dep(src, target_task)

    def _is_inside_call_block(self, wf_body: str, pos: int) -> bool:
        """Check if a position is inside a call { ... } block."""
        last_call = -1
        for m in re.finditer(r"\bcall\s+\w+\s*\{", wf_body):
            if m.end() - 1 < pos:
                last_call = m.end() - 1
            else:
                break
        if last_call < 0:
            return False
        brace_end = find_matching_brace(wf_body, last_call)
        return last_call < pos < brace_end

    def _find_call_refs(self, expr_str: str) -> list[str]:
        """Find references to other calls in an expression."""
        pattern = r"([A-Za-z_][A-Za-z0-9_]*)\.[A-Za-z_][A-Za-z0-9_]*"
        return list(set(m.group(1) for m in re.finditer(pattern, expr_str)))
