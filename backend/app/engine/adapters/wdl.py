from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import settings
from app.engine.adapter import EngineAdapter
from app.engine.backend import EngineEvent, EngineEventType
from app.path_layout import normalize_engine_dir
from app.services.docker_service import DockerService
from app.utils.process import terminate_process_tree

_MINIWDL_ENTRY_MODULE = "app.engine._miniwdl_entry"
_ENGINE_LOGS_KEY = "__engine_logs__"

# miniwdl writes every task-scoped lifecycle event through a logger whose
# name has the shape `wdl.w:<workflow>.t:call-<task>` — true for any WDL
# running on miniwdl, not just Deaf_20. We pin to that shape so we can
# translate these lines into per-task status events without hand-written
# parsers for each workflow.
_TASK_LOG_RE = re.compile(
    r"\bwdl\.w:\w+\.t:call-(?P<task>\S+)\s+(?P<level>NOTICE|WARNING|ERROR)\s+(?P<message>.*)"
)


def _detect_task_update(line: str) -> "EngineEvent | None":
    """Extract a task-level status transition from one miniwdl log line.

    Chooses four authoritative signals per task. In particular:

    * `NOTICE done` is preferred over `NOTICE docker task exit :: state: "complete"`
      because the former fires only when miniwdl's post-task output
      validation also passed. Some failures (e.g. the RESULT task's
      OutputError when a declared File is missing) leave `docker task
      exit state: "complete"` true but still fail the WDL contract.
    * `ERROR ... failed` covers both miniwdl-level task failures and
      docker-level task failures (miniwdl surfaces both with that phrasing).
    """
    match = _TASK_LOG_RE.search(line)
    if match is None:
        return None
    task = match.group("task")
    level = match.group("level")
    message = match.group("message").lower()

    status: str | None = None
    if level == "ERROR" and "failed" in message:
        status = "failed"
    elif level == "NOTICE":
        if message.startswith("done"):
            status = "completed"
        elif "docker task running" in message:
            status = "running"
        elif "task setup" in message:
            status = "submitted"

    if status is None:
        return None
    return EngineEvent(
        EngineEventType.TASK_UPDATE,
        {"name": task, "status": status},
    )


