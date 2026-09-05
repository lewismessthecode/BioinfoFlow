from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

import aiofiles
from sqlalchemy.exc import IntegrityError

from app.models.agent_harness import AgentHarnessSession, AgentHarnessToolOutput
from app.path_layout import (
    agent_artifacts_root,
    agent_session_tool_outputs_root,
    agent_tool_output_root,
    agent_tool_outputs_root,
    safe_join,
)
from app.repositories.agent_harness_repo import (
    AgentHarnessToolOutputRepository,
    RunFence,
)
from app.utils.exceptions import ConflictError, NotFoundError


class AgentHarnessToolOutputService:
    """Persist truncated tool output without creating a user-facing Artifact."""

    def __init__(self, db) -> None:
        self.db = db
        self.repo = AgentHarnessToolOutputRepository(db)

    async def list_for_session(
        self,
        *,
        session_id: str,
        workspace_id: str,
        user_id: str,
        run_id: str | None = None,
    ) -> list[AgentHarnessToolOutput]:
        session = await self.db.get(AgentHarnessSession, session_id)
        if (
            session is None
            or session.status == "deleted"
            or str(session.workspace_id) != workspace_id
            or session.user_id != user_id
        ):
            raise NotFoundError(f"Agent session not found: {session_id}")
        return await self.repo.list_for_session(session_id, run_id=run_id)

    async def get(
        self, *, output_id: str, workspace_id: str, user_id: str
    ) -> AgentHarnessToolOutput:
        output = await self.repo.get_owned(
            output_id, workspace_id=workspace_id, user_id=user_id
        )
        if output is None:
            raise NotFoundError(f"Agent tool output not found: {output_id}")
        return output

    async def download_path(
        self, *, output_id: str, workspace_id: str, user_id: str
    ) -> tuple[Path, str, str]:
        output = await self.get(
            output_id=output_id, workspace_id=workspace_id, user_id=user_id
        )
        resource = output.resource_ref or {}
        try:
            legacy_storage = resource.get("legacy_storage") == "artifact"
            path = safe_join(
                (
                    agent_artifacts_root()
                    if legacy_storage
                    else agent_session_tool_outputs_root(str(output.session_id))
                ),
                str(output.file_path),
                escape_message="Agent tool output path escapes managed storage",
            )
        except PermissionError as exc:
            raise NotFoundError("Agent tool output file is invalid") from exc
        if not path.is_file():
            raise NotFoundError("Agent tool output file was not found")
        return path, str(resource.get("filename") or path.name), "application/json"

    def writer(self, *, session_id: str, run_id: str, fence: RunFence):
        async def write(payload: dict[str, Any]) -> dict[str, Any]:
            if payload.get("type") != "command_output":
                raise ValueError(
                    "Tool output writer accepts only command_output payloads"
                )
            return await self._store(
                payload,
                session_id=session_id,
                run_id=run_id,
                fence=fence,
            )

        return write

    async def _store(
        self,
        payload: dict[str, Any],
        *,
        session_id: str,
        run_id: str,
        fence: RunFence,
    ) -> dict[str, Any]:
        tool_call_id = payload.get("tool_call_id")
        if not isinstance(tool_call_id, str) or not tool_call_id.strip():
            raise ValueError("Tool output requires a tool call id")
        output_id = str(
            uuid5(
                NAMESPACE_URL,
                f"bioinfoflow:agent-tool-output:{session_id}:{run_id}:{tool_call_id}",
            )
        )
        root = agent_tool_output_root(session_id, output_id)
        staging_root = root.with_name(f".{output_id}.{uuid4()}.staging")
        staging_root.mkdir(parents=True, exist_ok=False)
        filename = "tool-output.json"
        output_path = staging_root / filename
        stored_payload = {
            **payload,
            "tool_output_id": output_id,
            "session_id": session_id,
            "run_id": run_id,
        }
        encoded = json.dumps(
            stored_payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()
        resource_ref = {
            "kind": "stored_file",
            "filename": filename,
            "mime_type": "application/json",
            "size_bytes": len(encoded),
            "sha256": digest,
        }
        moved_to_final_root = False
        try:
            async with aiofiles.open(output_path, "xb") as output:
                await output.write(encoded)
            try:
                tool_output = await self.repo.create_for_run(
                    id=output_id,
                    session_id=session_id,
                    run_id=run_id,
                    fence=fence,
                    commit=False,
                    tool_call_id=tool_call_id,
                    command=str(payload.get("command") or "Shell command"),
                    cwd=str(payload.get("cwd")) if payload.get("cwd") else None,
                    exit_code=(
                        int(payload["exit_code"])
                        if payload.get("exit_code") is not None
                        else None
                    ),
                    file_path=f"{output_id}/{filename}",
                    resource_ref=resource_ref,
                )
            except IntegrityError:
                await self.db.rollback()
                existing = await self.repo.get(output_id)
                if existing is None or existing.resource_ref != resource_ref:
                    raise ConflictError(
                        "Tool output conflicts with an existing tool call"
                    )
                existing_path = root / filename
                if (
                    not existing_path.is_file()
                    or hashlib.sha256(existing_path.read_bytes()).hexdigest() != digest
                ):
                    raise RuntimeError("Tool output conflicts with managed storage")
                shutil.rmtree(staging_root, ignore_errors=True)
                return _tool_output_reference(existing)
            if root.exists():
                raise FileExistsError("Tool output storage already exists")
            staging_root.rename(root)
            moved_to_final_root = True
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            shutil.rmtree(staging_root, ignore_errors=True)
            if moved_to_final_root:
                shutil.rmtree(root, ignore_errors=True)
            raise
        return _tool_output_reference(tool_output)


def _tool_output_reference(output: AgentHarnessToolOutput) -> dict[str, Any]:
    return {
        "tool_output_id": str(output.id),
        "resource": {
            **output.resource_ref,
            "session_id": str(output.session_id),
            "run_id": str(output.run_id) if output.run_id else None,
        },
    }


async def recover_agent_tool_output_storage(db) -> int:
    """Remove interrupted staging trees and final trees without a DB owner."""

    root = agent_tool_outputs_root()
    if not root.exists():
        return 0
    expected = await AgentHarnessToolOutputRepository(db).storage_identities()
    removed = 0
    for session_root in root.iterdir():
        if session_root.is_symlink():
            session_root.unlink()
            removed += 1
            continue
        if not session_root.is_dir():
            continue
        for candidate in session_root.iterdir():
            identity = (session_root.name, candidate.name)
            if not candidate.name.startswith(".") and identity in expected:
                continue
            if candidate.is_symlink() or candidate.is_file():
                candidate.unlink()
            else:
                shutil.rmtree(candidate)
            removed += 1
        try:
            session_root.rmdir()
        except OSError:
            pass
    return removed


__all__ = ["AgentHarnessToolOutputService", "recover_agent_tool_output_storage"]
