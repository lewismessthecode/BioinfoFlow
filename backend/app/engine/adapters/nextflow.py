from __future__ import annotations

import asyncio
import json
import re
import shutil
import uuid
from http.client import IncompleteRead, RemoteDisconnected
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from app.config import settings
from app.engine.adapter import EngineAdapter
from app.engine.backend import EngineEvent, EngineEventType
from app.path_layout import nextflow_work_dir
from app.services.docker_service import DockerService
from app.utils.logging import get_logger
from app.utils.process import terminate_process_tree

logger = get_logger(__name__)

GPU_PIPELINE_PATTERNS = [
    "parabricks",
    "wgs-nf",
    "wgs_germline",
    "clara-parabricks",
]
_ENGINE_LOGS_KEY = "__engine_logs__"
_RESUME_RUN_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{1,99}$")
_VALID_PARAM_KEY_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


class NextflowAdapter(EngineAdapter):
    def __init__(self, *, nextflow_bin: str | None = None) -> None:
        self._binary = _resolve_nextflow_bin(nextflow_bin or settings.nextflow_bin)

    @property
    def engine_name(self) -> str:
        return "nextflow"

    @property
    def display_name(self) -> str:
        return "Nextflow"

    @property
    def binary(self) -> str:
        return self._binary

    @property
    def supports_native_resume(self) -> bool:
        return True

    async def build_command(self, config: dict, workspace: str) -> list[str]:
        run_id = str(config.get("run_id") or f"run_{uuid.uuid4().hex[:6]}")
        pipeline = str(config.get("pipeline") or config.get("workflow_path") or "")
        work_dir_value = config.get("work_dir")
        work_dir = Path(work_dir_value) if work_dir_value else nextflow_work_dir(run_id)
        trace_path = str(config.get("trace_path") or "trace.txt")
        dag_path = str(config.get("dag_path") or "dag.dot")
        log_path = _nextflow_log_path(config, workspace, dag_path=dag_path)
        cmd = [
            self.binary,
            "-log",
            str(log_path),
            "run",
            pipeline,
        ]
        revision = _optional_revision(config.get("revision"))
        if revision:
            cmd.extend(["-r", revision])

        cmd.extend(
            [
                "-work-dir",
                str(work_dir),
                "-with-trace",
                trace_path,
                "-with-dag",
                dag_path,
                "-ansi-log",
                "false",
            ]
        )

        profile = _optional_string(config.get("profile"))
        if not profile and is_gpu_pipeline(pipeline):
            profile = "consumer_gpu"
            logger.info(
                "nextflow.auto_gpu_profile",
                pipeline=pipeline,
                profile=profile,
            )
        if profile:
            cmd.extend(["-profile", profile])

        if bool(config.get("resume")):
            cmd.append("-resume")
            resume_from = _optional_string(config.get("resume_from"))
            if resume_from:
                cmd.append(resume_from)

        overrides = _config_overrides(config)
        if overrides:
            override_path = Path(
                str(
                    config.get("config_overrides_path")
                    or (work_dir.parent / "overrides.config")
                )
            )
            override_path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(_write_overrides, override_path, overrides)
            cmd.extend(["-c", str(override_path)])

        for key, value in _params(config).items():
            if not _VALID_PARAM_KEY_RE.match(key):
                raise ValueError(
                    f"Invalid Nextflow param key: {key!r}. "
                    "Param keys must start with a letter or underscore and "
                    "contain only alphanumeric characters and underscores."
                )
            cmd.extend([f"--{key}", str(value)])

        return cmd

    def parse_event(self, line: str, stream: str) -> EngineEvent | None:
        if not line:
            return None
        if stream == "stderr":
            return EngineEvent(
                EngineEventType.LOG,
                {"message": line, "level": "error"},
            )

        if "Launching" in line:
            bracketed = re.search(r"Launching\s+`[^`]+`\s+\[([^\]]+)\]", line)
            if bracketed:
                return EngineEvent(
                    EngineEventType.STARTED,
                    {"run_name": bracketed.group(1), "message": line},
                )
            quoted = re.search(r"Launching\s+`([^`]+)`", line)
            if quoted:
                token = quoted.group(1)
                if "/" not in token and "\\" not in token and " " not in token:
                    return EngineEvent(
                        EngineEventType.STARTED,
                        {"run_name": token, "message": line},
                    )

        if "ERROR" in line or "ERROR ~" in line:
            return EngineEvent(EngineEventType.ERROR, {"message": line})

        if "Execution complete" in line or "Completed at" in line:
            return EngineEvent(
                EngineEventType.COMPLETED,
                {"success": True, "message": line},
            )

        if "process >" in line:
            match = re.search(r"process >\s+([^\s]+)", line)
            if match:
                return EngineEvent(
                    EngineEventType.TASK_UPDATE,
                    {
                        "name": match.group(1),
                        "status": "completed" if "[100%]" in line else "running",
                        "raw": line,
                        "message": line,
                    },
                )

        return EngineEvent(EngineEventType.LOG, {"message": line})

    async def cancel(self, *, pid: int | None = None, **kwargs) -> bool:
        run_name = _optional_string(kwargs.get("run_name"))
        if pid:
            return await asyncio.to_thread(terminate_process_tree, pid)
        if not run_name:
            return False
        process = await asyncio.create_subprocess_exec(
            self.binary,
            "cancel",
            run_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await process.communicate()
        return process.returncode == 0

    def get_resume_token(self, run_config: dict) -> str | None:
        runtime = _runtime(run_config)
        candidates = [
            runtime.get("session_id"),
            runtime.get("resume_token"),
            runtime.get("resume_from"),
            run_config.get("resume_from"),
        ]
        for candidate in candidates:
            token = _optional_string(candidate)
            if not token:
                continue
            if _is_valid_uuid(token) or _is_valid_resume_run_name(token):
                return token
        return None

    async def pre_submit(self, config: dict, workspace: str) -> dict:
        updated = dict(config)
        overrides = _config_overrides(updated)
        runtime = _runtime(updated)
        profile = _optional_string(updated.get("profile"))
        retry_policy = _retry_policy(updated)

        max_retries = max(0, int(retry_policy.get("max_retries", 0) or 0))
        if max_retries > 0:
            overrides.setdefault("process.errorStrategy", "'retry'")
            overrides.setdefault("process.maxRetries", max_retries)

        docker_available = await DockerService().is_available()
        if docker_available:
            overrides.setdefault("docker.enabled", True)
            overrides.setdefault("docker.pull", True)
        else:
            overrides["docker.enabled"] = False
            runtime["docker_available"] = False
            profile = None
            logs = list(updated.get(_ENGINE_LOGS_KEY, []) or [])
            logs.append(
                {
                    "message": "Docker not running; running without Docker profile",
                    "level": "warning",
                    "config_patch": {"runtime": dict(runtime)},
                }
            )
            updated[_ENGINE_LOGS_KEY] = logs

        updated["runtime"] = runtime
        updated["profile"] = profile
        return _sync_request_aliases(updated, config_overrides=overrides)

    async def extract_schema(self, source: str | None, **kwargs) -> dict | None:
        source_value = _optional_string(source)
        if not source_value:
            return None

        if _is_nfcore_source(source_value):
            schema = await _fetch_nfcore_schema(
                source_value,
                revision=kwargs.get("revision") or kwargs.get("version"),
            )
            if schema is not None:
                return schema

        return await _run_inspect(self.binary, source_value)


def is_gpu_pipeline(pipeline: str) -> bool:
    lowered = pipeline.lower()
    return any(pattern in lowered for pattern in GPU_PIPELINE_PATTERNS)


def _params(config: dict) -> dict:
    request = config.get("request")
    if isinstance(request, dict) and isinstance(request.get("params"), dict):
        return dict(request["params"])
    params = config.get("params")
    return dict(params) if isinstance(params, dict) else {}


def _runtime(config: dict) -> dict:
    runtime = config.get("runtime")
    return dict(runtime) if isinstance(runtime, dict) else {}


def _config_overrides(config: dict) -> dict:
    request = config.get("request")
    if isinstance(request, dict) and isinstance(request.get("config_overrides"), dict):
        return dict(request["config_overrides"])
    overrides = config.get("config_overrides")
    return dict(overrides) if isinstance(overrides, dict) else {}


def _retry_policy(config: dict) -> dict:
    policy = config.get("policy")
    if isinstance(policy, dict) and isinstance(policy.get("retry"), dict):
        return dict(policy["retry"])
    return {}


def _sync_request_aliases(config: dict, *, config_overrides: dict) -> dict:
    request = config.get("request")
    request_dict = dict(request) if isinstance(request, dict) else {}
    request_dict["config_overrides"] = dict(config_overrides)
    config["request"] = request_dict
    config["config_overrides"] = dict(config_overrides)
    return config


def _optional_string(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_revision(value) -> str | None:
    text = _optional_string(value)
    if not text or text.lower() == "latest":
        return None
    return text


def _nextflow_log_path(config: dict, workspace: str, *, dag_path: str) -> Path:
    runtime = _runtime(config)
    explicit = _optional_string(config.get("log_path") or runtime.get("log_path"))
    if explicit:
        path = Path(explicit)
    else:
        path = Path(dag_path).parent / "nextflow.log"

    if not path.is_absolute():
        path = Path(workspace) / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _is_valid_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


def _is_valid_resume_run_name(value: str) -> bool:
    if "/" in value or "\\" in value:
        return False
    return bool(_RESUME_RUN_NAME_RE.match(value))


def _format_override_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return repr(value)


def _write_overrides(path: Path, overrides: dict) -> None:
    lines = [f"{key} = {_format_override_value(value)}" for key, value in overrides.items()]
    path.write_text("\n".join(lines), encoding="utf-8")


def _resolve_nextflow_bin(candidate: str) -> str:
    resolved = shutil.which(candidate) if candidate else None
    if resolved:
        return resolved
    fallback = shutil.which("nextflow")
    return fallback or candidate or "nextflow"


def _is_nfcore_source(source: str) -> bool:
    lowered = source.lower()
    return lowered.startswith("nf-core/") or "github.com/nf-core/" in lowered


def _nfcore_pipeline_name(source: str) -> str | None:
    text = source.strip().rstrip("/")
    for prefix in ("nf-core/", "github.com/nf-core/"):
        idx = text.find(prefix)
        if idx >= 0:
            tail = text[idx + len(prefix) :]
            name = tail.split("/", 1)[0]
            return name or None
    return None


async def _fetch_nfcore_schema(source: str, *, revision: object = None) -> dict | None:
    pipeline = _nfcore_pipeline_name(source)
    if not pipeline:
        return None

    candidates: list[str] = []
    requested = _optional_revision(revision)
    if requested:
        candidates.append(requested)
    candidates.extend(["master", "main"])

    seen: set[str] = set()
    for branch in candidates:
        if branch in seen:
            continue
        seen.add(branch)
        url = (
            f"https://raw.githubusercontent.com/nf-core/{pipeline}/"
            f"{branch}/nextflow_schema.json"
        )
        try:
            payload = await asyncio.to_thread(_load_json_url, url)
        except (
            HTTPError,
            URLError,
            TimeoutError,
            IncompleteRead,
            RemoteDisconnected,
            ValueError,
        ):
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _load_json_url(url: str) -> dict:
    with urlopen(url, timeout=1.5) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


async def _run_inspect(binary: str, source: str) -> dict | None:
    if not _is_binary_available(binary):
        return None

    try:
        process = await asyncio.create_subprocess_exec(
            binary,
            "inspect",
            source,
            "-format",
            "json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError:
        return None

    try:
        stdout, _stderr = await asyncio.wait_for(process.communicate(), timeout=5)
    except TimeoutError:
        process.kill()
        await process.communicate()
        return None

    if process.returncode != 0 or not stdout:
        return None

    try:
        payload = json.loads(stdout.decode("utf-8"))
    except ValueError:
        return None

    return payload if isinstance(payload, dict) else None


def _is_binary_available(binary: str) -> bool:
    path = Path(binary)
    return path.exists() or shutil.which(binary) is not None
