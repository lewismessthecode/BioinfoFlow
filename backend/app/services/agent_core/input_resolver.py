from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from pypdf import PdfReader
from sqlalchemy import select

from app.config import settings
from app.models.agent_core import AgentAttachmentStatus, AgentSession
from app.models.project import Project
from app.models.project_workflow_binding import ProjectWorkflowBinding
from app.models.run import Run
from app.models.workflow import Workflow
from app.path_layout import project_home, safe_join
from app.repositories.agent_core_repo import AgentAttachmentRepository
from app.repositories.project_repo import ProjectRepository
from app.schemas.agent_core import (
    AGENT_INPUT_PARTS_ADAPTER,
    AgentDirectoryRefInputPart,
    AgentFileRefInputPart,
    AgentImageRefInputPart,
    AgentRunRefInputPart,
    AgentTextInputPart,
    AgentWorkflowRefInputPart,
)
from app.services.agent_core.attachments import AgentAttachmentService
from app.services.agent_core.transcript.messages import text_part
from app.utils.exceptions import BadRequestError, NotFoundError, PermissionDeniedError


LegacyResolver = Callable[[dict], str]
_DIRECTORY_MANIFEST_LIMIT = 100


class AgentInputResolver:
    def __init__(
        self,
        db,
        *,
        legacy_file_resolver: LegacyResolver | None = None,
        legacy_workflow_resolver: LegacyResolver | None = None,
    ) -> None:
        self.db = db
        self.attachments = AgentAttachmentRepository(db)
        self.attachment_service = AgentAttachmentService(db)
        self.projects = ProjectRepository(db)
        self.legacy_file_resolver = legacy_file_resolver
        self.legacy_workflow_resolver = legacy_workflow_resolver

    async def resolve(
        self,
        *,
        agent_session: AgentSession,
        input_text: str,
        input_parts: list[dict] | None,
    ) -> list[dict[str, Any]]:
        if not input_parts:
            return [text_part(input_text)]
        normalized = [_normalize_discriminator(part) for part in input_parts]
        try:
            parsed_parts = AGENT_INPUT_PARTS_ADAPTER.validate_python(normalized)
        except ValidationError as exc:
            unsupported = _unsupported_fields(exc)
            if unsupported:
                raise BadRequestError(
                    "input part has unsupported fields: " + ", ".join(unsupported)
                ) from exc
            raise BadRequestError(_validation_message(exc)) from exc

        result: list[dict[str, Any]] = []
        has_text = False
        for parsed, raw in zip(parsed_parts, normalized):
            if isinstance(parsed, AgentTextInputPart):
                if parsed.text.strip():
                    has_text = True
                    result.append(text_part(parsed.text))
                continue
            if isinstance(parsed, AgentFileRefInputPart):
                result.extend(await self._resolve_file(agent_session, parsed, raw))
                continue
            if isinstance(parsed, AgentDirectoryRefInputPart):
                result.extend(await self._resolve_directory(agent_session, parsed))
                continue
            if isinstance(parsed, AgentImageRefInputPart):
                result.append(await self._resolve_image(agent_session, parsed))
                continue
            if isinstance(parsed, AgentRunRefInputPart):
                result.append(await self._resolve_run(agent_session, parsed))
                continue
            if isinstance(parsed, AgentWorkflowRefInputPart):
                result.append(await self._resolve_workflow(agent_session, parsed, raw))

        if not has_text and input_text.strip():
            result.insert(0, text_part(input_text))
        return result or [text_part(input_text)]

    async def _resolve_file(
        self,
        session: AgentSession,
        part: AgentFileRefInputPart,
        raw: dict,
    ) -> list[dict[str, Any]]:
        if part.attachment_id is not None:
            attachment = await self._require_attachment(
                session, str(part.attachment_id)
            )
            if attachment.kind == "folder":
                raise BadRequestError("file_ref cannot reference a folder")
            if attachment.kind == "image":
                return [
                    _image_reference(
                        attachment,
                        detail="high",
                    )
                ]
            root = self.attachment_service.validated_root(attachment)
            original = safe_join(
                root,
                str((attachment.attachment_metadata or {}).get("preview_relpath") or ""),
                escape_message="Attachment file escapes its root",
            )
            return [
                text_part(
                    _file_context_text(
                        original,
                        label=part.label or attachment.filename,
                        mime_type=attachment.mime_type,
                        include_content=part.include_content,
                    )
                )
            ]

        if part.project_id is not None:
            project = await self._require_project(session, str(part.project_id))
            target = _project_target(project, part.path or "", allow_directory=False)
            return [
                text_part(
                    _file_context_text(
                        target,
                        label=part.label or target.name,
                        mime_type=None,
                        include_content=part.include_content,
                    )
                )
            ]

        if self.legacy_file_resolver is None:
            raise BadRequestError("Legacy absolute file references are unsupported")
        return [text_part(self.legacy_file_resolver(raw))]

    async def _resolve_directory(
        self,
        session: AgentSession,
        part: AgentDirectoryRefInputPart,
    ) -> list[dict[str, Any]]:
        if part.attachment_id is not None:
            attachment = await self._require_attachment(
                session, str(part.attachment_id)
            )
            if attachment.kind != "folder":
                raise BadRequestError("directory_ref requires a folder attachment")
            manifest = list((attachment.attachment_metadata or {}).get("manifest") or [])
            reference = {
                "type": "directory_ref",
                "attachment_id": str(attachment.id),
                "label": part.label or attachment.filename,
            }
            return [reference, text_part(_directory_context(manifest, attachment.filename))]

        project = await self._require_project(session, str(part.project_id))
        target = _project_target(project, part.path or "", allow_directory=True)
        manifest = _local_directory_manifest(target)
        reference = {
            "type": "directory_ref",
            "project_id": str(project.id),
            "path": part.path,
            "label": part.label or target.name,
        }
        return [reference, text_part(_directory_context(manifest, reference["label"]))]

    async def _resolve_image(
        self,
        session: AgentSession,
        part: AgentImageRefInputPart,
    ) -> dict[str, Any]:
        attachment = await self._require_attachment(session, str(part.attachment_id))
        if attachment.kind != "image" or not str(attachment.mime_type).startswith(
            "image/"
        ):
            raise BadRequestError("image_ref requires an image attachment")
        return _image_reference(attachment, detail=part.detail)

    async def _resolve_run(
        self,
        session: AgentSession,
        part: AgentRunRefInputPart,
    ) -> dict[str, str]:
        row = (
            await self.db.execute(
                select(Run, Workflow.name)
                .join(Project, Project.id == Run.project_id)
                .outerjoin(Workflow, Workflow.id == Run.workflow_id)
                .where(
                    Run.run_id == part.run_id,
                    Project.workspace_id == session.workspace_id,
                )
            )
        ).first()
        if row is None:
            raise NotFoundError("Run not found")
        run, workflow_name = row
        lines = [
            "Referenced run (server-validated):",
            f"Run ID: {run.run_id}",
            f"Status: {run.status.value if hasattr(run.status, 'value') else run.status}",
            f"Project ID: {run.project_id}",
        ]
        if workflow_name:
            lines.append(f"Workflow: {workflow_name}")
        if run.started_at:
            lines.append(f"Started: {run.started_at.isoformat()}")
        if run.completed_at:
            lines.append(f"Completed: {run.completed_at.isoformat()}")
        if run.error_message:
            lines.append(f"Error: {run.error_message}")
        return text_part("\n".join(lines))

    async def _resolve_workflow(
        self,
        session: AgentSession,
        part: AgentWorkflowRefInputPart,
        raw: dict,
    ) -> dict[str, str]:
        if part.workflow_id is None:
            if part.project_id is not None:
                await self._require_project(session, str(part.project_id))
            if self.legacy_workflow_resolver is not None:
                return text_part(self.legacy_workflow_resolver(raw))
            scope = "All registered workflows" if part.scope == "global" else "Project workflows"
            return text_part(f"Workflow context: {scope}")

        workflow = await self.db.get(Workflow, str(part.workflow_id))
        if workflow is None:
            raise NotFoundError("Workflow not found")
        if part.project_id is not None:
            project = await self._require_project(session, str(part.project_id))
            binding = await self.db.scalar(
                select(ProjectWorkflowBinding.id).where(
                    ProjectWorkflowBinding.project_id == project.id,
                    ProjectWorkflowBinding.workflow_id == workflow.id,
                )
            )
            if binding is None:
                raise PermissionDeniedError("Workflow is not bound to the project")
        return text_part(
            "\n".join(
                [
                    "Referenced workflow (server-validated):",
                    f"Workflow ID: {workflow.id}",
                    f"Name: {workflow.name}",
                    f"Version: {workflow.version}",
                    f"Engine: {workflow.engine.value if hasattr(workflow.engine, 'value') else workflow.engine}",
                ]
            )
        )

    async def _require_attachment(self, session: AgentSession, attachment_id: str):
        attachment = await self.attachments.get_owned(
            attachment_id,
            session_id=str(session.id),
            workspace_id=str(session.workspace_id),
            user_id=session.user_id,
        )
        if attachment is None or attachment.status != AgentAttachmentStatus.READY:
            raise NotFoundError("Attachment not found")
        return attachment

    async def _require_project(
        self,
        session: AgentSession,
        project_id: str,
    ) -> Project:
        project = await self.projects.get(project_id)
        if project is None or str(project.workspace_id) != str(session.workspace_id):
            raise NotFoundError("Project not found")
        return project