# Match real miniwdl error signals — log-level tags (``ERROR name:`` or
# ``[error]``) and tracebacks — not substrings like ``no_error``,
# ``stderr_file`` or ``error_correction_enabled``.
_WDL_ERROR_LINE_RE = re.compile(
    r"(?:\bERROR\b(?::|\s)|\[error\]|^error:|Traceback)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class RequiredImage:
    full_name: str
    name: str
    tag: str
    registry: str
    auth_config: dict[str, Any] | None = None


class WDLAdapter(EngineAdapter):
    def __init__(self, *, miniwdl_bin: str | None = None) -> None:
        self._binary = _resolve_miniwdl_bin(miniwdl_bin or settings.miniwdl_bin)

    @property
    def engine_name(self) -> str:
        return "wdl"

    @property
    def display_name(self) -> str:
        return "MiniWDL"

    @property
    def binary(self) -> str:
        return self._binary

    @property
    def supports_native_resume(self) -> bool:
        return False

    @property
    def supports_best_effort_resume(self) -> bool:
        return True

    async def pre_submit(self, config: dict, workspace: str) -> dict:
        del workspace
        updated = dict(config)
        runtime = updated.get("runtime")
        runtime = dict(runtime) if isinstance(runtime, dict) else {}
        required_images = _required_images(updated)
        if not required_images:
            updated["runtime"] = runtime
            return updated
        if runtime.get("pull_required_images") is False:
            updated["runtime"] = runtime
            return updated

        docker = DockerService()
        if not await docker.is_available():
            updated["runtime"] = runtime
            return updated

        pulled_images: list[str] = []
        for image in required_images:
            if await docker.inspect_image(image.full_name) is not None:
                continue
            try:
                pull_kwargs: dict[str, Any] = {}
                if image.auth_config is not None:
                    pull_kwargs["auth_config"] = image.auth_config
                async for _event in docker.pull_image(
                    image.name,
                    image.tag,
                    image.registry,
                    **pull_kwargs,
                ):
                    pass
            except Exception as exc:
                raise ValueError(
                    f"Failed to pull required WDL image {image.full_name}: {exc}"
                ) from exc
            pulled_images.append(image.full_name)

        if pulled_images:
            logs = list(updated.get(_ENGINE_LOGS_KEY, []) or [])
            logs.append(
                {
                    "message": "Pulled missing WDL images: " + ", ".join(pulled_images),
                    "level": "info",
                }
            )
            updated[_ENGINE_LOGS_KEY] = logs

        updated["runtime"] = runtime
        return updated

    async def build_command(self, config: dict, workspace: str) -> list[str]:
        run_id = str(config.get("run_id") or "run")

        # Path Contract v3: host path == container path. No translation needed
        # between backend, miniwdl runner, and task containers.
        workflow_path = str(config.get("workflow_path") or "")
        work_dir = _work_dir(config, workspace, run_id=run_id)
        work_dir.mkdir(parents=True, exist_ok=True)
        _seed_resume_work_dir(config, workspace, target=work_dir)
        # Many production WDLs derive output/input file paths from String values such
        # as `outdir` or manifest rows. miniwdl rejects those paths by default unless
        # they appear as explicit File/Directory inputs, so we attach a per-run config
        # that relaxes file_io validation for the runner. This is a platform-level
        # compatibility shim, not a workflow-specific special case.
        cfg_path = work_dir / "miniwdl.cfg"
        await asyncio.to_thread(_write_runner_cfg, cfg_path)

        # Invoke miniwdl via our subprocess entry module so
        # BioinfoflowSwarmContainer is pre-registered in miniwdl's in-process
        # backend registry. Running the raw `miniwdl` binary relies on
        # importlib.metadata entry-point discovery, which silently no-ops on
        # some installs and leaves task containers without our identity mounts.
        cmd = [
            sys.executable,
            "-m",
            _MINIWDL_ENTRY_MODULE,
            "run",
            workflow_path,
            "--dir",
            str(work_dir),
            "--cfg",
            str(cfg_path),
        ]

        inputs = _prepare_inputs(_inputs(config), workspace)
        if inputs:
            inputs_path = Path(
                str(config.get("inputs_path") or (work_dir.parent / "inputs.json"))
            )
            inputs_path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(_write_inputs, inputs_path, inputs)
            cmd.extend(["-i", str(inputs_path)])

        for key, value in _options(config).items():
            cmd.extend([f"--{key}", str(value)])

        return cmd

    def get_resume_token(self, run_config: dict) -> str | None:
        runtime = run_config.get("runtime")
        if isinstance(runtime, dict):
            work_dir = runtime.get("wdl_work_dir")
            if isinstance(work_dir, str) and work_dir.strip():
                return work_dir.strip()
        return None

    def parse_event(self, line: str, stream: str) -> EngineEvent | None:
        if not line:
            return None
        # miniwdl writes task lifecycle events to stderr in its standard
        # logger format. Try to extract per-task transitions first so the
        # frontend DAG can light up nodes; any unmatched line then falls
        # through to plain LOG / ERROR / COMPLETED handling.
        task_event = _detect_task_update(line)
        if task_event is not None:
            return task_event

        if stream == "stderr":
            return EngineEvent(
                EngineEventType.LOG,
                {"message": line, "level": "error"},
            )

        # Treat stdout as a structured log. Only emit ERROR when the line
        # carries an actual log-level tag or a traceback marker. Substring
        # "error" matches false positives miniwdl emits routinely
        # ("no error", "stderr_file", "error_correction_enabled"), and
        # because ERROR is terminal those false positives used to mark
        # successful zero-exit runs as failed. The adapter now relies on
        # the process exit code as the authoritative success signal.
        if _WDL_ERROR_LINE_RE.search(line):
            return EngineEvent(EngineEventType.ERROR, {"message": line})
        lower = line.lower()
        if "done" in lower or "complete" in lower:
            return EngineEvent(EngineEventType.COMPLETED, {"success": True})
        return EngineEvent(EngineEventType.LOG, {"message": line})

    async def cancel(self, *, pid: int | None = None, **kwargs) -> bool:
        if not pid:
            return False
        return await asyncio.to_thread(terminate_process_tree, pid)

    async def post_complete(self, config: dict, workspace: str, status: str) -> None:
        if status != "completed":
            return
        run_id = str(config.get("run_id") or "run")
        work_dir = _work_dir(config, workspace, run_id=run_id)
        outdir = _outdir(config)
        await asyncio.to_thread(_copy_outputs, work_dir, Path(workspace), outdir)

    async def extract_schema(self, source: str | None, **kwargs) -> dict | None:
        if importlib.util.find_spec("WDL") is None:
            return None

        content = kwargs.get("content")
        temp_path: str | None = None
        load_target = source
        source_path = (
            Path(str(source)).expanduser()
            if isinstance(source, str) and source.strip()
            else None
        )

        if source_path and source_path.exists():
            load_target = str(source_path)
        elif isinstance(content, str) and content.strip():
            suffix = Path(
                str(kwargs.get("file_name") or source or "workflow.wdl")
            ).suffix
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=suffix or ".wdl",
                delete=False,
                encoding="utf-8",
            ) as handle:
                handle.write(content)
                temp_path = handle.name
                load_target = temp_path

        if not isinstance(load_target, str) or not load_target.strip():
            return None

        try:
            doc = await _load_wdl_document(load_target)
            return _doc_to_schema(doc)
        except Exception:
            return None
        finally:
            if temp_path:
                os.unlink(temp_path)


