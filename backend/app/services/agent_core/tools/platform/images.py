from __future__ import annotations

from typing import Any

from app.services.agent_core.tools.specs import AgentToolContext, AgentToolSpec
from app.services.image_service import ImageService


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


def _value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)
