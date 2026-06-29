"""Pure helper functions extracted from RunService.

Every function here is stateless — it depends only on its arguments.
"""

from __future__ import annotations

import csv
import io
import json
import re
import secrets
import shutil
import uuid
from collections.abc import Callable, Sequence
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from app.models.run import Run, RunStatus
from app.models.run_config import RunConfigHelper


# ── regex constants (moved from RunService class body) ──────────────────────

_PATHLIKE_KEY_RE = re.compile(
    r"(path|file|input|reads?|reference|fasta|fastq|bam|vcf|cram|samplesheet|genome|index)",
    re.IGNORECASE,
)
_RESUME_RUN_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{1,99}$")


# ── ID generation ───────────────────────────────────────────────────────────


def generate_run_id() -> str:
    return f"run_{secrets.token_hex(16)}"


def generate_mock_run_id(variant: str) -> str:
    return f"run_mock_{variant}_{secrets.token_hex(2)}"


# ── config helpers ──────────────────────────────────────────────────────────


def config_helper(config: dict | None) -> RunConfigHelper:
    return RunConfigHelper(config if isinstance(config, dict) else {})


def copy_config(config: dict | None) -> dict:
    if isinstance(config, dict):
        return deepcopy(config)
    return {}


def sync_run_config_aliases(
    config: dict,
    *,
    params: dict | None = None,
    inputs: dict | None = None,
    config_overrides: dict | None = None,
    resolved_runspec: dict | None = None,
) -> dict:
    request = dict(config.get("request", {}) or {})
    resolved = dict(config.get("resolved", {}) or {})

    if params is not None:
        config["params"] = params
        request["params"] = params
    if inputs is not None:
        config["inputs"] = inputs
        request["inputs"] = inputs
    if config_overrides is not None:
        config["config_overrides"] = config_overrides
        request["config_overrides"] = config_overrides
    if request:
        config["request"] = request

    if resolved_runspec is not None:
        config["resolved_runspec"] = resolved_runspec
        resolved["runspec"] = resolved_runspec
    if resolved:
        config["resolved"] = resolved

    if request or resolved:
        config.setdefault("config_schema_version", 1)
        config.setdefault("runtime", {})
        config.setdefault("policy", {})
        config.setdefault("ui", {"dag": {}})
    return config


# ── path / workspace helpers ────────────────────────────────────────────────


def safe_workspace(root: Path, relative_path: str) -> Path:
    target = (root / relative_path).resolve()
    if not target.is_relative_to(root):
        raise PermissionError("workspace path escapes project root")
    return target


def binary_exists(binary: str) -> bool:
    if shutil.which(binary):
        return True
    candidate = Path(binary).expanduser()
    return candidate.exists() and candidate.is_file()


# ── path-like key detection ─────────────────────────────────────────────────


def is_path_like_key(key: str) -> bool:
    lowered = key.lower()
    if lowered.endswith("_mode"):
        return False
    if lowered in {"outdir", "output_dir", "publish_dir", "work_dir"}:
        return False
    if lowered.endswith("_url") or lowered.endswith("_uri"):
        return False
    return bool(_PATHLIKE_KEY_RE.search(lowered))


def is_external_reference(value: str) -> bool:
    lowered = value.lower()
    if re.match(r"^[a-z][a-z0-9+.-]*://", lowered):
        return True
    if "${" in value:
        return True
    return False


def has_glob(value: str) -> bool:
    return any(char in value for char in "*?[]{}")


def iter_string_values(payload, prefix: str = ""):
    if isinstance(payload, dict):
        for key, value in payload.items():
            key_name = f"{prefix}.{key}" if prefix else str(key)
            yield from iter_string_values(value, key_name)
        return
    if isinstance(payload, list):
        for index, value in enumerate(payload):
            key_name = f"{prefix}[{index}]"
            yield from iter_string_values(value, key_name)
        return
    if isinstance(payload, str):
        yield prefix, payload


# ── runspec resolution ──────────────────────────────────────────────────────


def build_resolved_runspec(*, workspace_path: Path, params: dict, inputs: dict) -> dict:
    resolved_params, param_files = resolve_payload_paths(
        workspace_path=workspace_path,
        payload=params,
        scope="params",
    )
    resolved_inputs, input_files = resolve_payload_paths(
        workspace_path=workspace_path,
        payload=inputs,
        scope="inputs",
    )
    return {
        "workspace": str(workspace_path),
        "params": resolved_params,
        "inputs": resolved_inputs,
        "files": [*param_files, *input_files],
    }


def resolve_payload_paths(
    *, workspace_path: Path, payload: dict, scope: str
) -> tuple[dict, list[dict]]:
    resolved: dict = {}
    files: list[dict] = []
    for key, value in payload.items():
        if not isinstance(value, str) or not is_path_like_key(str(key)):
            resolved[key] = value
            continue
        if is_external_reference(value):
            resolved[key] = value
            continue
        candidate = value.strip()
        if not candidate:
            resolved[key] = value
            continue
        candidate_path = Path(candidate)
        if candidate_path.is_absolute():
            absolute = str(candidate_path.resolve(strict=False))
            resolved[key] = absolute
            files.append(
                {
                    "scope": scope,
                    "key": str(key),
                    "kind": "absolute_path",
                    "raw": value,
                    "resolved": absolute,
                }
            )
            continue
        if has_glob(candidate):
            absolute = str((workspace_path / candidate).resolve(strict=False))
            resolved[key] = absolute
            files.append(
                {
                    "scope": scope,
                    "key": str(key),
                    "kind": "glob",
                    "raw": value,
                    "resolved": absolute,
                }
            )
            continue
        target = safe_workspace(workspace_path, candidate)
        absolute = str(target)
        resolved[key] = absolute
        files.append(
            {
                "scope": scope,
                "key": str(key),
                "kind": "path",
                "raw": value,
                "resolved": absolute,
            }
        )
    return resolved, files


