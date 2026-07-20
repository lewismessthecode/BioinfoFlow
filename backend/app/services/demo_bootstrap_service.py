from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.schema_extractor import derive_form_spec
from app.path_layout import (
    ensure_project_layout,
    project_data_root,
    workflow_bundle_home,
    workflow_metadata_path,
)
from app.repositories.project_repo import ProjectRepository
from app.repositories.project_workflow_binding_repo import (
    ProjectWorkflowBindingRepository,
)
from app.repositories.project_workflow_pin_repo import ProjectWorkflowPinRepository
from app.repositories.workflow_repo import WorkflowRepository
from app.services.demo_contract import DEMO_WORKFLOW
from app.services.workflow_form_spec import reconcile_workflow_form_spec
from app.services.workflow_validator import WorkflowValidator


DEMO_MARKER = DEMO_WORKFLOW.marker
DEMO_PROJECT_NAME = "Bioinfoflow Demo"
DEMO_WORKFLOW_NAME = DEMO_WORKFLOW.name
DEMO_WORKFLOW_VERSION = DEMO_WORKFLOW.version
DEMO_RUNTIME_IMAGE = DEMO_WORKFLOW.runtime_image
DEMO_ENTRYPOINT = DEMO_WORKFLOW.entrypoint_relpath
DEMO_ASSET_ROOT = Path(__file__).resolve().parents[1] / "demo_assets" / "quickstart"
DEMO_PROJECT_FILES = ("samples.tsv", "sample-a.fastq", "sample-b.fastq")

@dataclass(slots=True)
class _LockEntry:
    lock: asyncio.Lock
    references: int = 0


class KeyedAsyncLockPool:
    def __init__(self) -> None:
        self._entries: dict[str, _LockEntry] = {}
        self._guard = asyncio.Lock()

    @asynccontextmanager
    async def hold(self, key: str) -> AsyncIterator[None]:
        async with self._guard:
            entry = self._entries.setdefault(key, _LockEntry(asyncio.Lock()))
            entry.references += 1
        try:
            async with entry.lock:
                yield
        finally:
            async with self._guard:
                entry.references -= 1
                if entry.references == 0 and self._entries.get(key) is entry:
                    self._entries.pop(key, None)

    def clear(self) -> None:
        if any(entry.references for entry in self._entries.values()):
            raise RuntimeError("Cannot clear bootstrap locks while they are active")
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)


_bootstrap_locks = KeyedAsyncLockPool()