def _inputs(config: dict) -> dict:
    request = config.get("request")
    if isinstance(request, dict) and isinstance(request.get("inputs"), dict):
        return dict(request["inputs"])
    inputs = config.get("inputs")
    return dict(inputs) if isinstance(inputs, dict) else {}


def _prepare_inputs(inputs: dict, workspace: str) -> dict:
    prepared = dict(inputs)
    for key, value in list(prepared.items()):
        if not _is_platform_managed_dir_key(key):
            continue
        if not isinstance(value, str) or not value.strip():
            continue
        candidate = Path(value)
        if candidate.is_absolute():
            continue
        prepared[key] = str((Path(workspace) / candidate).resolve(strict=False))
    return prepared


def _is_platform_managed_dir_key(key: object) -> bool:
    text = str(key or "").strip().lower()
    if not text:
        return False
    leaf = text.split(".")[-1]
    return leaf in {"outdir", "output_dir", "publish_dir", "work_dir"}


def _options(config: dict) -> dict:
    options = config.get("options")
    return dict(options) if isinstance(options, dict) else {}


def _outdir(config: dict) -> str | None:
    sources = [
        config.get("params"),
        (config.get("request") or {}).get("params")
        if isinstance(config.get("request"), dict)
        else None,
    ]
    for source in sources:
        if isinstance(source, dict):
            outdir = source.get("outdir")
            if isinstance(outdir, str) and outdir.strip():
                return outdir
    outdir = config.get("outdir")
    return outdir if isinstance(outdir, str) and outdir.strip() else None


def _write_inputs(path: Path, inputs: dict) -> None:
    path.write_text(json.dumps(inputs), encoding="utf-8")


def _write_runner_cfg(path: Path) -> None:
    # Keep the generated config minimal so it's obvious which runner behavior we
    # intentionally override for Bioinfoflow-managed WDL execution.
    #
    # `task_runtime.as_user = true` forces miniwdl to set `--user {uid}:{gid}`
    # on every task container from the invoking process's uid:gid (the backend
    # container runs as root). Without this, the image's `USER` directive wins
    # — many production bioinformatics images (e.g. deaf:V2.0.9.9) ship with a
    # non-root USER, and scripts inside them silently fail to write to the
    # results dir that the backend created as root:root mode 0755.
    path.write_text(
        "[scheduler]\n"
        "container_backend = bioinfoflow_docker_swarm\n"
        "[file_io]\n"
        "allow_any_input = true\n"
        "[task_runtime]\n"
        "as_user = true\n",
        encoding="utf-8",
    )