def _normalize_discriminator(part: Any) -> dict:
    if not isinstance(part, dict):
        raise BadRequestError("input parts must be objects")
    normalized = dict(part)
    kind = normalized.pop("kind", None)
    if kind is not None:
        if normalized.get("type") not in {None, kind}:
            raise BadRequestError("input part type and kind disagree")
        normalized["type"] = kind
    return normalized


def _unsupported_fields(exc: ValidationError) -> list[str]:
    fields = []
    for error in exc.errors():
        if error.get("type") == "extra_forbidden" and error.get("loc"):
            fields.append(str(error["loc"][-1]))
    return sorted(set(fields))


def _validation_message(exc: ValidationError) -> str:
    first = exc.errors()[0]
    message = str(first.get("msg") or "Invalid input part")
    return message.replace("Value error, ", "")


def _image_reference(attachment, *, detail: str) -> dict[str, Any]:
    metadata = attachment.attachment_metadata or {}
    sha256 = metadata.get("sha256")
    if not isinstance(sha256, str) or len(sha256) != 64:
        raise NotFoundError("Attachment image metadata is invalid")
    return {
        "type": "image_ref",
        "attachment_id": str(attachment.id),
        "mime_type": attachment.mime_type,
        "sha256": sha256,
        "detail": detail,
    }