# ── validation helpers ──────────────────────────────────────────────────────


def is_valid_uuid(value: str) -> bool:
    if not value:
        return False
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


def is_valid_resume_run_name(value: str) -> bool:
    if not value:
        return False
    if "/" in value or "\\" in value:
        return False
    return bool(_RESUME_RUN_NAME_RE.match(value))


def normalize_status_value(value: str | RunStatus) -> str:
    if isinstance(value, RunStatus):
        return value.value
    raw = str(value)
    if raw.startswith("RunStatus."):
        raw = raw.split(".", 1)[1]
    raw = raw.lower()
    return raw if raw in RunStatus._value2member_map_ else raw


def resolve_resume_token(run: Run) -> str | None:
    cfg = config_helper(run.config)
    session_id = str(cfg.session_id or "").strip()
    if is_valid_uuid(session_id):
        return session_id
    resume_token = str(cfg.resume_token or "").strip()
    if is_valid_resume_run_name(resume_token):
        return resume_token
    run_name = str(run.nextflow_run_name or "").strip()
    if is_valid_resume_run_name(run_name):
        return run_name
    return None


# ── mock / DAG variant helpers ──────────────────────────────────────────────


def mock_variant_run_status(variant: str) -> str:
    mapping = {
        "pending": RunStatus.PENDING.value,
        "queued": RunStatus.QUEUED.value,
        "running": RunStatus.RUNNING.value,
        "failed": RunStatus.FAILED.value,
        "success": RunStatus.COMPLETED.value,
    }
    return mapping[variant]


def mock_timestamps(
    variant: str, now: datetime
) -> tuple[datetime | None, datetime | None]:
    if variant in {"pending", "queued"}:
        return None, None
    started_at = now
    if variant == "running":
        return started_at, None
    return started_at, now


def mock_current_task(dag: dict) -> str | None:
    for status in ("running", "queued", "failed"):
        for node in dag.get("nodes", []):
            if node.get("data", {}).get("status") == status:
                return node.get("data", {}).get("label")
    return None


def mock_log_content(variant: str, dag: dict) -> str:
    lines = [f"Mock DAG variant: {variant}"]
    for node in dag.get("nodes", []):
        label = node.get("data", {}).get("label", node.get("id"))
        status = node.get("data", {}).get("status", "pending")
        lines.append(f"{label}: {status}")
    return "\n".join(lines) + "\n"


def _clone_json(value):
    """Deep-clone a JSON-serializable value."""
    return json.loads(json.dumps(value))


def _sync_edge_animation(dag: dict) -> None:
    """Set edge ``animated`` based on source-node status."""
    node_status = {
        node.get("id"): node.get("data", {}).get("status", "pending")
        for node in dag.get("nodes", [])
    }
    for edge in dag.get("edges", []):
        edge["animated"] = node_status.get(edge.get("source")) in {
            "running",
            "queued",
        }


def build_mock_variant_dag(source_dag: dict, variant: str) -> dict:
    dag = _clone_json(source_dag)
    nodes = dag.get("nodes", [])
    for node in nodes:
        node.setdefault("data", {})["status"] = "pending"

    if not nodes:
        return dag

    if variant == "success":
        for node in nodes:
            node["data"]["status"] = "success"
    elif variant == "pending":
        pass
    elif variant == "queued":
        nodes[0]["data"]["status"] = "queued"
    elif variant == "running":
        nodes[0]["data"]["status"] = "running"
        if len(nodes) > 1:
            nodes[1]["data"]["status"] = "success"
    elif variant == "failed":
        nodes[0]["data"]["status"] = "failed"
        if len(nodes) > 1:
            nodes[1]["data"]["status"] = "success"

    _sync_edge_animation(dag)
    if variant in {"failed", "success"}:
        for edge in dag.get("edges", []):
            edge["animated"] = False
    return dag


# ── timestamp helper ────────────────────────────────────────────────────────


def now() -> datetime:
    return datetime.now(timezone.utc)


# ── samplesheet CSV writer ───────────────────────────────────────────────────


def write_samplesheet_csv(
    workspace_path: Path,
    samples: list[dict],
    dest: Path,
    *,
    headers: Sequence[str],
    extract_row: Callable[[dict], tuple[list[str], list[str]]],
    error_label: str,
) -> None:
    """Write a samplesheet CSV for any input mode.

    *extract_row* receives a sample dict and returns
    ``(csv_values, relative_file_paths)`` — values to write and paths
    to validate inside *workspace_path*.  Raise ``ValueError`` with
    *error_label* when required fields are missing.
    """
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(headers)
    for row in samples:
        values, rel_paths = extract_row(row)
        for rp in rel_paths:
            resolved = safe_workspace(workspace_path, rp)
            if not resolved.exists():
                raise FileNotFoundError(f"sample {error_label} not found")
        writer.writerow(values)
    dest.write_text(buf.getvalue(), encoding="utf-8")