def _resolve_work_dir(workspace: str, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else Path(workspace) / path


def _work_dir(config: dict, workspace: str, *, run_id: str) -> Path:
    configured = config.get("work_dir")
    if isinstance(configured, str) and configured.strip():
        return _resolve_work_dir(workspace, configured)
    return (
        Path(workspace)
        / "runs"
        / run_id
        / "engine"
        / normalize_engine_dir("wdl")
        / "work"
    )


def _seed_resume_work_dir(config: dict, workspace: str, *, target: Path) -> None:
    resume_work_dir = config.get("resume_work_dir")
    if not isinstance(resume_work_dir, str) or not resume_work_dir.strip():
        return
    source = _resolve_work_dir(workspace, resume_work_dir)
    if source == target or not source.exists() or not source.is_dir():
        return
    try:
        next(target.iterdir())
    except StopIteration:
        shutil.copytree(source, target, dirs_exist_ok=True)


def _copy_outputs(work_dir: Path, workspace: Path, outdir: str | None) -> None:
    """Copy miniwdl outputs into the platform results dir.

    When the workflow declared an `outdir` input we honor it (preserves the
    existing per-workflow layout under `<workspace>/<outdir>/`). When it did
    not, miniwdl leaves outputs under its work dir only, so the run's
    `results/` (where `RunArchiveService.list_outputs` reads from) stays
    empty and the frontend file browser shows nothing after reload.

    Default destination is `<workspace>/results/`, which on a real run is
    the rw sibling mount `runs/{run_id}/results/` per the Path Contract.
    """
    workspace_resolved = workspace.resolve()
    if outdir:
        target = (workspace / outdir).resolve()
        if not target.is_relative_to(workspace_resolved):
            return
    else:
        target = (workspace / "results").resolve()
        # `workspace` itself is the run's results-bearing dir, so target ==
        # workspace is acceptable here too; only reject paths that escape it.
        if not target.is_relative_to(workspace_resolved):
            return

    output_dir = work_dir / "out"
    if output_dir.exists():
        if target.exists() and outdir:
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)
        for item in output_dir.rglob("*"):
            if item.is_dir():
                continue
            dest = target / item.relative_to(output_dir)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dest)
        return

    # Fallback: miniwdl always writes outputs.json at the work dir root with
    # absolute paths into the work dir's per-task `output_links/` tree. Use
    # those when `out/` is missing (older miniwdl layouts, or when the run
    # was resumed from a stale work dir without the staged tree).
    outputs_json = work_dir / "outputs.json"
    if not outputs_json.exists():
        return

    try:
        payload = json.loads(outputs_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return

    raw_outputs = payload.get("outputs") if isinstance(payload, dict) else None
    if not isinstance(raw_outputs, dict):
        return

    target.mkdir(parents=True, exist_ok=True)
    for value in raw_outputs.values():
        for src in _iter_file_paths(value):
            try:
                src_resolved = Path(src).resolve()
            except (OSError, RuntimeError):
                continue
            if not src_resolved.exists() or src_resolved.is_dir():
                continue
            # When falling back from outputs.json the path layout inside the
            # work dir is miniwdl-internal (call-TASK/outputs/...) and not
            # meaningful to surface. Flatten to basename — the file browser
            # cares about the file existing, not its internal nesting.
            dest = target / src_resolved.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_resolved, dest)