def _file_context_text(
    path: Path,
    *,
    label: str,
    mime_type: str | None,
    include_content: bool,
) -> str:
    if not path.is_file() or path.is_symlink():
        raise NotFoundError("Referenced file is not available")
    if not include_content:
        return f"Attached file reference: {label}\nContent: not included."
    if mime_type == "application/pdf" or path.read_bytes()[:5] == b"%PDF-":
        return f"Attached PDF: {label}\n\n{_pdf_text(path)}"
    limit = settings.agent_attachment_text_max_bytes
    size = path.stat().st_size
    with path.open("rb") as source:
        raw = source.read(limit + 1)
    truncated = size > limit or len(raw) > limit
    try:
        content = raw[:limit].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BadRequestError("Attached file is not valid UTF-8 text") from exc
    suffix = "\n[File truncated]" if truncated else ""
    return f"Attached file: {label}\n\n{content}{suffix}"


def _pdf_text(path: Path) -> str:
    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise BadRequestError("Encrypted PDFs are unsupported")
        pages = []
        for index, page in enumerate(
            reader.pages[: settings.agent_attachment_pdf_max_pages], start=1
        ):
            text = (page.extract_text() or "").strip()
            if text:
                pages.append(f"[Page {index}]\n{text}")
    except BadRequestError:
        raise
    except Exception as exc:
        raise BadRequestError("PDF text could not be extracted") from exc
    if not pages:
        raise BadRequestError("PDF contains no extractable text")
    combined = "\n\n".join(pages)
    max_chars = settings.agent_attachment_text_max_bytes
    if len(combined.encode("utf-8")) > max_chars:
        combined = combined.encode("utf-8")[:max_chars].decode("utf-8", errors="ignore")
        combined += "\n[PDF truncated]"
    return combined


def _project_target(project: Project, relative_path: str, *, allow_directory: bool) -> Path:
    if project.storage_mode == "remote":
        raise BadRequestError("Remote project references require remote browsing")
    target = safe_join(
        project_home(project),
        relative_path,
        escape_message="Project reference escapes its root",
    )
    if allow_directory:
        if not target.is_dir() or target.is_symlink():
            raise NotFoundError("Referenced directory is not available")
    elif not target.is_file() or target.is_symlink():
        raise NotFoundError("Referenced file is not available")
    return target


def _local_directory_manifest(root: Path) -> list[str]:
    manifest = []
    for candidate in sorted(root.rglob("*")):
        if len(manifest) >= _DIRECTORY_MANIFEST_LIMIT:
            break
        if candidate.is_symlink() or not candidate.is_file():
            continue
        manifest.append(candidate.relative_to(root).as_posix())
    return manifest


def _directory_context(manifest: list[str], label: str) -> str:
    bounded = manifest[:_DIRECTORY_MANIFEST_LIMIT]
    lines = [f"Attached directory: {label}", "Bounded manifest:"]
    lines.extend(f"- {path}" for path in bounded)
    if len(manifest) > len(bounded):
        lines.append(f"- ... {len(manifest) - len(bounded)} more files")
    lines.append(
        "Use attachments.search and attachments.read for bounded on-demand access; "
        "do not assume recursive file contents are already in context."
    )
    return "\n".join(lines)
