from __future__ import annotations

import asyncio
from typing import Any

from app.services.agent_core.sandbox import FilesystemPolicy
from app.services.agent_core.tools.specs import AgentToolContext, AgentToolSpec
from app.services.authorization_service import AuthorizationService
from app.services.image_service import ImageService
from app.utils.exceptions import NotFoundError


def _image_summary(image) -> dict[str, Any]:
    return {
        "id": str(image.id),
        "name": image.name,
        "tag": image.tag,
        "full_name": image.full_name,
        "registry": image.registry,
        "status": _value(image.status),
        "size_bytes": getattr(image, "size_bytes", None),
        "entrypoint": getattr(image, "entrypoint", None),
        "env": getattr(image, "env", None),
        "labels": getattr(image, "labels", None),
    }


class ListImagesTool:
    spec = AgentToolSpec(
        name="images.list",
        description="List registered Docker image assets.",
        input_schema={
            "type": "object",
            "properties": {
                "search": {"type": "string"},
                "status": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "force_sync": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "images": {"type": "array"},
                "total_count": {"type": "integer"},
                "status": {"type": "object"},
            },
            "required": ["images", "total_count", "status"],
        },
        risk_level="read",
        read_scope=["images"],
        audit="List Docker image assets.",
    )

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        service = ImageService(context.db)
        images, pagination, status = await service.list_images(
            limit=int(input.get("limit") or 20),
            search=input.get("search"),
            status=input.get("status") or "remote",
            force_sync=bool(input.get("force_sync", False)),
        )
        return {
            "images": [
                {
                    "id": str(image.id),
                    "name": image.name,
                    "tag": image.tag,
                    "full_name": image.full_name,
                    "registry": image.registry,
                    "status": _value(image.status),
                    "size_bytes": image.size_bytes,
                    "entrypoint": image.entrypoint,
                    "env": image.env,
                    "labels": image.labels,
                }
                for image in images
            ],
            "total_count": pagination.total_count or 0,
            "status": status,
        }


class GetImageTool:
    spec = AgentToolSpec(
        name="images.get",
        description="Read Docker image asset details by id.",
        input_schema={
            "type": "object",
            "properties": {"image_id": {"type": "string"}},
            "required": ["image_id"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"image": {"type": "object"}},
            "required": ["image"],
        },
        risk_level="read",
        read_scope=["images"],
        audit="Read Docker image asset.",
    )

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        image = await ImageService(context.db).get_image(str(input["image_id"]))
        if image is None:
            raise NotFoundError("Image not found")
        return {"image": _image_summary(image)}


class PullImageTool:
    spec = AgentToolSpec(
        name="images.pull",
        description="Pull a Docker image from a registry into the image module.",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "tag": {"type": "string"},
                "registry": {"type": "string"},
                "project_id": {"type": "string"},
            },
            "required": ["name"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"image": {"type": "object"}},
            "required": ["image"],
        },
        risk_level="act_high",
        read_scope=["images"],
        write_scope=["images"],
        audit="Pull a Docker image.",
        rollback_hint="Delete the pulled image from the image module if it is unwanted.",
        artifact_policy={"type": "image"},
        timeout_seconds=60,
    )

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        service = ImageService(context.db)
        image = await service.pull_image(
            name=str(input["name"]),
            tag=str(input.get("tag") or "latest"),
            registry=str(input.get("registry") or "docker.io"),
            project_id=input.get("project_id"),
            user_id=context.user_id,
            workspace_id=context.workspace_id,
        )
        return {"image": _image_summary(image)}


class BuildImageTool:
    spec = AgentToolSpec(
        name="images.build",
        description=(
            "Build a Docker image from a Dockerfile and context directory, then "
            "register it in the image module. Use after cloning or writing a repo."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "tag": {"type": "string"},
                "context_path": {"type": "string"},
                "dockerfile": {"type": "string"},
            },
            "required": ["tag", "context_path"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "tag": {"type": "string"},
                "exit_code": {"type": "integer"},
                "stdout": {"type": "string"},
                "stderr": {"type": "string"},
                "image": {"type": "object"},
            },
            "required": ["tag", "exit_code", "stdout", "stderr"],
        },
        risk_level="act_high",
        read_scope=["images", "workspace"],
        write_scope=["images"],
        audit="Build a Docker image from a local context.",
        rollback_hint="Remove the built image with `docker rmi <tag>` if it is unwanted.",
        artifact_policy={"type": "image"},
        timeout_seconds=600,
    )

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        tag = str(input["tag"])
        context_dir = FilesystemPolicy().require_allowed_dir(input["context_path"])
        argv = ["docker", "build", "-t", tag]
        if input.get("dockerfile"):
            argv += ["-f", str(input["dockerfile"])]
        argv.append(str(context_dir))

        process = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(context_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        exit_code = int(process.returncode or 0)
        result: dict[str, Any] = {
            "tag": tag,
            "exit_code": exit_code,
            "stdout": _limit(stdout.decode("utf-8", errors="replace")),
            "stderr": _limit(stderr.decode("utf-8", errors="replace")),
        }
        built = None
        if exit_code == 0:
            # Force a catalog sync so the freshly built image is registered.
            service = ImageService(context.db)
            images, _pagination, _status = await service.list_images(
                status="local", force_sync=True
            )
            built = next((image for image in images if image.full_name == tag), None)
        if built is not None:
            result["image"] = _image_summary(built)
        return result


class DeleteImageTool:
    spec = AgentToolSpec(
        name="images.delete",
        description="Delete a Docker image asset and remove the image from Docker when possible.",
        input_schema={
            "type": "object",
            "properties": {
                "image_id": {"type": "string"},
                "force": {"type": "boolean"},
            },
            "required": ["image_id"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "image_id": {"type": "string"},
                "deleted": {"type": "boolean"},
            },
            "required": ["image_id", "deleted"],
        },
        risk_level="destructive",
        read_scope=["images"],
        write_scope=["images"],
        audit="Delete Docker image asset.",
        rollback_hint="Pull or build the image again if it is needed.",
    )

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        image_id = str(input["image_id"])
        service = ImageService(context.db)
        image = await service.get_image(image_id)
        if image is None:
            raise NotFoundError("Image not found")
        await AuthorizationService(context.db).require_destructive_business_access(
            workspace_id=context.workspace_id,
            user_id=context.user_id,
        )
        deleted = await service.delete_image(image, force=bool(input.get("force", False)))
        return {"image_id": image_id, "deleted": bool(deleted)}


def _limit(text: str, limit: int = 16000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n[truncated]"


def _value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)
