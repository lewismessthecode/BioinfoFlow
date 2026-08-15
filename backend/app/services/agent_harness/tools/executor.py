from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
import hashlib
import hmac
import json
from typing import Any, Literal

from app.services.agent_harness.tools.ask_user import AskUserTool
from app.services.agent_harness.tools.bash import BashTool
from app.services.agent_harness.tools.edit import EditTool
from app.services.agent_harness.tools.read import ReadTool
from app.services.agent_harness.tools.specs import (
    HarnessTool,
    PermissionMode,
    ToolBatchResult,
    ToolCall,
    ToolExecutionContext,
    ToolResult,
    WorkspaceAccess,
)
from app.services.agent_harness.tools.update_plan import UpdatePlanTool
from app.services.agent_harness.tools.write import WriteTool
from app.services.agent_harness.token_policy import is_scoped_bif_command


RecoveryAction = Literal["retry", "verify", "require_user", "none"]


class ToolExecutor:
    def __init__(
        self,
        backend: Any,
        *,
        permission_mode: PermissionMode = "ask_dangerous",
        workspace_access: WorkspaceAccess = "read_write",
        environment: dict[str, str] | None = None,
        bash_environment: dict[str, str] | None = None,
        bash_environment_provider: Callable[[], Awaitable[dict[str, str]]]
        | None = None,
        extra_tools: Iterable[HarnessTool] = (),
    ) -> None:
        if permission_mode not in {"ask_changes", "ask_dangerous", "full_access"}:
            raise ValueError(f"unknown permission mode: {permission_mode}")
        if workspace_access not in {"read_only", "read_write"}:
            raise ValueError(f"unknown workspace access: {workspace_access}")
        defaults: tuple[HarnessTool, ...] = (
            ReadTool(),
            BashTool(),
            EditTool(),
            WriteTool(),
            AskUserTool(),
            UpdatePlanTool(),
        )
        self._tools = {tool.spec.name: tool for tool in (*defaults, *extra_tools)}
        self._default_names = tuple(tool.spec.name for tool in defaults)
        self.backend = backend
        self.permission_mode = permission_mode
        self.workspace_access = workspace_access
        self.environment = dict(environment or {})
        self.bash_environment = dict(bash_environment or {})
        self.bash_environment_provider = bash_environment_provider
        self._path_locks: dict[str, asyncio.Lock] = {}
        self._recovery_approval_fingerprints: dict[str, str] = {}

    @property
    def tools(self):
        return tuple(self._tools[name].spec for name in self._default_names)

    @property
    def model_tools(self):
        return tuple(spec.model_definition() for spec in self.tools)

    async def execute(
        self,
        call: ToolCall,
        *,
        cancellation: Any | None = None,
        interaction_response: dict[str, Any] | None = None,
    ) -> ToolResult:
        tool = self._tools.get(call.name)
        if tool is None:
            return ToolResult(
                call_id=call.call_id,
                tool_name=call.name,
                status="failed",
                replay_policy="never",
                error=f"unknown tool: {call.name}",
            )
        if _is_cancelled(cancellation):
            return _cancelled(call, tool)
        try:
            arguments = _validate_arguments(call.arguments, tool.spec.input_schema)
        except (TypeError, ValueError) as exc:
            return _failed(call, tool, exc)
        call = ToolCall(call.call_id, call.name, arguments)
        context = ToolExecutionContext(
            backend=self.backend,
            cancellation=cancellation,
            environment=dict(self.environment),
        )
        if call.name == "ask_user":
            if interaction_response is not None:
                if not _response_matches(call, interaction_response):
                    return ToolResult(
                        call_id=call.call_id,
                        tool_name=call.name,
                        status="blocked",
                        replay_policy=tool.spec.replay_policy,
                        error="interaction response does not match this tool call",
                    )
                answers = interaction_response.get("answers")
                if not isinstance(answers, dict):
                    return ToolResult(
                        call_id=call.call_id,
                        tool_name=call.name,
                        status="failed",
                        replay_policy=tool.spec.replay_policy,
                        error="ask_user response must include an answers object",
                    )
                return ToolResult(
                    call_id=call.call_id,
                    tool_name=call.name,
                    status="completed",
                    replay_policy=tool.spec.replay_policy,
                    output={"answers": answers},
                )
            try:
                questions = _normalize_questions(call.arguments)
            except (TypeError, ValueError) as exc:
                return _failed(call, tool, exc)
            return ToolResult.interaction_required(
                call_id=call.call_id,
                tool_name=call.name,
                replay_policy=tool.spec.replay_policy,
                request_id=f"tool:{call.call_id}",
                kind="question",
                questions=questions,
            )

        risk = None
        if call.name == "bash":
            try:
                risk = tool.assess_risk(call.arguments, context)
            except (TypeError, ValueError) as exc:
                return _failed(call, tool, exc)
            if risk.hard_blocked:
                return ToolResult(
                    call_id=call.call_id,
                    tool_name=call.name,
                    status="blocked",
                    replay_policy=tool.spec.replay_policy,
                    error="command violates a hard workspace boundary",
                    output={"risk": risk.audit_snapshot()},
                )

        is_read_only = _is_read_only(tool, risk)
        if self.workspace_access == "read_only" and not is_read_only:
            return ToolResult(
                call_id=call.call_id,
                tool_name=call.name,
                status="blocked",
                replay_policy=tool.spec.replay_policy,
                error="tool is not permitted in a read_only workspace",
            )
        requires_confirmation = (
            self.permission_mode == "ask_changes" and not is_read_only
        ) or (
            self.permission_mode == "ask_dangerous"
            and risk is not None
            and (
                risk.requires_explicit_approval
                or risk.level in {"destructive", "critical"}
            )
        )
        approved_cwd_binding = None
        if requires_confirmation:
            if interaction_response is not None:
                if not _response_matches(call, interaction_response):
                    return ToolResult(
                        call_id=call.call_id,
                        tool_name=call.name,
                        status="blocked",
                        replay_policy=tool.spec.replay_policy,
                        error="interaction response does not match this tool call",
                    )
                if interaction_response.get("approved") is not True:
                    return ToolResult(
                        call_id=call.call_id,
                        tool_name=call.name,
                        status="blocked",
                        replay_policy=tool.spec.replay_policy,
                        error="user denied the command",
                    )
            if risk is None:
                approval_snapshot = _workspace_change_approval(call, tool)
            else:
                try:
                    (
                        approval_snapshot,
                        approved_cwd_binding,
                    ) = await self._approval_snapshot(call, risk)
                except Exception as exc:
                    return _failed(call, tool, exc)
            if interaction_response is not None and risk is not None:
                expected_fingerprint = interaction_response.get(
                    "assessment_fingerprint"
                )
                current_fingerprint = approval_snapshot["assessment_fingerprint"]
                base_fingerprint = approval_snapshot.get("base_assessment_fingerprint")
                recovery_fingerprint = self._recovery_approval_fingerprints.pop(
                    call.call_id,
                    None,
                )
                if (
                    not isinstance(expected_fingerprint, str)
                    or len(expected_fingerprint) != 64
                    or not (
                        hmac.compare_digest(
                            expected_fingerprint,
                            current_fingerprint,
                        )
                        or (
                            isinstance(recovery_fingerprint, str)
                            and isinstance(base_fingerprint, str)
                            and hmac.compare_digest(
                                expected_fingerprint,
                                recovery_fingerprint,
                            )
                            and hmac.compare_digest(
                                recovery_fingerprint,
                                base_fingerprint,
                            )
                        )
                    )
                ):
                    return ToolResult(
                        call_id=call.call_id,
                        tool_name=call.name,
                        status="blocked",
                        replay_policy=tool.spec.replay_policy,
                        error=("Bash approval assessment changed before execution"),
                    )
            if interaction_response is None:
                return ToolResult.interaction_required(
                    call_id=call.call_id,
                    tool_name=call.name,
                    replay_policy=tool.spec.replay_policy,
                    request_id=f"tool:{call.call_id}",
                    kind="confirmation",
                    questions=(
                        {
                            "question": "Allow this command to run?",
                            "header": "Confirm",
                            "options": [
                                {
                                    "label": "Allow",
                                    "description": "Run the command once",
                                },
                                {"label": "Deny", "description": "Do not run it"},
                            ],
                        },
                    ),
                    risk=approval_snapshot,
                )
        scoped_bif = False
        if call.name == "bash":
            command = call.arguments.get("command")
            checker = getattr(self.backend, "allows_scoped_bif_token", None)
            scoped_bif = (
                bool(checker(command))
                if callable(checker)
                else is_scoped_bif_command(command)
            )
        if scoped_bif:
            bash_environment = self.bash_environment
            if self.bash_environment_provider is not None:
                try:
                    bash_environment = await self.bash_environment_provider()
                except Exception as exc:
                    return _failed(call, tool, exc)
            context = ToolExecutionContext(
                backend=self.backend,
                cancellation=cancellation,
                environment={**self.environment, **bash_environment},
            )
        if approved_cwd_binding is not None and interaction_response is not None:
            context = ToolExecutionContext(
                backend=_CwdBoundBackend(self.backend, approved_cwd_binding),
                cancellation=context.cancellation,
                environment=context.environment,
            )
        lock = self._lock_for(call, tool)
        try:
            if lock is None:
                output = await _run_interruptibly(
                    tool.run(call.arguments, context), cancellation
                )
            else:
                async with lock:
                    if _is_cancelled(cancellation):
                        return _cancelled(call, tool)
                    output = await _run_interruptibly(
                        tool.run(call.arguments, context), cancellation
                    )
        except asyncio.CancelledError:
            return _cancelled(call, tool)
        except ToolCancelledError:
            return _cancelled(call, tool)
        except Exception as exc:
            return _failed(call, tool, exc)
        return ToolResult(
            call_id=call.call_id,
            tool_name=call.name,
            status="completed",
            replay_policy=tool.spec.replay_policy,
            output=output,
        )

    async def execute_batch(
        self,
        calls: Iterable[ToolCall],
        *,
        cancellation: Any | None = None,
        on_start: Callable[[ToolCall], Awaitable[None]] | None = None,
        on_result: Callable[[ToolResult], Awaitable[None]] | None = None,
    ) -> ToolBatchResult:
        ordered = tuple(calls)
        if not ordered:
            return ToolBatchResult(())
        pause_index = next(
            (index for index, call in enumerate(ordered) if call.name == "ask_user"),
            None,
        )
        active = ordered if pause_index is None else ordered[: pause_index + 1]
        pending = () if pause_index is None else ordered[pause_index + 1 :]
        callback_lock = asyncio.Lock()

        async def notify_start(call: ToolCall) -> None:
            if on_start is not None:
                async with callback_lock:
                    await on_start(call)

        async def notify_result(result: ToolResult) -> None:
            if on_result is not None:
                async with callback_lock:
                    await on_result(result)

        async def execute_one(call: ToolCall) -> ToolResult:
            await notify_start(call)
            result = await self.execute(call, cancellation=cancellation)
            if on_result is not None and result.status != "interaction_required":
                await notify_result(result)
            return result

        if self._batch_requires_serial(active):
            results: list[ToolResult] = []
            for index, call in enumerate(active):
                result = await execute_one(call)
                results.append(result)
                if result.status == "interaction_required":
                    pending = (*active[index + 1 :], *pending)
                    break
                if result.status == "cancelled":
                    unfinished = (*active[index + 1 :], *pending)
                    for unfinished_call in unfinished:
                        cancelled = self._cancelled_result(unfinished_call)
                        await notify_result(cancelled)
                        results.append(cancelled)
                    pending = ()
                    break
            return ToolBatchResult(tuple(results), tuple(pending))

        results = await asyncio.gather(
            *(execute_one(call) for call in active)
        )
        return ToolBatchResult(tuple(results), tuple(pending))

    def batch_execution_mode(
        self, calls: Iterable[ToolCall]
    ) -> Literal["parallel", "serial", "mixed"]:
        ordered = tuple(calls)
        if len(ordered) < 2 or self._batch_requires_serial(ordered):
            return "serial"
        return "parallel"

    def _cancelled_result(self, call: ToolCall) -> ToolResult:
        tool = self._tools.get(call.name)
        if tool is None:
            return ToolResult(
                call_id=call.call_id,
                tool_name=call.name,
                status="cancelled",
                replay_policy="never",
                error="tool execution was cancelled",
            )
        return _cancelled(call, tool)

    def recovery_action(
        self,
        call: ToolCall,
        *,
        execution_started: bool,
        result_committed: bool,
    ) -> RecoveryAction:
        if not execution_started or result_committed:
            return "none"
        tool = self._tools.get(call.name)
        if tool is None or tool.spec.replay_policy == "never":
            return "require_user"
        if tool.spec.replay_policy == "verify":
            return "verify"
        return "retry"

    def approval_assessment_matches(
        self,
        call: ToolCall,
        interaction: dict[str, Any] | None,
    ) -> bool:
        """Recheck a Bash approval against the exact persisted assessment."""

        if call.name != "bash" or not isinstance(interaction, dict):
            return False
        approved_risk = interaction.get("risk")
        if not isinstance(approved_risk, dict):
            return False
        expected = approved_risk.get(
            "base_assessment_fingerprint",
            approved_risk.get("assessment_fingerprint"),
        )
        if not isinstance(expected, str) or len(expected) != 64:
            return False
        tool = self._tools.get(call.name)
        if tool is None:
            return False
        try:
            current = self._base_assessment_fingerprint(call)
        except (TypeError, ValueError):
            return False
        return hmac.compare_digest(expected, current)

    def approval_assessment_fingerprint(self, call: ToolCall) -> str:
        fingerprint = self._base_assessment_fingerprint(call)
        self._recovery_approval_fingerprints[call.call_id] = fingerprint
        return fingerprint

    def _base_assessment_fingerprint(self, call: ToolCall) -> str:
        if call.name != "bash":
            raise ValueError("only Bash calls have approval assessments")
        tool = self._tools.get(call.name)
        if tool is None:
            raise ValueError("unknown Bash tool")
        arguments = _validate_arguments(call.arguments, tool.spec.input_schema)
        current = tool.assess_risk(
            arguments,
            ToolExecutionContext(
                backend=self.backend,
                environment=dict(self.environment),
            ),
        )
        return current.assessment_fingerprint()

    async def _approval_snapshot(
        self,
        call: ToolCall,
        risk: Any,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        snapshot = risk.audit_snapshot()
        binder = getattr(self.backend, "command_cwd_binding", None)
        if not callable(binder):
            return snapshot, None
        binding = await binder(call.arguments.get("cwd"))
        if not isinstance(binding, dict):
            raise RuntimeError("Bash working directory identity is unavailable")
        base_fingerprint = risk.assessment_fingerprint()
        snapshot["base_assessment_fingerprint"] = base_fingerprint
        snapshot["cwd_identity"] = dict(binding)
        snapshot["assessment_fingerprint"] = _approval_fingerprint(
            base_fingerprint,
            binding,
        )
        return snapshot, binding

    def _batch_requires_serial(self, calls: tuple[ToolCall, ...]) -> bool:
        for call in calls:
            tool = self._tools.get(call.name)
            if tool is None or tool.spec.serial:
                return True
            if call.name == "bash":
                context = ToolExecutionContext(
                    self.backend,
                    environment={**self.environment, **self.bash_environment},
                )
                try:
                    risk = tool.assess_risk(call.arguments, context)
                except (TypeError, ValueError):
                    return True
                if not _is_read_only(tool, risk):
                    return True
        seen_paths: set[str] = set()
        for call in calls:
            tool = self._tools.get(call.name)
            if tool is None or not tool.spec.mutates_workspace:
                continue
            argument = tool.spec.path_argument
            raw_path = call.arguments.get(argument) if argument is not None else None
            if not isinstance(raw_path, str) or not raw_path.strip():
                return True
            path = str(self.backend.canonical_path(raw_path))
            if path in seen_paths:
                return True
            seen_paths.add(path)
        return False

    def _lock_for(self, call: ToolCall, tool: HarnessTool) -> asyncio.Lock | None:
        argument = tool.spec.path_argument
        if not tool.spec.mutates_workspace or argument is None:
            return None
        raw_path = call.arguments.get(argument)
        if not isinstance(raw_path, str) or not raw_path.strip():
            return None
        key = str(self.backend.canonical_path(raw_path))
        return self._path_locks.setdefault(key, asyncio.Lock())


class _CwdBoundBackend:
    def __init__(self, backend: Any, binding: dict[str, Any]) -> None:
        self._backend = backend
        self._binding = dict(binding)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._backend, name)

    async def run_command(self, **kwargs: Any) -> dict[str, Any]:
        return await self._backend.run_command(
            **kwargs,
            expected_cwd_binding=self._binding,
        )