class DemoBootstrapService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.project_repo = ProjectRepository(session)
        self.workflow_repo = WorkflowRepository(session)
        self.binding_repo = ProjectWorkflowBindingRepository(session)
        self.pin_repo = ProjectWorkflowPinRepository(session)

    async def bootstrap(self, *, workspace_id: str, user_id: str) -> dict:
        async with _bootstrap_locks.hold(workspace_id):
            try:
                return await self._bootstrap_locked(
                    workspace_id=workspace_id,
                    user_id=user_id,
                )
            except IntegrityError:
                await self.session.rollback()
                return await self._bootstrap_locked(
                    workspace_id=workspace_id,
                    user_id=user_id,
                )
            except BaseException:
                await self.session.rollback()
                raise

    async def _bootstrap_locked(self, *, workspace_id: str, user_id: str) -> dict:
        project_id = str(
            uuid5(
                NAMESPACE_URL,
                f"bioinfoflow:quickstart-project:{workspace_id}",
            )
        )
        project = await self.project_repo.get(project_id)
        created = False

        if project is None:
            if not await self._workspace_is_fresh(workspace_id=workspace_id):
                return self._not_ready_result()
            project = await self.project_repo.add(
                id=project_id,
                name=DEMO_PROJECT_NAME,
                description=(
                    "Managed quickstart assets for the first Agent-guided analysis. "
                    f"Marker: {DEMO_MARKER}"
                ),
                storage_mode="managed",
                external_root_path=None,
                remote_connection_id=None,
                container_registry_id=None,
                remote_root_path=None,
                user_id=user_id,
                created_by_user_id=user_id,
                workspace_id=workspace_id,
                is_default=False,
            )
            created = True
        else:
            self._validate_managed_project(
                project,
                workspace_id=workspace_id,
            )

        ensure_project_layout(project)
        self._repair_project_files(project)
        workflow = await self._ensure_workflow()
        await self._ensure_binding_and_pin(
            project_id=str(project.id),
            workflow=workflow,
        )
        await self.session.commit()

        return {
            "ready": True,
            "created": created,
            "demo_project_id": str(project.id),
            "workflow_id": str(workflow.id),
            "starter_context": self._starter_context(
                project_id=str(project.id),
                workflow_id=str(workflow.id),
            ),
        }

    async def _workspace_is_fresh(self, *, workspace_id: str) -> bool:
        projects, _pagination = await self.project_repo.list(
            limit=20,
            workspace_id=workspace_id,
        )
        return not any(not project.is_default for project in projects)

    async def _ensure_workflow(self):
        workflow_id = DEMO_WORKFLOW.id
        workflow = await self.workflow_repo.get(workflow_id)
        if workflow is None:
            preclaimed = await self.workflow_repo.get_by_unique(
                source=DEMO_WORKFLOW.source,
                name=DEMO_WORKFLOW.name,
                version=DEMO_WORKFLOW.version,
            )
            if preclaimed is not None:
                raise FileExistsError("Canonical demo workflow tuple is already in use")

        if workflow is not None:
            self._validate_managed_workflow(workflow)
            self._repair_workflow_bundle(workflow_id=str(workflow.id))
            self._write_workflow_metadata(workflow_id=str(workflow.id))
            return workflow

        workflow_content = (DEMO_ASSET_ROOT / DEMO_ENTRYPOINT).read_text(
            encoding="utf-8"
        )
        self._repair_workflow_bundle(workflow_id=workflow_id)
        validation = await WorkflowValidator().validate_and_extract(
            content=workflow_content,
            engine="wdl",
            file_name=DEMO_ENTRYPOINT,
            source=str(DEMO_ASSET_ROOT / DEMO_ENTRYPOINT),
        )
        if not validation.valid:
            errors = "; ".join(error.message for error in validation.errors)
            raise ValueError(f"Bundled demo workflow is invalid: {errors}")
        schema_json = validation.to_schema_json()
        form_spec = reconcile_workflow_form_spec(
            derive_form_spec(schema_json, "wdl"),
            workflow_id=workflow_id,
            source=DEMO_WORKFLOW.source,
            engine=DEMO_WORKFLOW.engine,
            bundle_root=workflow_bundle_home(workflow_id),
        ).model_dump(mode="json")
        workflow = await self.workflow_repo.add(
            id=workflow_id,
            name=DEMO_WORKFLOW_NAME,
            description=(
                "Tiny deterministic biological read summary. "
                f"Marker: {DEMO_MARKER}"
            ),
            source=DEMO_WORKFLOW.source,
            engine=DEMO_WORKFLOW.engine,
            source_ref=DEMO_WORKFLOW.source_ref,
            entrypoint_relpath=DEMO_ENTRYPOINT,
            bundle_kind=DEMO_WORKFLOW.bundle_kind,
            version=DEMO_WORKFLOW_VERSION,
            estimated_time="Under 1 minute",
            container_registry_id=None,
            schema_json=schema_json,
            form_spec=form_spec,
            weight=1,
        )
        self._write_workflow_metadata(workflow_id=workflow_id)
        return workflow

    async def _ensure_binding_and_pin(self, *, project_id: str, workflow) -> None:
        workflow_id = str(workflow.id)
        binding = await self.binding_repo.get_by_project_workflow(
            project_id=project_id,
            workflow_id=workflow_id,
        )
        if binding is None:
            await self.binding_repo.add(
                project_id=project_id,
                workflow_id=workflow_id,
            )

        pin = await self.pin_repo.get_by_group(
            project_id=project_id,
            workflow_source="local",
            workflow_name=DEMO_WORKFLOW_NAME,
        )
        if pin is None:
            await self.pin_repo.add(
                project_id=project_id,
                workflow_source="local",
                workflow_name=DEMO_WORKFLOW_NAME,
                pinned_workflow_id=workflow_id,
            )
        elif str(pin.pinned_workflow_id) != workflow_id:
            await self.pin_repo.update_all_pending(
                pin,
                pinned_workflow_id=workflow_id,
            )

    def _repair_project_files(self, project) -> None:
        root = project_data_root(project)
        for name in DEMO_PROJECT_FILES:
            self._write_canonical_file(
                root / name,
                (DEMO_ASSET_ROOT / name).read_bytes(),
            )

    def _repair_workflow_bundle(self, *, workflow_id: str) -> None:
        self._write_canonical_file(
            workflow_bundle_home(workflow_id) / DEMO_ENTRYPOINT,
            (DEMO_ASSET_ROOT / DEMO_ENTRYPOINT).read_bytes(),
        )

    def _write_workflow_metadata(self, *, workflow_id: str) -> None:
        payload = {
            "workflow_id": workflow_id,
            "source": DEMO_WORKFLOW.source,
            "source_ref": DEMO_WORKFLOW.source_ref,
            "entrypoint_relpath": DEMO_ENTRYPOINT,
            "bundle_kind": DEMO_WORKFLOW.bundle_kind,
            "name": DEMO_WORKFLOW_NAME,
            "engine": DEMO_WORKFLOW.engine,
            "version": DEMO_WORKFLOW_VERSION,
            "marker": DEMO_MARKER,
            "runtime_image": DEMO_RUNTIME_IMAGE,
        }
        self._write_canonical_file(
            workflow_metadata_path(workflow_id),
            json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n",
        )

    @staticmethod
    def _write_canonical_file(target: Path, content: bytes) -> None:
        if target.exists() and target.read_bytes() == content:
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
        temporary.write_bytes(content)
        temporary.replace(target)

    @staticmethod
    def _validate_managed_project(
        project,
        *,
        workspace_id: str,
    ) -> None:
        if (
            str(project.workspace_id) != workspace_id
            or project.name != DEMO_PROJECT_NAME
            or project.storage_mode != "managed"
            or DEMO_MARKER not in (project.description or "")
        ):
            raise FileExistsError("Canonical demo project id is already in use")

    @staticmethod
    def _validate_managed_workflow(workflow) -> None:
        if not DEMO_WORKFLOW.matches(workflow):
            raise FileExistsError("Canonical demo workflow identity is already in use")

    @staticmethod
    def _starter_context(*, project_id: str, workflow_id: str) -> dict:
        return {
            "project_id": project_id,
            "workflow": {
                "id": workflow_id,
                "name": DEMO_WORKFLOW_NAME,
                "version": DEMO_WORKFLOW_VERSION,
                "source": "local",
                "engine": "wdl",
                "scope": "project",
                "project_id": project_id,
            },
            "values": {
                "samples_tsv": "asset://project/samples.tsv",
                "sample_a_fastq": "asset://project/sample-a.fastq",
                "sample_b_fastq": "asset://project/sample-b.fastq",
            },
        }

    @staticmethod
    def _not_ready_result() -> dict:
        return {
            "ready": False,
            "created": False,
            "demo_project_id": None,
            "workflow_id": None,
            "starter_context": None,
        }