def _iter_file_paths(value):
    """Yield absolute file path strings from a miniwdl outputs.json value."""
    if isinstance(value, str):
        if value:
            yield value
    elif isinstance(value, list):
        for item in value:
            yield from _iter_file_paths(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_file_paths(item)


def _resolve_miniwdl_bin(candidate: str) -> str:
    normalized = (candidate or "").strip() or "miniwdl"
    resolved = shutil.which(normalized)
    if resolved:
        return resolved

    path = Path(normalized).expanduser()
    if not path.is_absolute():
        path = (Path(settings.repo_root).expanduser() / path).resolve()
    if path.exists():
        return str(path)

    fallback = shutil.which("miniwdl")
    return fallback or str(path)


def _required_images(config: dict) -> list[RequiredImage]:
    runtime = config.get("runtime")
    if not isinstance(runtime, dict):
        return []
    images = runtime.get("required_images")
    if not isinstance(images, list):
        return []

    required: list[RequiredImage] = []
    seen: set[str] = set()
    for image in images:
        required_image = _required_image_from_runtime_item(image)
        if required_image is None or required_image.full_name in seen:
            continue
        seen.add(required_image.full_name)
        required.append(required_image)
    return required


def _required_image_from_runtime_item(value: Any) -> RequiredImage | None:
    if isinstance(value, str):
        full_name = value.strip()
        if not full_name:
            return None
        name, tag, registry = _parse_image_reference(full_name)
        return RequiredImage(
            full_name=full_name,
            name=name,
            tag=tag,
            registry=registry,
        )
    if not isinstance(value, dict):
        return None
    full_name = str(value.get("full_name") or "").strip()
    if not full_name:
        return None
    parsed_name, parsed_tag, parsed_registry = _parse_image_reference(full_name)
    name = str(value.get("name") or parsed_name).strip() or parsed_name
    tag = str(value.get("tag") or parsed_tag).strip() or parsed_tag
    registry = str(value.get("registry") or parsed_registry).strip() or parsed_registry
    auth_config = value.get("auth_config")
    return RequiredImage(
        full_name=full_name,
        name=name,
        tag=tag,
        registry=registry,
        auth_config=dict(auth_config) if isinstance(auth_config, dict) else None,
    )


def _parse_image_reference(full_name: str) -> tuple[str, str, str]:
    image = full_name.strip()
    registry = "docker.io"
    remainder = image

    first_segment = image.split("/", 1)[0]
    if "/" in image and (
        "." in first_segment or ":" in first_segment or first_segment == "localhost"
    ):
        registry, remainder = image.split("/", 1)

    tag = "latest"
    last_segment = remainder.rsplit("/", 1)[-1]
    if ":" in last_segment:
        remainder, tag = remainder.rsplit(":", 1)

    return remainder, tag, registry


async def _load_wdl_document(path: str):
    import WDL

    return await asyncio.to_thread(WDL.load, path)


def _doc_to_schema(doc) -> dict:
    from app.services.validators.types import (
        infer_is_internal,
        infer_source_hint,
        infer_value_kind,
    )

    workflow_name = None
    version = getattr(doc, "wdl_version", None)
    description = None
    inputs = []
    outputs = []
    tasks = []
    dependencies: list[dict[str, str]] = []
    seen_tasks: set[str] = set()

    workflow = getattr(doc, "workflow", None)
    if workflow is not None:
        workflow_name = workflow.name
        if getattr(workflow, "meta", None):
            description = workflow.meta.get("description")
        for available_input in getattr(workflow, "available_inputs", []):
            if "." in available_input.name:
                continue
            value = getattr(available_input, "value", None)
            type_value = getattr(value, "type", value)
            inputs.append(
                {
                    "name": available_input.name,
                    "type": str(type_value),
                    "optional": bool(getattr(type_value, "optional", False)),
                    "default": (
                        str(getattr(value, "expr", None))
                        if getattr(value, "expr", None) is not None
                        else None
                    ),
                    "description": None,
                    "value_kind": infer_value_kind(
                        str(type_value),
                        name=available_input.name,
                    ),
                    "source_hint": infer_source_hint(
                        name=available_input.name,
                        value_kind=infer_value_kind(
                            str(type_value),
                            name=available_input.name,
                        ),
                    ),
                    "is_internal": infer_is_internal(available_input.name),
                }
            )
        for effective_output in getattr(workflow, "effective_outputs", []):
            value = getattr(effective_output, "value", None)
            output_name = effective_output.name.split(".")[-1]
            output_type = str(value)
            output_value_kind = infer_value_kind(output_type, name=output_name)
            outputs.append(
                {
                    "name": output_name,
                    "type": output_type,
                    "optional": bool(getattr(value, "optional", False)),
                    "default": None,
                    "description": None,
                    "value_kind": output_value_kind,
                    "source_hint": infer_source_hint(
                        name=output_name,
                        value_kind=output_value_kind,
                    ),
                    "is_internal": False,
                }
            )
        _extract_workflow_dependencies(workflow, dependencies)
        _extract_import_call_dependencies(doc, workflow, dependencies)

    for task in getattr(doc, "tasks", []):
        _append_task_schema(tasks, seen_tasks, task)
    for imported_doc in _imported_docs(doc):
        imported_workflow = getattr(imported_doc, "workflow", None)
        if imported_workflow is not None:
            _extract_workflow_dependencies(imported_workflow, dependencies)
        for task in getattr(imported_doc, "tasks", []):
            _append_task_schema(tasks, seen_tasks, task)

    return {
        "workflow_name": workflow_name,
        "version": version,
        "description": description,
        "inputs": inputs,
        "outputs": outputs,
        "tasks": tasks,
        "dependencies": dependencies,
    }


def _append_task_schema(tasks: list[dict], seen_tasks: set[str], task) -> None:
    if task.name in seen_tasks:
        return
    seen_tasks.add(task.name)

    container = None
    runtime = getattr(task, "runtime", None) or {}
    docker_expr = runtime.get("docker")
    image_expr = runtime.get("image")
    if docker_expr is not None:
        container = _stringify_expr(docker_expr)
    elif image_expr is not None:
        container = _stringify_expr(image_expr)

    tasks.append(
        {
            "name": task.name,
            "inputs": [task_input.name for task_input in getattr(task, "inputs", [])],
            "outputs": [
                task_output.name for task_output in getattr(task, "outputs", [])
            ],
            "container": container,
        }
    )


def _imported_docs(doc) -> list:
    imported = []
    for item in getattr(doc, "imports", []) or []:
        subdoc = getattr(item, "doc", None)
        if subdoc is not None:
            imported.append(subdoc)
    return imported


def _extract_import_call_dependencies(
    doc, workflow, dependencies: list[dict[str, str]]
) -> None:
    import_metadata = _imported_workflow_metadata(doc)
    if not import_metadata:
        return

    seen = {(item["source"], item["target"]) for item in dependencies}

    def _add(source: str, target: str) -> None:
        pair = (source, target)
        if source != target and pair not in seen:
            seen.add(pair)
            dependencies.append({"source": source, "target": target})

    call_outputs: dict[str, dict[str, set[str]]] = {}
    for element in getattr(workflow, "body", []):
        try:
            import WDL
        except ImportError:
            return
        if not isinstance(element, WDL.Tree.Call):
            continue

        callee = getattr(element, "callee", None)
        call_alias = getattr(element, "name", None)
        if not call_alias or callee is None:
            continue

        if isinstance(callee, WDL.Tree.Task):
            for input_name, expr in getattr(element, "inputs", {}).items():
                del input_name
                for source_alias, source_output in _find_call_output_refs(str(expr)):
                    producers = call_outputs.get(source_alias, {}).get(
                        source_output, set()
                    )
                    for producer in producers:
                        _add(producer, callee.name)
            output_names = {
                output.name for output in getattr(callee, "outputs", []) if output.name
            }
            call_outputs[call_alias] = {
                output_name: {callee.name} for output_name in output_names
            }
            continue

        subworkflow_name = getattr(callee, "name", None)
        metadata = import_metadata.get(subworkflow_name)
        if metadata is None:
            continue

        for input_name, expr in getattr(element, "inputs", {}).items():
            target_tasks = set(metadata["input_consumers"].get(str(input_name), set()))
            if not target_tasks:
                continue
            for source_alias, source_output in _find_call_output_refs(str(expr)):
                producers = call_outputs.get(source_alias, {}).get(source_output, set())
                for producer in producers:
                    for target in target_tasks:
                        _add(producer, target)

        call_outputs[call_alias] = metadata["output_producers"]


def _imported_workflow_metadata(doc) -> dict[str, dict[str, dict[str, set[str]]]]:
    metadata: dict[str, dict[str, dict[str, set[str]]]] = {}
    for imported_doc in _imported_docs(doc):
        workflow = getattr(imported_doc, "workflow", None)
        if workflow is None or not getattr(workflow, "name", None):
            continue
        metadata[workflow.name] = {
            "input_consumers": _workflow_input_consumers(workflow),
            "output_producers": _workflow_output_producers(workflow),
        }
    return metadata


def _workflow_input_consumers(workflow) -> dict[str, set[str]]:
    consumers: dict[str, set[str]] = {}
    workflow_inputs = {inp.name for inp in getattr(workflow, "available_inputs", [])}
    for element in getattr(workflow, "body", []):
        call_name = getattr(getattr(element, "callee", None), "name", None)
        if not call_name:
            continue
        for input_name, expr in getattr(element, "inputs", {}).items():
            expr_text = str(expr).strip()
            if expr_text in workflow_inputs:
                consumers.setdefault(str(input_name), set()).add(call_name)
    return consumers


def _workflow_output_producers(workflow) -> dict[str, set[str]]:
    producers: dict[str, set[str]] = {}
    for output in getattr(workflow, "outputs", []) or []:
        expr_text = str(getattr(output, "expr", "")).strip()
        for source_alias, source_output in _find_call_output_refs(expr_text):
            del source_output
            producers.setdefault(output.name, set()).add(source_alias)
    return producers


def _find_call_output_refs(expr_str: str) -> list[tuple[str, str]]:
    pattern = r"([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)"
    return list(
        {(match.group(1), match.group(2)) for match in re.finditer(pattern, expr_str)}
    )


def _extract_workflow_dependencies(
    workflow, dependencies: list[dict[str, str]]
) -> None:
    try:
        import WDL
    except ImportError:
        return

    seen: set[tuple[str, str]] = set()

    def _add(source: str, target: str) -> None:
        pair = (source, target)
        if source != target and pair not in seen:
            seen.add(pair)
            dependencies.append({"source": source, "target": target})

    # Build a map of workflow-scope variable names to the task(s) they reference.
    # E.g. ``Array[...] x = read_tsv(TASK.output)`` -> {"x": {"TASK"}}
    var_sources: dict[str, set[str]] = {}

    # Collect all task names defined in the document.
    task_names: set[str] = set()
    for task in getattr(getattr(workflow, "doc", None) or workflow, "tasks", []):
        task_names.add(task.name)
    # Also include call names (tasks defined externally are still referenced).
    for element in getattr(workflow, "body", []):
        _collect_call_names(element, task_names, WDL)

    def _refs_from_expr(expr_str: str) -> set[str]:
        return {ref for ref in _find_call_refs(expr_str) if ref in task_names}

    def process_element(element) -> None:
        if isinstance(element, WDL.Tree.Decl):
            # Workflow-scope variable declaration.
            expr_str = str(getattr(element, "expr", ""))
            refs = _refs_from_expr(expr_str)
            if refs:
                var_name = getattr(element, "name", None)
                if var_name:
                    var_sources[var_name] = refs

        elif isinstance(element, WDL.Tree.Scatter):
            # Check if scatter expression references a variable derived from a task.
            scatter_expr = str(getattr(element, "expr", ""))
            # Direct task refs in scatter expression.
            scatter_refs = _refs_from_expr(scatter_expr)
            # Also check if the scatter iterates over a var that maps to tasks.
            for var_name, src_tasks in var_sources.items():
                if var_name in scatter_expr:
                    scatter_refs |= src_tasks
            # Link scatter-source tasks to all calls inside the scatter body.
            if scatter_refs:
                for call_name in _collect_calls_in_body(element, WDL):
                    for src in scatter_refs:
                        _add(src, call_name)
            # Recurse into scatter body for nested calls with direct refs.
            for child in getattr(element, "body", []):
                process_element(child)

        elif isinstance(element, WDL.Tree.Call):
            task_name = (
                element.callee.name
                if hasattr(element.callee, "name")
                else str(element.callee)
            )
            for expr in getattr(element, "inputs", {}).values():
                expr_str = str(expr)
                # Direct task refs in call inputs.
                for ref in _refs_from_expr(expr_str):
                    _add(ref, task_name)
                # Variable refs that map to tasks.
                for var_name, src_tasks in var_sources.items():
                    if var_name in expr_str:
                        for src in src_tasks:
                            _add(src, task_name)
        else:
            body = getattr(element, "body", None)
            if body:
                for child in body:
                    process_element(child)

    for element in getattr(workflow, "body", []):
        process_element(element)


def _collect_call_names(element, task_names: set[str], WDL) -> None:
    """Recursively collect call target names from workflow body elements."""
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
            _collect_call_names(child, task_names, WDL)


def _collect_calls_in_body(element, WDL) -> list[str]:
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
        result.extend(_collect_calls_in_body(child, WDL))
    return result


def _find_call_refs(expr_str: str) -> list[str]:
    pattern = r"([A-Za-z_][A-Za-z0-9_]*)\.[A-Za-z_][A-Za-z0-9_]*"
    return list({match.group(1) for match in re.finditer(pattern, expr_str)})


def _stringify_expr(expr) -> str | None:
    text = str(expr).strip().strip("\"'")
    return text or None
