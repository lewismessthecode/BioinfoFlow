from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from uuid import UUID

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.database import async_session_maker
from app.models.conversation import Conversation
from app.models.image import DockerImage, ImageStatus
from app.models.message import Message, MessageRole, MessageType
from app.models.project import Project
from app.models.workflow import Workflow, WorkflowEngine, WorkflowSource
from app.path_layout import ensure_project_layout


async def seed() -> None:
    project_id = UUID("11111111-1111-1111-1111-111111111111")
    workflow_id = UUID("22222222-2222-2222-2222-222222222222")
    image_id = UUID("33333333-3333-3333-3333-333333333333")
    conversation_id = UUID("44444444-4444-4444-4444-444444444444")
    message_id = UUID("55555555-5555-5555-5555-555555555555")

    async with async_session_maker() as session:
        project = Project(
            id=project_id,
            name="Demo Project",
            description="Seeded project",
            storage_mode="managed",
        )
        workflow = Workflow(
            id=workflow_id,
            name="nf-core/viralrecon",
            description="Seeded workflow",
            source=WorkflowSource.NFCORE,
            engine=WorkflowEngine.NEXTFLOW,
            source_ref="https://github.com/nf-core/viralrecon",
            bundle_kind="remote_ref",
            version="2.6.0",
        )
        image = DockerImage(
            id=image_id,
            name="bioinfoflow/bwa",
            tag="v2.2.1",
            full_name="bioinfoflow/bwa:v2.2.1",
            description="Seeded image",
            status=ImageStatus.LOCAL,
            registry="docker.io",
        )
        conversation = Conversation(id=conversation_id, project_id=project_id)
        message = Message(
            id=message_id,
            conversation_id=conversation_id,
            project_id=project_id,
            role=MessageRole.SYSTEM,
            type=MessageType.TEXT,
            content="Seeded conversation",
            message_metadata=None,
        )

        await session.merge(project)
        await session.merge(workflow)
        await session.merge(image)
        await session.merge(conversation)
        await session.merge(message)
        await session.commit()
        ensure_project_layout(project)


if __name__ == "__main__":
    asyncio.run(seed())