def _approval_fingerprint(
    base_fingerprint: str,
    cwd_binding: dict[str, Any],
) -> str:
    payload = json.dumps(
        {
            "assessment_fingerprint": base_fingerprint,
            "cwd_identity": cwd_binding,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class ToolCancelledError(Exception):
    pass


def _workspace_change_approval(
    call: ToolCall,
    tool: HarnessTool,
) -> dict[str, Any]:
    path_argument = tool.spec.path_argument
    resource = call.arguments.get(path_argument) if path_argument else None
    resources = [resource] if isinstance(resource, str) and resource else []
    return {
        "level": "changes",
        "effects": ["write"],
        "reasons": ["session requires approval for workspace changes"],
        "affected_resources": resources,
    }


def _is_read_only(tool: HarnessTool, risk: Any | None) -> bool:
    if tool.spec.name == "bash":
        return (
            risk is not None
            and set(risk.effects) <= {"read"}
            and not risk.requires_explicit_approval
        )
    return not tool.spec.mutates_workspace


def _is_cancelled(cancellation: Any | None) -> bool:
    if cancellation is None:
        return False
    is_set = getattr(cancellation, "is_set", None)
    return bool(callable(is_set) and is_set())


def _cancelled(call: ToolCall, tool: HarnessTool) -> ToolResult:
    return ToolResult(
        call_id=call.call_id,
        tool_name=call.name,
        status="cancelled",
        replay_policy=tool.spec.replay_policy,
        error="tool execution was cancelled",
    )


def _failed(call: ToolCall, tool: HarnessTool, exc: Exception) -> ToolResult:
    return ToolResult(
        call_id=call.call_id,
        tool_name=call.name,
        status="failed",
        replay_policy=tool.spec.replay_policy,
        error=str(exc),
    )


def _normalize_questions(arguments: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    questions = arguments.get("questions")
    if not isinstance(questions, list) or not 1 <= len(questions) <= 3:
        raise ValueError("ask_user requires one to three questions")
    normalized: list[dict[str, Any]] = []
    for question in questions:
        if not isinstance(question, dict):
            raise TypeError("each question must be an object")
        prompt = question.get("question")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("question text is required")
        header = question.get("header")
        if not isinstance(header, str) or not header.strip():
            raise ValueError("question header is required")
        options = question.get("options")
        if not isinstance(options, list) or not 2 <= len(options) <= 3:
            raise ValueError("each question requires two or three options")
        normalized.append(
            {
                **question,
                "question": prompt.strip(),
                "header": header.strip()[:12],
            }
        )
    return tuple(normalized)


def _response_matches(call: ToolCall, response: dict[str, Any]) -> bool:
    return response.get("request_id") == f"tool:{call.call_id}"


async def _run_interruptibly(awaitable, cancellation: Any | None):
    wait = getattr(cancellation, "wait", None)
    if not callable(wait):
        return await awaitable
    execution = asyncio.create_task(awaitable)
    interruption = asyncio.create_task(wait())
    done, _ = await asyncio.wait(
        {execution, interruption}, return_when=asyncio.FIRST_COMPLETED
    )
    if execution in done:
        interruption.cancel()
        return execution.result()
    execution.cancel()
    await asyncio.gather(execution, return_exceptions=True)
    raise ToolCancelledError


def _validate_arguments(
    arguments: dict[str, Any], schema: dict[str, Any]
) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        raise TypeError("tool arguments must be an object")
    properties = schema.get("properties")
    properties = properties if isinstance(properties, dict) else {}
    required = schema.get("required")
    required = required if isinstance(required, list) else []
    missing = [name for name in required if name not in arguments]
    if missing:
        raise ValueError(f"missing required tool arguments: {', '.join(missing)}")
    if schema.get("additionalProperties") is False:
        unknown = [name for name in arguments if name not in properties]
        if unknown:
            raise ValueError(f"unknown tool arguments: {', '.join(unknown)}")
    for name, value in arguments.items():
        field = properties.get(name)
        if isinstance(field, dict):
            _validate_value(value, field, path=name)
    return dict(arguments)


def _validate_value(value: Any, schema: dict[str, Any], *, path: str) -> None:
    expected = schema.get("type")
    expected_types: dict[str, type | tuple[type, ...]] = {
        "string": str,
        "integer": int,
        "boolean": bool,
        "object": dict,
        "array": list,
    }
    python_type = expected_types.get(str(expected))
    if python_type is not None and (
        not isinstance(value, python_type)
        or (expected == "integer" and isinstance(value, bool))
    ):
        raise ValueError(f"{path} must be {expected}")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < int(schema["minLength"]):
            raise ValueError(f"{path} must have length >= {schema['minLength']}")
        if "maxLength" in schema and len(value) > int(schema["maxLength"]):
            raise ValueError(f"{path} must have length <= {schema['maxLength']}")
    if isinstance(value, int) and not isinstance(value, bool):
        if "minimum" in schema and value < int(schema["minimum"]):
            raise ValueError(f"{path} must be >= {schema['minimum']}")
        if "maximum" in schema and value > int(schema["maximum"]):
            raise ValueError(f"{path} must be <= {schema['maximum']}")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < int(schema["minItems"]):
            raise ValueError(f"{path} must contain at least {schema['minItems']} items")
        if "maxItems" in schema and len(value) > int(schema["maxItems"]):
            raise ValueError(f"{path} must contain at most {schema['maxItems']} items")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _validate_value(item, item_schema, path=f"{path}[{index}]")
    if isinstance(value, dict):
        _validate_arguments(value, schema)
